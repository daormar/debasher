"""
Tests that run a general program for real with debasher_exec, as installed
under bin/ by make install, on the built-in scheduler, and on Slurm where
it is installed. Like the tests of resident programs, they are skipped
unless DEBASHER_RUN_CHAOS_TEST is set.
"""

import fcntl
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from resident_run import DEBASHER_EXEC, REPO_ROOT, real_run, wait_until

pytestmark = real_run

HELLO_WORLD = REPO_ROOT / "data" / "programs" / "debasher_hello_world.sh"

# A process whose post method changes the working directory before the
# completion marker is written
CD_POST_MODULE = """\
cdpost_explain_opts()
{
    explain_opt "-x" "<int>" "Unused value"
}

cdpost_define_opts()
{
    local optlist=""
    define_opt "-x" "1" optlist || return 1
    save_opt_list optlist
}

cdpost()
{
    echo done
}

cdpost_post()
{
    cd /
}

debasher_cdpost_program()
{
    add_debasher_process "cdpost" "cpus=1 mem=32 time=00:01:00"
}
"""


def run_exec(*args, cwd=None):
    assert DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    return subprocess.run(
        [str(DEBASHER_EXEC), *args, "--sched", "BUILTIN"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_a_relative_output_directory_does_not_depend_on_the_working_directory(tmp_path):
    pfile = tmp_path / "debasher_cdpost.sh"
    pfile.write_text(CD_POST_MODULE)

    result = run_exec("--pfile", str(pfile), "--outdir", "rel", cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    outdir = tmp_path / "rel"
    script = (outdir / "__exec__" / "cdpost" / "cdpost").read_text()
    assert f'DEBASHER_DIR_NAME="{outdir}"' in script or f"DEBASHER_DIR_NAME={outdir}" in script
    # The post method's cd must not keep the completion marker from being
    # written
    assert (outdir / "__exec__" / "cdpost" / "cdpost.finished").exists()


def test_a_run_refuses_an_output_directory_whose_lock_is_held_and_writes_nothing(tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    with open(outdir / "lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))

    assert result.returncode != 0
    assert "another debasher_exec" in result.stderr
    assert not (outdir / "program.opts").exists()
    assert not (outdir / "command_line.sh").exists()


def test_the_lock_file_is_kept_after_a_run(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert (outdir / "lock").exists()


def test_check_proc_opts_leaves_the_options_of_a_run_untouched(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "first")
    assert result.returncode == 0, result.stderr
    sched_opts = outdir / ".sched_opts" / "sched_opts_hello_world"
    before = (sched_opts.read_text(), sched_opts.stat().st_mtime_ns)

    # Another debasher_exec holding the lock, as the built-in scheduler
    # does for a whole run, does not stop the check
    with open(outdir / "lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_exec(
            "--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "second", "--check-proc-opts"
        )

    assert result.returncode == 0, result.stderr
    assert "second" in result.stderr
    assert (sched_opts.read_text(), sched_opts.stat().st_mtime_ns) == before


def run_exec_with_sched(sched, *args, cwd=None):
    assert DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    return subprocess.run(
        [str(DEBASHER_EXEC), *args, "--sched", sched], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_the_standard_output_of_a_process_goes_to_its_stdout_file_only(tmp_path, sched):
    outdir = tmp_path / "out"
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(
        sched, "--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "marker_line", *extra
    )
    assert result.returncode == 0, result.stderr

    execdir = outdir / "__exec__" / "hello_world"
    assert (execdir / "hello_world.stdout").read_text() == "marker_line\n"
    assert "marker_line" not in (execdir / "hello_world.sched_out").read_text()


def test_minus_one_means_unlimited_cpus_and_memory(tmp_path):
    result = run_exec(
        "--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "out"),
        "--builtinsched-cpus", "-1", "--builtinsched-mem", "-1",
    )
    assert result.returncode == 0, result.stderr


def test_zero_cpus_is_refused(tmp_path):
    result = run_exec(
        "--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "out"), "--builtinsched-cpus", "0"
    )
    assert result.returncode != 0
    assert "positive integer" in result.stderr


def test_oneshot_accepts_limits_that_fit_every_process(tmp_path):
    result = run_exec(
        "--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "out"),
        "--builtinsched-cpus", "1", "--builtinsched-mem", "64", "--builtinsched-oneshot",
    )
    assert result.returncode == 0, result.stderr


ARRAY_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_array_example.sh"
DEBASHER_STATS = REPO_ROOT / "bin" / "debasher_stats"


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_the_elapsed_time_of_an_array_gives_the_total_of_its_tasks(tmp_path, sched):
    outdir = tmp_path / "out"
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(
        sched, "--pfile", str(ARRAY_EXAMPLE), "--outdir", str(outdir), "-c", "3", *extra
    )
    assert result.returncode == 0, result.stderr

    stats = subprocess.run(
        [str(DEBASHER_STATS), "-d", str(outdir), "-p", "array_writer"],
        capture_output=True,
        text=True,
    )
    elapsed = stats.stdout.split("ELAPSED_TIME(s):", 1)[1].strip()
    # -c 3 makes array_writer write four files, one per task
    task_time = r"\d+->\d+\.\d{3} ;"
    assert re.fullmatch(rf"\d+\.\d{{3}} : {task_time}( {task_time}){{3}}", elapsed), stats.stdout


# A process that writes the values it receives into its output directory
VALUES_MODULE = """\
values_explain_opts()
{
    explain_opt "-n" "<int>" "A negative number"
    explain_opt "-e" "<string>" "An empty value"
    explain_flag "-f" "A flag"
}

values_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-n" "-5" optlist || return 1
    define_opt "-e" "" optlist || return 1
    define_flag "-f" optlist || return 1
    save_opt_list optlist
}

values()
{
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local e=$(read_opt_value_from_func_args "-e" "$@")
    local f=no
    read_flag_from_func_args "-f" "$@" && f=yes
    echo "n=[${n}] e=[${e}] f=[${f}]"
}

debasher_values_program()
{
    add_debasher_process "values" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_process_receives_a_negative_number_an_empty_value_and_a_flag_given_last(tmp_path):
    pfile = tmp_path / "debasher_values.sh"
    pfile.write_text(VALUES_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    stdout = (outdir / "__exec__" / "values" / "values.stdout").read_text()
    assert stdout == "n=[-5] e=[] f=[yes]\n"


SKIP_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_skip_example.sh"


def test_the_skip_example_reads_the_value_its_writer_passes(tmp_path):
    outdir = tmp_path / "out"
    # The sum is even, so value_reader is not skipped
    result = run_exec("--pfile", str(SKIP_EXAMPLE), "--outdir", str(outdir), "-num-a", "1", "-num-b", "3")
    assert result.returncode == 0, result.stderr

    reader_out = next((outdir / "value_reader").glob("*.out"))
    assert reader_out.read_text() == "5\n"


# A module that reads a file next to it, by a relative path, when it is
# loaded, and a process that prints what it read
RELATIVE_READ_MODULE = """\
PARAM_FROM_FILE=$(cat params.txt)

show_param_explain_opts()
{
    explain_opt "-x" "<int>" "Unused value"
}

show_param_define_opts()
{
    local optlist=""
    define_opt "-x" "1" optlist || return 1
    save_opt_list optlist
}

show_param()
{
    echo "${PARAM_FROM_FILE}"
}

debasher_relread_program()
{
    add_debasher_process "show_param" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_a_process_sees_what_its_module_computed_when_debasher_exec_loaded_it(tmp_path, sched):
    moddir = tmp_path / "module"
    moddir.mkdir()
    (moddir / "debasher_relread.sh").write_text(RELATIVE_READ_MODULE)
    (moddir / "params.txt").write_text("value next to the module\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    outdir = tmp_path / "out"

    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(
        sched, "--pfile", str(moddir / "debasher_relread.sh"), "--outdir", str(outdir), *extra,
        cwd=elsewhere,
    )
    assert result.returncode == 0, result.stderr

    stdout = (outdir / "__exec__" / "show_param" / "show_param.stdout").read_text()
    assert stdout == "value next to the module\n"
    assert (outdir / ".exec_context.sh").exists()


# A process that waits until the file given with -gate exists, and one that
# runs once it finishes; both print what the function message of the module
# prints
GATED_MODULE = """\
message()
{
    echo "before"
}

gated_explain_opts()
{
    explain_opt "-gate" "<file>" "File whose creation lets the process end"
}

gated_identify_cmdline_opts()
{
    opt_is_cmdline "-gate"
}

gated_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-gate" optlist || return 1
    save_opt_list optlist
}

gated()
{
    local gate=$(read_opt_value_from_func_args "-gate" "$@")
    while [ ! -f "${gate}" ]; do
        sleep 0.1
    done
    message
}

later_explain_opts()
{
    explain_opt "-x" "<int>" "Unused value"
}

later_define_opts()
{
    local optlist=""
    define_opt "-x" "1" optlist || return 1
    save_opt_list optlist
}

later()
{
    message
}

debasher_gated_program()
{
    add_debasher_process "gated" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "later" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:gated"
}
"""


# The gated process alone, which the oneshot mode accepts
GATED_ONLY_MODULE = GATED_MODULE.replace(
    '    add_debasher_process "later" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:gated"\n', ""
)


def test_a_run_is_refused_while_a_process_of_an_earlier_run_is_in_progress(tmp_path):
    pfile = tmp_path / "debasher_gated.sh"
    pfile.write_text(GATED_ONLY_MODULE)
    gate = tmp_path / "gate"
    outdir = tmp_path / "out"
    args = ["--pfile", str(pfile), "--outdir", str(outdir), "-gate", str(gate)]
    gated_finished = outdir / "__exec__" / "gated" / "gated.finished"

    # In oneshot mode debasher_exec ends, and releases the lock, while the
    # gated process is still running; its output goes to a file, since the
    # process keeps a pipe open until it ends
    log = tmp_path / "oneshot.log"
    with open(log, "w") as log_file:
        result = subprocess.run(
            [str(DEBASHER_EXEC), *args, "--sched", "BUILTIN", "--builtinsched-oneshot"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
    try:
        assert result.returncode == 0, log.read_text()
        before = read_files(outdir, ["command_line.sh", "program.procspec", ".exec_context.sh"])

        again = run_exec(*args)

        assert again.returncode != 0
        assert "this program has processes being executed" in again.stderr
        assert read_files(outdir, ["command_line.sh", "program.procspec", ".exec_context.sh"]) == before
        assert not list(outdir.glob(".prep*"))
        assert not gated_finished.exists()
    finally:
        gate.write_text("")
    assert wait_until(gated_finished.exists)


def test_a_task_runs_the_code_of_the_module_as_it_was_when_the_run_was_prepared(tmp_path):
    pfile = tmp_path / "debasher_gated.sh"
    pfile.write_text(GATED_MODULE)
    gate = tmp_path / "gate"
    outdir = tmp_path / "out"
    execdir = outdir / "__exec__"

    # debasher_exec is the scheduler of the run, and launches later, whose
    # process script it writes then, only after gated finishes
    run = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN",
         "-gate", str(gate)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert wait_until((execdir / "gated" / "gated.id").exists)

        # The module is edited while the run goes on
        pfile.write_text(GATED_MODULE.replace('echo "before"', 'echo "after"'))
        gate.write_text("")

        _, stderr = run.communicate(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()
            gate.write_text("")
    assert run.returncode == 0, stderr

    assert (execdir / "gated" / "gated.stdout").read_text() == "before\n"
    assert (execdir / "later" / "later.stdout").read_text() == "before\n"


# A process that is always skipped, and one that depends on its output
# file; the output of the skipped one exists from before
SKIP_CHAIN_MODULE = """\
producer_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
}

producer_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "__PRODUCED_FILE__" optlist || return 1
    save_opt_list optlist
}

producer_skip()
{
    return 0
}

producer()
{
    echo "produced by the process" > "$(read_opt_value_from_func_args "-outf" "$@")"
}

consumer_explain_opts()
{
    explain_opt "-inf" "<file>" "Input file"
}

consumer_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "producer" "-outf" optlist || return 1
    save_opt_list optlist
}

consumer()
{
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_skipchain_program()
{
    add_debasher_process "producer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "consumer" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_a_skipped_process_counts_as_finished_and_its_dependents_run(tmp_path, sched):
    produced = tmp_path / "produced.txt"
    produced.write_text("there from before\n")
    pfile = tmp_path / "debasher_skipchain.sh"
    pfile.write_text(SKIP_CHAIN_MODULE.replace("__PRODUCED_FILE__", str(produced)))
    outdir = tmp_path / "out"

    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), *extra)
    assert result.returncode == 0, result.stderr

    assert produced.read_text() == "there from before\n"
    assert (outdir / "__exec__" / "producer" / "producer.finished").exists()
    consumer_out = (outdir / "__exec__" / "consumer" / "consumer.stdout").read_text()
    assert consumer_out == "there from before\n"


def test_the_skip_example_finishes_when_value_reader_is_skipped(tmp_path):
    outdir = tmp_path / "out"
    # The sum is odd, so value_reader is skipped
    result = run_exec("--pfile", str(SKIP_EXAMPLE), "--outdir", str(outdir), "-num-a", "1", "-num-b", "2")
    assert result.returncode == 0, result.stderr

    status = subprocess.run(
        [str(REPO_ROOT / "bin" / "debasher_status"), "-d", str(outdir)], capture_output=True, text=True
    )
    assert status.returncode == 0, status.stdout + status.stderr


# An array of four tasks whose odd tasks are skipped
SKIP_ARRAY_MODULE = """\
arr_explain_opts()
{
    explain_opt "-idx" "<int>" "Index of the task"
}

arr_define_opts()
{
    local i
    for (( i = 0; i < 4; i++ )); do
        local optlist=""
        define_opt "-idx" "${i}" optlist || return 1
        save_opt_list optlist
    done
}

arr_skip()
{
    local idx=$(read_opt_value_from_func_args "-idx" "$@")
    (( idx % 2 == 1 ))
}

arr()
{
    echo "ran $(read_opt_value_from_func_args "-idx" "$@")"
}

debasher_skiparray_program()
{
    add_debasher_process "arr" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_the_skip_of_an_array_is_decided_task_by_task(tmp_path):
    pfile = tmp_path / "debasher_skiparray.sh"
    pfile.write_text(SKIP_ARRAY_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    execdir = outdir / "__exec__" / "arr"
    for idx in range(4):
        assert (execdir / f"arr_{idx}.finished").exists()
    assert (execdir / "arr_0.stdout").read_text() == "ran 0\n"
    assert (execdir / "arr_2.stdout").read_text() == "ran 2\n"
    assert not (execdir / "arr_1.stdout").exists()
    assert not (execdir / "arr_3.stdout").exists()


FIFO_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_fifo_example.sh"


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_a_program_that_uses_fifos_is_refused_on_slurm(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec_with_sched("SLURM", "--pfile", str(FIFO_EXAMPLE), "--outdir", str(outdir))

    assert result.returncode != 0
    assert "uses fifos, which cannot be run with the SLURM scheduler" in result.stderr
    assert not (outdir / "__exec__" / "fifo_writer" / "fifo_writer").exists()


# The example programs, each with the command line options it needs
EXAMPLE_PROGRAMS = sorted((REPO_ROOT / "data" / "programs").glob("debasher_*.sh"))


@pytest.mark.parametrize("pfile", EXAMPLE_PROGRAMS, ids=lambda p: p.stem)
def test_the_options_of_an_example_program_have_one_owner_and_one_reader_per_fifo(tmp_path, pfile):
    result = run_exec("--pfile", str(pfile), "--outdir", str(tmp_path / "out"), "--check-proc-opts")
    assert "a fifo has a single reader" not in result.stderr
    assert "each task needs a fifo name of its own" not in result.stderr
    assert "is not an output option" not in result.stderr


DEBASHER_STATUS = REPO_ROOT / "bin" / "debasher_status"
DEBASHER_GET_SCHED_OUT = REPO_ROOT / "bin" / "debasher_get_sched_out"
FILE_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_file_example.sh"


def run_tool(tool, *args):
    return subprocess.run([str(tool), *args], capture_output=True, text=True)


def test_status_reports_the_processes_that_ran_even_after_the_module_changes(tmp_path):
    pfile = tmp_path / "debasher_hello_world.sh"
    pfile.write_text(HELLO_WORLD.read_text())
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    # The process is renamed in the module after the run
    pfile.write_text(pfile.read_text().replace("hello_world", "renamed_world"))

    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert status.returncode == 0, status.stdout + status.stderr
    assert "PROCESS: hello_world ; STATUS: FINISHED" in status.stdout


def test_status_of_one_process_gives_its_own_exit_code_and_refuses_an_unknown_one(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "hi")
    assert result.returncode == 0, result.stderr
    # Make the reader look unfinished
    for marker in (outdir / "__exec__" / "file_reader").glob("*.finished"):
        marker.unlink()

    assert run_tool(DEBASHER_STATUS, "-d", str(outdir), "-p", "file_writer").returncode == 0
    assert run_tool(DEBASHER_STATUS, "-d", str(outdir), "-p", "file_reader").returncode != 0
    unknown = run_tool(DEBASHER_STATUS, "-d", str(outdir), "-p", "nosuch")
    assert unknown.returncode != 0
    assert "nosuch is not a process of the program" in unknown.stderr


def test_status_reports_the_run_in_progress_while_a_debasher_exec_holds_the_lock(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert run_tool(DEBASHER_STATUS, "-d", str(outdir)).returncode == 0

    # A debasher_exec preparing a run again, before any process is in
    # progress; with -p, the status is that of the process alone
    with open(outdir / "lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
        one_process = run_tool(DEBASHER_STATUS, "-d", str(outdir), "-p", "hello_world")

    assert status.returncode == 2, status.stdout + status.stderr
    assert "PROCESS: hello_world ; STATUS: FINISHED" in status.stdout
    assert "debasher_exec is preparing or running the program" in status.stderr
    assert one_process.returncode == 0


def test_status_does_not_take_a_validation_for_a_run(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    # A debasher_exec --validate holds the lock, and marks it
    with open(outdir / "lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (outdir / "lock").write_text(f"{os.getpid()}\nvalidate\n")
        status = run_tool(DEBASHER_STATUS, "-d", str(outdir))

    assert status.returncode == 0, status.stdout + status.stderr
    assert "debasher_exec is preparing or running the program" not in status.stderr


def test_status_reports_the_run_in_progress_before_debasher_exec_writes_the_command_line(tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    with open(outdir / "lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = run_tool(DEBASHER_STATUS, "-d", str(outdir))

    assert status.returncode == 2, status.stdout + status.stderr
    assert run_tool(DEBASHER_STATUS, "-d", str(outdir)).returncode == 1


# A producer that fails until a file exists, and a consumer that copies
# what it produced, which afterany lets run after the producer failed
AFTERANY_MODULE = """\
produce_explain_opts()
{
    explain_opt "-ok" "<file>" "File whose existence lets the producer succeed"
    explain_opt "-outf" "<file>" "What the producer wrote"
}

produce_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""
    define_cmdline_opt "$cmdline" "-ok" optlist || return 1
    define_opt "-outf" "${process_outdir}/out.txt" optlist || return 1
    save_opt_list optlist
}

produce()
{
    local ok=$(read_opt_value_from_func_args "-ok" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    if [ -f "${ok}" ]; then
        echo new > "${outf}"
    else
        echo old > "${outf}"
        return 1
    fi
}

consume_explain_opts()
{
    explain_opt "-inf" "<file>" "What the producer wrote"
    explain_opt "-outf" "<file>" "A copy of it"
}

consume_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""
    define_opt_from_proc_out "-inf" "produce" "-outf" optlist || return 1
    define_opt "-outf" "${process_outdir}/copy.txt" optlist || return 1
    save_opt_list optlist
}

consume()
{
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    cp "${inf}" "${outf}"
}

debasher_afterany_program()
{
    add_debasher_process "produce" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "consume" "cpus=1 mem=32 time=00:01:00" "processdeps=afterany:produce"
}
"""


def test_a_process_that_ran_after_its_producer_failed_runs_again_once_the_producer_does(tmp_path):
    pfile = tmp_path / "debasher_afterany.sh"
    pfile.write_text(AFTERANY_MODULE)
    outdir = tmp_path / "out"
    ok = tmp_path / "ok"
    args = ("--pfile", str(pfile), "--outdir", str(outdir), "-ok", str(ok), "--wait")

    # The producer fails, and the consumer, under afterany, copies what it
    # left and finishes
    run_exec(*args)
    copy = outdir / "consume" / "copy.txt"
    assert copy.read_text() == "old\n"
    assert (outdir / "__exec__" / "consume" / "consume.finished").exists()
    assert not (outdir / "__exec__" / "produce" / "produce.finished").exists()

    # Once the producer succeeds, the consumer reads what it produces now
    ok.write_text("")
    result = run_exec(*args)
    assert result.returncode == 0, result.stderr
    assert copy.read_text() == "new\n"
    assert "consume" in result.stderr.split("Printing list of processes to rerun...")[1].split("\n")[1]


def test_get_sched_out_fails_for_a_missing_file(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    missing = run_tool(DEBASHER_GET_SCHED_OUT, "-d", str(outdir), "-p", "nosuch")
    assert missing.returncode != 0


def test_a_program_runs_and_is_inspected_from_a_directory_with_spaces(tmp_path):
    workdir = tmp_path / "dir with spaces"
    workdir.mkdir()
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", "out", cwd=workdir)
    assert result.returncode == 0, result.stderr

    status = run_tool(DEBASHER_STATUS, "-d", str(workdir / "out"))
    assert status.returncode == 0, status.stdout + status.stderr
    assert "moved" not in status.stderr


def test_a_moved_output_directory_can_be_inspected_but_not_run_again(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    moved = tmp_path / "moved"
    outdir.rename(moved)

    status = run_tool(DEBASHER_STATUS, "-d", str(moved))
    assert status.returncode == 0, status.stdout + status.stderr

    again = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(moved))
    assert again.returncode != 0
    assert "was run in" in again.stderr


@pytest.mark.parametrize(
    "example", ["debasher_namespace_example", "debasher_namespace_multidot_example"]
)
def test_a_program_with_namespaced_processes_runs(tmp_path, example):
    outdir = tmp_path / "out"
    pfile = REPO_ROOT / "data" / "programs" / f"{example}.sh"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--gen-proc-graph")
    assert result.returncode == 0, result.stderr

    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert status.returncode == 0, status.stdout + status.stderr


# A process that asks for two cpus, for a scheduler limited to one
TWO_CPUS_MODULE = CD_POST_MODULE.replace("cdpost", "twocpus").replace("cpus=1", "cpus=2")


def test_validate_launches_nothing_and_leaves_a_finished_run_as_it_was(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "first")
    assert result.returncode == 0, result.stderr
    execdir = outdir / "__exec__" / "hello_world"
    before = (execdir / "hello_world.finished").stat().st_mtime_ns

    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "second", "--validate")

    assert result.returncode == 0, result.stderr
    assert "PROCESS: hello_world ; STATUS: FINISHED" in result.stderr
    assert (execdir / "hello_world.finished").stat().st_mtime_ns == before
    assert (execdir / "hello_world.stdout").read_text() == "first\n"


# The files with which a run describes itself to its tasks and to the tools
RUN_FILES = [
    ".sched_opts/sched_opts_file_writer",
    ".sched_opts/sched_opts_file_reader",
    "program.opts",
    "program.fifos",
    "program.procspec",
    "command_line.sh",
    ".exec_context.sh",
    "__graphs__/dependency_graph.dot",
]


def read_files(outdir, names):
    return {name: (outdir / name).read_text() for name in names}


def read_run_files(outdir):
    return read_files(outdir, RUN_FILES)


def test_validate_leaves_the_files_of_a_finished_run_as_they_were(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "first")
    assert result.returncode == 0, result.stderr
    before = read_run_files(outdir)
    assert "first" in before[".sched_opts/sched_opts_file_writer"]

    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "second", "--validate")

    assert result.returncode == 0, result.stderr
    assert "second" in result.stderr
    assert read_run_files(outdir) == before
    assert not list(outdir.glob(".prep*"))


DEBASHER_LAUNCH_PROCESS = REPO_ROOT / "libexec" / "debasher_launch_process"


def test_a_preparation_that_fails_leaves_a_finished_run_that_can_be_launched_again(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "first")
    assert result.returncode == 0, result.stderr
    before = read_run_files(outdir)

    # Without -s the options of file_writer cannot be built
    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir))

    assert result.returncode != 0
    assert "option not found for process file_writer" in result.stderr
    assert read_run_files(outdir) == before
    assert not list(outdir.glob(".prep*"))

    # A task of the earlier run still finds its options
    stdout = outdir / "__exec__" / "file_reader" / "file_reader.stdout"
    stdout.unlink()
    launch = run_tool(DEBASHER_LAUNCH_PROCESS, "-d", str(outdir), "-p", "file_reader")
    assert launch.returncode == 0, launch.stdout + launch.stderr
    assert wait_until(lambda: stdout.exists() and stdout.read_text() == "first\n")


def test_validate_refuses_a_process_above_the_limits_of_the_scheduler(tmp_path):
    pfile = tmp_path / "debasher_twocpus.sh"
    pfile.write_text(TWO_CPUS_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--builtinsched-cpus", "1", "--validate")

    assert result.returncode != 0
    assert "number of cpus for process twocpus exceeds limit" in result.stderr
    assert not list(outdir.glob("__exec__/*/*.id"))


def test_debug_is_refused_and_launches_nothing(tmp_path):
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "x", "--debug")

    assert result.returncode != 0
    assert "--debug was renamed --validate" in result.stderr
    assert not (outdir / "__exec__").exists()


# An array whose elements, and an option generator whose number of tasks,
# come from Python files beside the module, and an array whose skip method
# is a Python file too
PY_FUNCS_MODULE = """\
arr_explain_opts()
{
    explain_opt "-elem" "<string>" "Element of the task"
}

arr_explain_task_shaping_opts()
{
    explain_task_shaping_opt "-n" "<int>" "Number of tasks"
}

arr_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    local array
    tasks_from_file array "py/arr_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}" || return 1

    local task_idx
    for task_idx in "${!array[@]}"; do
        local optlist=""
        define_opt "-elem" "${array[$task_idx]}" optlist || return 1
        save_opt_list optlist
    done
}

arr_skip()
{
    skip_from_file "arr" "py/arr_skip.py" "$@"
}

arr()
{
    echo "ran $(read_opt_value_from_func_args "-elem" "$@")"
}

gen_explain_opts()
{
    explain_opt "-idx" "<int>" "Index of the task"
}

gen_explain_task_shaping_opts()
{
    explain_task_shaping_opt "-n" "<int>" "Number of tasks"
}

gen_generate_opts_size()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    num_tasks_from_file "py/gen_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}"
}

gen_generate_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    define_opt "-idx" "${task_idx}" optlist || return 1
    save_opt_list optlist
}

gen()
{
    echo "gen $(read_opt_value_from_func_args "-idx" "$@")"
}

debasher_pyfuncs_program()
{
    add_debasher_process "arr" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "gen" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_the_tasks_and_the_skip_method_of_a_process_come_from_python_files(tmp_path, sched):
    moddir = tmp_path / "prg"
    (moddir / "py").mkdir(parents=True)
    pfile = moddir / "debasher_pyfuncs.sh"
    pfile.write_text(PY_FUNCS_MODULE)
    (moddir / "py" / "arr_tasks.py").write_text(
        "def tasks(run):\n    return [f'sample {i}' for i in range(int(run.value('-n')))]\n"
    )
    (moddir / "py" / "arr_skip.py").write_text("def skip(task):\n    return task.value('-elem') == 'sample 1'\n")
    (moddir / "py" / "gen_tasks.py").write_text("def tasks(run):\n    return int(run.value('-n')) - 1\n")
    outdir = tmp_path / "out"

    # Run from another directory, so that the files are found relative to
    # the module only
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(
        sched, "--pfile", str(pfile), "--outdir", str(outdir), "-n", "3", *extra, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr

    arr_dir = outdir / "__exec__" / "arr"
    for idx in range(3):
        assert (arr_dir / f"arr_{idx}.finished").exists()
    assert (arr_dir / "arr_0.stdout").read_text() == "ran sample 0\n"
    assert not (arr_dir / "arr_1.stdout").exists()
    assert (arr_dir / "arr_2.stdout").read_text() == "ran sample 2\n"

    gen_dir = outdir / "__exec__" / "gen"
    assert sorted(p.name for p in gen_dir.glob("gen_*.finished")) == ["gen_0.finished", "gen_1.finished"]


def test_a_python_tasks_file_that_fails_stops_the_preparation_of_the_run(tmp_path):
    moddir = tmp_path / "prg"
    (moddir / "py").mkdir(parents=True)
    pfile = moddir / "debasher_pyfuncs.sh"
    pfile.write_text(PY_FUNCS_MODULE)
    (moddir / "py" / "arr_tasks.py").write_text("def tasks(run):\n    raise RuntimeError('no samples')\n")
    (moddir / "py" / "arr_skip.py").write_text("def skip(task):\n    return False\n")
    (moddir / "py" / "gen_tasks.py").write_text("def tasks(run):\n    return 1\n")
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-n", "3")

    assert result.returncode != 0
    assert "RuntimeError: no samples" in result.stderr
    assert not list(outdir.glob("__exec__/*/*.id"))


# A process whose skip method fails, rather than deciding: grep cannot read
# the file that it is given
FAILING_SKIP_MODULE = SKIP_CHAIN_MODULE.replace(
    "producer_skip()\n{\n    return 0\n}",
    'producer_skip()\n{\n    grep -q "DONE" "__PRODUCED_FILE__.missing"\n}',
)


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_a_skip_method_that_fails_fails_its_task_instead_of_running_it(tmp_path, sched):
    assert FAILING_SKIP_MODULE != SKIP_CHAIN_MODULE
    produced = tmp_path / "produced.txt"
    produced.write_text("there from before\n")
    pfile = tmp_path / "debasher_skipchain.sh"
    pfile.write_text(FAILING_SKIP_MODULE.replace("__PRODUCED_FILE__", str(produced)))
    outdir = tmp_path / "out"

    extra = ["--wait"] if sched == "SLURM" else []
    run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), *extra)

    # The process did not run over the file it would produce, and did not
    # finish
    assert produced.read_text() == "there from before\n"
    execdir = outdir / "__exec__" / "producer"
    assert not (execdir / "producer.finished").exists()
    log = "".join(p.read_text() for p in execdir.glob("producer.*") if p.suffix in (".log", ".sched_out"))
    assert "the skip method of process producer failed with exit code 2" in log


# A module whose processes are in R, loaded as on a machine where configure
# found no R: it empties the interpreter of R when it is loaded, before its
# processes are added
NO_R_MODULE = """\
DEBASHER_HEREDOC_INTERPRETERS[1]=""

rheredoc_explain_opts()
{
    :
}

rheredoc_heredoc_r()
{
    echo 'cat("hi\\\\n")'
}

rext_explain_opts()
{
    :
}

debasher_nor_program()
{
    add_debasher_process "rheredoc" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "rext" "cpus=1 mem=32 time=00:01:00" "ext_alias=hello.R"
}
"""


def test_a_process_whose_interpreter_was_not_found_is_documented_but_not_run(tmp_path):
    pfile = tmp_path / "debasher_nor.sh"
    pfile.write_text(NO_R_MODULE)
    (tmp_path / "hello.R").write_text('cat("hi\\n")\n')
    outdir = tmp_path / "out"

    # Reading the module needs no interpreter
    doc = subprocess.run(
        [str(REPO_ROOT / "bin" / "debasher_doc_mod"), "-m", str(pfile)], capture_output=True, text=True
    )
    assert doc.returncode == 0, doc.stderr

    # Running it is refused before any task starts, naming each process
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 1
    for process in ("rext", "rheredoc"):
        assert f"process {process} needs the interpreter of R (RSCRIPT)" in result.stderr
    assert not (outdir / "__exec__" / "rheredoc").exists()
    assert not (outdir / "__exec__" / "rext").exists()


# An array whose first task has a flag as its only option, a word that echo
# would take for one of its own flags
ECHO_FLAG_MODULE = """\
echoflag_explain_opts()
{
    explain_flag "-n" "A flag"
    explain_opt "-x" "<int>" "A number"
}

echoflag_define_opts()
{
    local optlist=""
    define_flag "-n" optlist || return 1
    save_opt_list optlist
    optlist=""
    define_opt "-x" "1" optlist || return 1
    save_opt_list optlist
    optlist=""
    define_opt "-x" "2" optlist || return 1
    save_opt_list optlist
}

echoflag()
{
    local n=no
    read_flag_from_func_args "-n" "$@" && n=yes
    echo "n=${n} x=$(read_opt_value_from_func_args "-x" "$@")"
}

debasher_echoflag_program()
{
    add_debasher_process "echoflag" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_each_task_of_an_array_receives_its_own_options_when_the_first_one_is_only_a_flag(tmp_path):
    pfile = tmp_path / "debasher_echoflag.sh"
    pfile.write_text(ECHO_FLAG_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    execdir = outdir / "__exec__" / "echoflag"
    stdouts = [(execdir / f"echoflag_{i}.stdout").read_text() for i in range(3)]
    assert stdouts == ["n=yes x=_OPT_NOT_FOUND_\n", "n=no x=1\n", "n=no x=2\n"]


# A consumer with option lists connected to an output of its producer whose
# path holds two blanks in a row and a "*"
BLANKS_PATH_MODULE = """\
prod_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
}

prod_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/a  b*.txt" optlist || return 1
    save_opt_list optlist
}

prod()
{
    echo produced > "$(read_opt_value_from_func_args "-outf" "$@")"
}

cons_explain_opts()
{
    explain_opt "-inf" "<file>" "Input file"
}

cons_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "prod" "-outf" optlist || return 1
    save_opt_list optlist
}

cons()
{
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    echo "inf=[${inf}]"
    cat "${inf}"
}

debasher_blanks_program()
{
    add_debasher_process "prod" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "cons" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_connected_path_with_blanks_reaches_the_consumer_as_it_is_and_keeps_its_dependency(tmp_path):
    pfile = tmp_path / "debasher_blanks.sh"
    pfile.write_text(BLANKS_PATH_MODULE)
    # A file that the "*" of the path would match if it were expanded
    (tmp_path / "a").mkdir()
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    procspec = (outdir / "program.procspec").read_text().splitlines()
    cons_line = next(line for line in procspec if line.startswith("cons "))
    assert "processdeps=afterok:prod" in cons_line
    stdout = (outdir / "__exec__" / "cons" / "cons.stdout").read_text()
    assert stdout == f"inf=[{outdir}/prod/a  b*.txt]\nproduced\n"


# An option generator whose options can be generated while the run is
# prepared but not when a task of it runs, once the exec directory of its
# process exists
GEN_FAILS_AT_LAUNCH_MODULE = """\
slgen_explain_opts()
{
    explain_opt "-c" "<string>" "A value"
}

slgen_generate_opts_size()
{
    echo 2
}

slgen_generate_opts()
{
    local process_outdir=$4
    [ ! -d "${process_outdir%/*}/__exec__/slgen" ] || return 1
    local optlist=""
    define_opt "-c" "x" optlist || return 1
    save_opt_list optlist
}

slgen()
{
    echo "c=$(read_opt_value_from_func_args "-c" "$@")"
}

debasher_slgen_program()
{
    add_debasher_process "slgen" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize(
    "sched",
    [
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed"),
        ),
    ],
)
def test_a_task_whose_options_cannot_be_generated_fails_instead_of_running(tmp_path, sched):
    pfile = tmp_path / "debasher_slgen.sh"
    pfile.write_text(GEN_FAILS_AT_LAUNCH_MODULE)
    outdir = tmp_path / "out"

    extra = ["--wait"] if sched == "SLURM" else []
    run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), *extra)

    execdir = outdir / "__exec__" / "slgen"
    for i in range(2):
        assert not (execdir / f"slgen_{i}.finished").exists()
        stdout = execdir / f"slgen_{i}.stdout"
        assert not stdout.exists() or "c=" not in stdout.read_text()
    log = "".join(p.read_text() for p in execdir.glob("slgen_*.sched_out"))
    for i in range(2):
        assert f"the options of slgen (task {i}) could not be generated" in log


# An option generator that gives an option two different values
TWO_VALUES_GEN_MODULE = """\
twoval_explain_opts()
{
    explain_opt "-c" "<string>" "A value"
}

twoval_generate_opts_size()
{
    echo 2
}

twoval_generate_opts()
{
    local optlist=""
    define_opt "-c" "x" optlist || return 1
    define_opt "-c" "y" optlist || return 1
    save_opt_list optlist
}

twoval()
{
    echo "c=$(read_opt_value_from_func_args "-c" "$@")"
}

debasher_twoval_program()
{
    add_debasher_process "twoval" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize("validate", [False, True])
def test_an_option_generator_that_gives_an_option_two_values_stops_the_preparation(tmp_path, validate):
    pfile = tmp_path / "debasher_twoval.sh"
    pfile.write_text(TWO_VALUES_GEN_MODULE)
    outdir = tmp_path / "out"

    extra = ["--validate"] if validate else []
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), *extra)
    assert result.returncode != 0
    error = "Error: option -c for process twoval was given multiple, conflicting values (x y)"
    assert result.stderr.count(error) == 1, result.stderr
    assert not (outdir / "__exec__" / "twoval").exists()


# A producer and three consumers, each connected to something that does not
# exist: an option generator with no such output option, read by a process
# with option lists; and, read by an option generator, a process that does
# not exist and an output option that the producer does not have
MISSING_CONNECTION_MODULE = """\
genprod_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
}

genprod_generate_opts_size()
{
    echo 1
}

genprod_generate_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/out.txt" optlist || return 1
    save_opt_list optlist
}

genprod()
{
    echo produced > "$(read_opt_value_from_func_args "-outf" "$@")"
}

listcons_explain_opts()
{
    explain_opt "-inf" "<file>" "Input file"
}

listcons_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "genprod" "-outmissing" optlist || return 1
    save_opt_list optlist
}

listcons()
{
    echo "inf=$(read_opt_value_from_func_args "-inf" "$@")"
}

gencons_explain_opts()
{
    explain_opt "-inf" "<file>" "Input file"
}

gencons_generate_opts_size()
{
    echo 1
}

gencons_generate_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "__CONNECTED_PROCESS__" "__CONNECTED_OPT__" optlist || return 1
    save_opt_list optlist
}

gencons()
{
    echo "inf=$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_missconn_program()
{
    add_debasher_process "genprod" "cpus=1 mem=32 time=00:01:00"
    __CONSUMER__
}
"""


@pytest.mark.parametrize(
    "consumer, connected_process, connected_opt",
    [
        ("listcons", "genprod", "-outf"),
        ("gencons", "nosuchproc", "-outf"),
        ("gencons", "genprod", "-outmissing"),
    ],
)
def test_a_connection_that_does_not_resolve_stops_the_preparation(
    tmp_path, consumer, connected_process, connected_opt
):
    module = (
        MISSING_CONNECTION_MODULE.replace("__CONNECTED_PROCESS__", connected_process)
        .replace("__CONNECTED_OPT__", connected_opt)
        .replace("__CONSUMER__", f'add_debasher_process "{consumer}" "cpus=1 mem=32 time=00:01:00"')
    )
    pfile = tmp_path / "debasher_missconn.sh"
    pfile.write_text(module)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode != 0
    assert f"Error: value of option -inf for process {consumer} could not be determined" in result.stderr
    assert not (outdir / "__exec__").exists() or not any((outdir / "__exec__").iterdir())


# An option generator with one task per line of a file given on the command
# line
LINES_GEN_MODULE = """\
lines_explain_opts()
{
    explain_opt "-f" "<string>" "A line"
}

lines_explain_task_shaping_opts()
{
    explain_task_shaping_opt "-in" "<file>" "One task per line"
}

lines_generate_opts_size()
{
    wc -l < "$(get_cmdline_opt "$1" -in)"
}

lines_generate_opts()
{
    local task_idx=$5
    local line
    line=$(sed -n "$(( task_idx + 1 ))p" "$(get_cmdline_opt "$1" -in)")
    [ -n "${line}" ] || return 1
    local optlist=""
    define_opt "-f" "${line}" optlist || return 1
    save_opt_list optlist
}

lines()
{
    echo "f=$(read_opt_value_from_func_args "-f" "$@")"
}

debasher_lines_program()
{
    add_debasher_process "lines" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_an_option_generator_with_no_task_is_prepared_and_runs_nothing(tmp_path):
    pfile = tmp_path / "debasher_lines.sh"
    pfile.write_text(LINES_GEN_MODULE)
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-in", str(empty))
    assert result.returncode == 0, result.stderr
    assert "PROCESS: lines ; NUM_TASKS: 0" in (outdir / "program.opts").read_text()
    assert not list((outdir / "__exec__").glob("lines/*.finished"))


# A process with a command line option that takes a value and a flag that
# may be left out
CMDLINE_MODULE = """\
cl_explain_opts()
{
    explain_opt "-s" "<string>" "A string"
    explain_flag "-f" "A flag"
}

cl_identify_cmdline_opts()
{
    opt_is_cmdline "-s"
    opt_is_non_mandatory_cmdline "-f"
}

cl_define_opts()
{
    local optlist=""
    define_cmdline_opt "$1" "-s" optlist || return 1
    define_cmdline_flag_if_given "$1" "-f" optlist
    save_opt_list optlist
}

cl()
{
    local s=$(read_opt_value_from_func_args "-s" "$@")
    local f=no
    read_flag_from_func_args "-f" "$@" && f=yes
    printf 's=[%s] f=[%s]\\n' "${s}" "${f}"
}

debasher_cl_program()
{
    add_debasher_process "cl" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize(
    "args, expected",
    [
        (["-s", ""], "s=[] f=[no]\n"),
        (["-s", "a  b", "-f"], "s=[a  b] f=[yes]\n"),
    ],
)
def test_a_command_line_option_reaches_the_task_empty_or_with_blanks(tmp_path, args, expected):
    pfile = tmp_path / "debasher_cl.sh"
    pfile.write_text(CMDLINE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), *args)
    assert result.returncode == 0, result.stderr
    assert "too many arguments" not in result.stderr
    assert "unary operator expected" not in result.stderr
    assert (outdir / "__exec__" / "cl" / "cl.stdout").read_text() == expected


def test_a_command_line_option_followed_by_an_option_instead_of_a_value_stops_the_preparation(tmp_path):
    pfile = tmp_path / "debasher_cl.sh"
    pfile.write_text(CMDLINE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "-verbose")
    assert result.returncode != 0
    assert "option -s takes a value, but on the command line it is followed by -verbose" in result.stderr
    assert not (outdir / "__exec__" / "cl").exists()


# A module that declares the shared directory "data" and a process whose
# option names another one
SHARED_DIR_MODULE = """\
debasher_shdir_shared_dirs()
{
    define_shared_dir "data"
}

shd_explain_opts()
{
    explain_opt "-datadir" "<dir>" "A shared directory"
}

shd_define_opts()
{
    local optlist=""
    define_opt_from_shared_dir "-datadir" "__SHDIR__" optlist || return 1
    save_opt_list optlist
}

shd()
{
    ls "$(read_opt_value_from_func_args "-datadir" "$@")"
}

debasher_shdir_program()
{
    add_debasher_process "shd" "cpus=1 mem=32 time=00:01:00"
}
"""


@pytest.mark.parametrize("shdir, accepted", [("data", True), ("dta", False)])
def test_an_option_that_names_a_shared_directory_no_module_declares_stops_the_preparation(tmp_path, shdir, accepted):
    pfile = tmp_path / "debasher_shdir.sh"
    pfile.write_text(SHARED_DIR_MODULE.replace("__SHDIR__", shdir))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    if accepted:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "option -datadir asks for the shared directory dta, which no module declares" in result.stderr
        assert not (outdir / "__exec__" / "shd").exists()
