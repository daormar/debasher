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
import time
from pathlib import Path

import pytest

from resident_run import DEBASHER_EXEC, DEBASHER_STOP, REPO_ROOT, real_run, wait_until

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


def run_exec(*args, cwd=None, timeout=None):
    assert DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    return subprocess.run(
        [str(DEBASHER_EXEC), *args, "--sched", "BUILTIN"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
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


def test_get_stdout_and_get_sched_out_print_the_files_of_a_process(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "hi")
    assert result.returncode == 0, result.stderr

    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "hello_world")
    assert stdout.returncode == 0, stdout.stderr
    assert stdout.stdout == "hi\n"
    sched_out = run_tool(DEBASHER_GET_SCHED_OUT, "-d", str(outdir), "-p", "hello_world")
    assert sched_out.returncode == 0, sched_out.stderr
    assert "Process started at" in sched_out.stdout
    missing = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "hello_world", "-t", "0")
    assert missing.returncode != 0
    assert "stdout file for process hello_world could not be found" in missing.stderr


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

    # A changed option runs the process again, into the process output
    # directory that the first run created
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", "out", "-s", "again", cwd=workdir)
    assert result.returncode == 0, result.stderr
    stdout = workdir / "out" / "__exec__" / "hello_world" / "hello_world.stdout"
    assert stdout.read_text() == "again\n"


# An array of four tasks, each writing its index into its task
# subdirectory
ARRAY_OF_FOUR_MODULE = """\
arr_explain_opts()
{
    explain_opt "-idx" "<int>" "Index of the task"
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

arr_define_opts()
{
    local cmdline=$1
    local i
    for i in 0 1 2 3; do
        local optlist=""
        define_opt "-idx" "${i}" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}

arr()
{
    local idx=$(read_opt_value_from_func_args "-idx" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    echo "${idx}" > "${outd}/out"
}

debasher_array_of_four_program()
{
    add_debasher_process "arr" "cpus=1 mem=32 time=00:01:00"
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
def test_an_array_runs_into_an_output_directory_with_a_blank_in_its_path(tmp_path, sched):
    pfile = tmp_path / "debasher_array_of_four.sh"
    pfile.write_text(ARRAY_OF_FOUR_MODULE)
    outdir = tmp_path / "out sp"
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), *extra)
    assert result.returncode == 0, result.stderr
    assert "binary operator expected" not in result.stderr

    for i in range(4):
        assert (outdir / "arr" / str(i) / "out").read_text() == f"{i}\n"
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert status.returncode == 0, status.stdout + status.stderr
    assert "STATUS: FINISHED" in status.stdout


def _task_steps_process(name, body, methods=""):
    return f"""\
{name}_explain_opts()
{{
    explain_opt "-t" "<dir>" "Directory where the steps leave their traces"
}}

{name}_identify_cmdline_opts()
{{
    opt_is_cmdline "-t"
}}

{name}_define_opts()
{{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${{cmdline}}" "-t" optlist || return 1
    save_opt_list optlist
}}

{name}()
{{
    local t=$(read_opt_value_from_func_args "-t" "$@")
    {body}
}}
{methods}
"""


# Four processes, each for a step of a task: a, whose _reset_outfiles
# method fails; b, whose function fails and whose _post method leaves a
# trace; c, whose function succeeds and whose _post method fails; and d,
# which writes the exec directory that the scheduler exports to it
TASK_STEPS_MODULE = (
    _task_steps_process(
        "a", 'touch "${t}/a_ran"', "a_reset_outfiles()\n{\n    return 1\n}\n"
    )
    + _task_steps_process(
        "b",
        'touch "${t}/b_ran"; return 1',
        'b_post()\n{\n    local t=$(read_opt_value_from_func_args "-t" "$@")\n    touch "${t}/b_post"\n}\n',
    )
    + _task_steps_process("c", 'touch "${t}/c_ran"', "c_post()\n{\n    return 1\n}\n")
    + _task_steps_process("d", 'echo "${DEBASHER_PROCESS_EXECDIR:-}" > "${t}/d_execdir"')
    + """
debasher_task_steps_program()
{
    add_debasher_process "a" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "b" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "c" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "d" "cpus=1 mem=32 time=00:01:00"
}
"""
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
def test_a_task_runs_its_steps_alike_under_both_schedulers(tmp_path, sched):
    pfile = tmp_path / "debasher_task_steps.sh"
    pfile.write_text(TASK_STEPS_MODULE)
    outdir = tmp_path / "out"
    traces = tmp_path / "traces"
    traces.mkdir()
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), "-t", str(traces), *extra)
    # Processes of the program did not finish, which the status says
    assert result.returncode == 3, result.stderr

    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    # A reset that fails fails the task, which runs nothing
    assert "PROCESS: a ; STATUS: UNFINISHED" in status
    assert not (traces / "a_ran").exists()
    # The _post method runs after a function that failed, and the task fails
    assert "PROCESS: b ; STATUS: UNFINISHED" in status
    assert (traces / "b_ran").exists()
    assert (traces / "b_post").exists()
    # A _post method that fails fails a task whose function succeeded
    assert "PROCESS: c ; STATUS: UNFINISHED" in status
    assert (traces / "c_ran").exists()
    assert "PROCESS: d ; STATUS: FINISHED" in status

    # Only the built-in scheduler exports the variables of the process
    execdir = (traces / "d_execdir").read_text().strip()
    if sched == "BUILTIN":
        assert execdir == str(outdir / "__exec__" / "d")
    else:
        assert execdir == ""


def test_debasher_exec_writes_its_process_id_into_the_lock_file_and_marks_a_validation(tmp_path):
    outdir = tmp_path / "out"
    args = [str(DEBASHER_EXEC), "--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "--sched", "BUILTIN"]

    validation = subprocess.Popen([*args, "--validate"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, err = validation.communicate()
    assert validation.returncode == 0, err
    assert (outdir / "lock").read_text() == f"{validation.pid}\nvalidate\n"

    run = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, err = run.communicate()
    assert run.returncode == 0, err
    assert (outdir / "lock").read_text() == f"{run.pid}\n"


def test_the_exhaustive_option_list_of_an_earlier_run_does_not_survive_a_run_without_it(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "--gen-proc-graph")
    assert result.returncode == 0, result.stderr
    assert (outdir / "program.opts_exh").exists()

    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "again")
    assert result.returncode == 0, result.stderr
    assert not (outdir / "program.opts_exh").exists()


def test_the_old_options_are_those_of_the_last_run(tmp_path):
    outdir = tmp_path / "out"
    for value in ("first", "second"):
        result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", value)
        assert result.returncode == 0, result.stderr

    old = (outdir / "program.opts_old").read_text()
    assert "second" in old
    assert "first" not in old


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

    # The other tool that runs a process of the run refuses it too, and one
    # that reads it reads it
    launch = run_tool(REPO_ROOT / "libexec" / "debasher_launch_process", "-d", str(moved), "-p", "hello_world")
    assert launch.returncode != 0
    assert "was run in" in launch.stdout + launch.stderr
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(moved), "-p", "hello_world")
    assert stdout.returncode == 0, stdout.stderr


def test_the_tools_that_read_a_run_work_once_its_module_is_removed(tmp_path):
    pfile = tmp_path / "debasher_hello_world.sh"
    pfile.write_text(HELLO_WORLD.read_text())
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "hi")
    assert result.returncode == 0, result.stderr
    pfile.unlink()

    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert status.returncode == 0, status.stderr
    assert "PROCESS: hello_world ; STATUS: FINISHED" in status.stdout
    stats = run_tool(DEBASHER_STATS, "-d", str(outdir))
    assert stats.returncode == 0, stats.stderr
    assert "hello_world" in stats.stdout
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "hello_world")
    assert stdout.returncode == 0, stdout.stderr
    assert stdout.stdout == "hi\n"
    stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
    assert stop.returncode == 0, stop.stderr


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


# The array of four tasks, whose _conda_envs and _docker_imgs methods only
# leave a trace in the file that TRACE names
ENV_METHODS_MODULE = ARRAY_OF_FOUR_MODULE.replace("debasher_array_of_four_program", "debasher_env_methods_program") + """
arr_conda_envs()
{
    echo conda >> "TRACE"
}

arr_docker_imgs()
{
    echo docker >> "TRACE"
}
"""


def test_the_environment_methods_run_only_with_their_options_and_once_for_each_process(tmp_path):
    trace = tmp_path / "trace"
    pfile = tmp_path / "debasher_env_methods.sh"
    pfile.write_text(ENV_METHODS_MODULE.replace("TRACE", str(trace)))

    result = run_exec("--pfile", str(pfile), "--outdir", str(tmp_path / "plain"))
    assert result.returncode == 0, result.stderr
    assert not trace.exists()

    result = run_exec(
        "--pfile", str(pfile), "--outdir", str(tmp_path / "envs"), "--conda-support", "--docker-support"
    )
    assert result.returncode == 0, result.stderr
    # Once for the process, whatever its number of tasks
    assert sorted(trace.read_text().split()) == ["conda", "docker"]


CONDA_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_conda_example.sh"


def _conda_env_exists(name):
    conda = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not conda:
        return False
    listed = subprocess.run([conda, "env", "list"], capture_output=True, text=True)
    return any(line.split()[:1] == [name] for line in listed.stdout.splitlines())


@pytest.mark.skipif(not _conda_env_exists("py27"), reason="conda or its environment py27 is missing")
def test_a_process_script_activates_its_conda_environment_from_an_empty_environment(tmp_path):
    # The run starts from a shell that conda never set up, so the context of
    # the process scripts carries the functions of conda that the run loaded;
    # the script is then run, as on a node of a Slurm job with
    # --export=NONE, from an environment without CONDA_EXE
    outdir = tmp_path / "out"
    bare_env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(CONDA_EXAMPLE), "--outdir", str(outdir), "--sched", "BUILTIN",
         "--conda-support"],
        env=bare_env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "__conda_exe ()" in (outdir / ".exec_context.sh").read_text()
    verfile = outdir / "conda_example" / "python_ver.txt"
    verfile.unlink()

    script = outdir / "__exec__" / "conda_example" / "conda_example"
    result = subprocess.run(["bash", "--norc", "--noprofile", str(script)], env=bare_env,
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "Python 2.7" in verfile.read_text()


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


@pytest.mark.parametrize(
    ("addition", "message"),
    [
        # The last top-level command of the module fails while it loads
        ("\nfalse\n", "ended with status 1"),
        # An unknown dependency type stops the inference of the dependencies
        ("\nfile_reader_define_opt_deps()\n{\n    echo afterbogus\n}\n", "afterbogus"),
    ],
    ids=["module", "dependencies"],
)
def test_a_module_or_a_dependency_that_fails_leaves_a_finished_run_as_it_was_and_launches_nothing(tmp_path, addition, message):
    pfile = tmp_path / "debasher_file_example.sh"
    pfile.write_text(FILE_EXAMPLE.read_text())
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "first")
    assert result.returncode == 0, result.stderr
    before = read_run_files(outdir)
    ids = {p: p.stat().st_mtime_ns for p in (outdir / "__exec__").glob("*/*.id")}
    assert ids

    pfile.write_text(pfile.read_text() + addition)
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "second")

    assert result.returncode != 0
    assert message in result.stderr
    # The files with which the run describes itself are those of the first
    # run, and no task was launched
    assert read_run_files(outdir) == before
    assert not list(outdir.glob(".prep*"))
    assert {p: p.stat().st_mtime_ns for p in (outdir / "__exec__").glob("*/*.id")} == ids
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert "PROCESS: file_writer ; STATUS: FINISHED" in status.stdout
    assert "PROCESS: file_reader ; STATUS: FINISHED" in status.stdout


def test_a_finished_process_launched_again_that_fails_is_unfinished(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "hi")
    assert result.returncode == 0, result.stderr

    # Without the file of file_writer, file_reader fails when launched
    # again, and the completion marker of the earlier run does not stay
    (outdir / "file_writer" / "out.txt").unlink()
    execdir = outdir / "__exec__" / "file_reader"
    log = execdir / "file_reader.sched_out"
    launch = run_tool(DEBASHER_LAUNCH_PROCESS, "-d", str(outdir), "-p", "file_reader")
    assert launch.returncode == 0, launch.stdout + launch.stderr
    assert wait_until(lambda: log.exists() and "failed with exit code" in log.read_text())
    assert wait_until(lambda: "STATUS: UNFINISHED" in run_tool(DEBASHER_STATUS, "-d", str(outdir), "-p", "file_reader").stdout)
    assert not (execdir / "file_reader.finished").exists()


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


# A process that, once the run is prepared, edits the external script of an
# alias and the Python skip file of another process, both of which wait for
# it: what the two read is what the task finds when it runs
LATE_READ_MODULE = """\
editor_explain_opts()
{
    explain_opt "-outf" "<file>" "Trace of the edit"
}

editor_define_opts()
{
    local optlist=""
    define_opt "-outf" "$4/done" optlist || return 1
    save_opt_list optlist
}

editor()
{
    echo 'echo after' > "__DIR__/ext.sh"
    printf 'def skip(task):\\n    return True\\n' > "__DIR__/skipper_skip.py"
    touch "$(read_opt_value_from_func_args "-outf" "$@")"
}

ext_explain_opts()
{
    explain_opt "-inf" "<file>" "Trace of the edit"
}

ext_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "editor" "-outf" optlist || return 1
    save_opt_list optlist
}

skipper_explain_opts()
{
    explain_opt "-inf" "<file>" "Trace of the edit"
}

skipper_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "editor" "-outf" optlist || return 1
    save_opt_list optlist
}

skipper_skip()
{
    skip_from_file "skipper" "skipper_skip.py" "$@"
}

skipper()
{
    echo ran
}

debasher_lateread_program()
{
    add_debasher_process "editor" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "ext" "cpus=1 mem=32 time=00:01:00" "ext_alias=ext.sh"
    add_debasher_process "skipper" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_the_external_script_of_an_alias_and_a_python_skip_file_are_read_when_the_task_runs(tmp_path):
    pfile = tmp_path / "debasher_lateread.sh"
    pfile.write_text(LATE_READ_MODULE.replace("__DIR__", str(tmp_path)))
    (tmp_path / "ext.sh").write_text("echo before\n")
    (tmp_path / "skipper_skip.py").write_text("def skip(task):\n    return False\n")
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    # Both were edited after the run was prepared, and before their tasks
    # ran: the alias ran the new script, and the new skip file skipped
    assert (outdir / "__exec__" / "ext" / "ext.stdout").read_text() == "after\n"
    skipper_log = (outdir / "__exec__" / "skipper" / "skipper.sched_out").read_text()
    assert "skipped by its skip method" in skipper_log
    stdout = outdir / "__exec__" / "skipper" / "skipper.stdout"
    assert not stdout.exists() or stdout.read_text() == ""


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
    # What an earlier run left in the process output directory, which the
    # reset of a task that runs would remove
    (outdir / "producer").mkdir(parents=True)
    (outdir / "producer" / "left.txt").write_text("from before\n")

    extra = ["--wait"] if sched == "SLURM" else []
    run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), *extra)

    # The process did not run over the file it would produce, did not
    # finish, and its process output directory was not touched
    assert produced.read_text() == "there from before\n"
    assert (outdir / "producer" / "left.txt").read_text() == "from before\n"
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


# A module that only declares a shared directory, loaded by a module that
# adds a process
EXTRA_SHDIR_MODULE = """\
extra_shared_dirs()
{
    define_shared_dir "extradata"
}
"""

LOADS_EXTRA_MODULE = """\
load_debasher_module "extra"

loader_explain_opts()
{
    :
}

loader_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

loader()
{
    echo done
}

debasher_loader_program()
{
    add_debasher_process "loader" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_the_shared_directories_of_a_loaded_module_that_adds_no_process_are_created(tmp_path):
    (tmp_path / "extra.sh").write_text(EXTRA_SHDIR_MODULE)
    pfile = tmp_path / "debasher_loader.sh"
    pfile.write_text(LOADS_EXTRA_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert (outdir / "extradata").is_dir()


def test_outdated_code_reruns_a_finished_process_only_on_request_against_every_loaded_module(tmp_path):
    (tmp_path / "extra.sh").write_text(EXTRA_SHDIR_MODULE)
    pfile = tmp_path / "debasher_loader.sh"
    counter = tmp_path / "runs.txt"
    pfile.write_text(LOADS_EXTRA_MODULE.replace("    echo done\n", f"    echo run >> {counter}\n"))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert counter.read_text().count("run") == 1

    # The module that the program file loads, not the program file itself,
    # becomes newer than the process script of the run
    script = outdir / "__exec__" / "loader" / "loader"
    newer = script.stat().st_mtime + 10
    os.utime(tmp_path / "extra.sh", (newer, newer))

    # Without the option, a finished process does not run again
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert counter.read_text().count("run") == 1

    # With it, the process runs again, since one of the modules of the
    # program is newer than its script
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--rerun-outdated-procs", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "used outdated modules" in result.stderr
    assert counter.read_text().count("run") == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--outdir"], "Error! option --outdir needs a value"),
        (["--outdir", "out", "--builtinsched-mem"], "Error! option --builtinsched-mem needs a value"),
        (["--outdir", "out", "--builtinsched-mem", "abc"], "should be a positive amount of memory"),
        (["--outdir", "out", "--builtinsched-mem", "0"], "should be a positive amount of memory"),
        (["--outdir", "out", "--builtinsched-cpus", "x"], "should be a positive integer"),
    ],
    ids=["outdir-last", "mem-last", "mem-word", "mem-zero", "cpus-word"],
)
def test_debasher_exec_refuses_an_option_without_its_value_or_with_a_wrong_one(tmp_path, args, message):
    # The option under test comes last, after the scheduler
    result = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(HELLO_WORLD), "--sched", "BUILTIN", "--validate", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert message in result.stderr


def test_debasher_exec_takes_the_memory_of_the_builtin_scheduler_with_a_unit(tmp_path):
    result = run_exec(
        "--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "out"), "--validate", "--builtinsched-mem", "1G"
    )
    assert result.returncode == 0, result.stderr


# A process with a flag among its options
FLAG_MODULE = """\
p_explain_opts()
{
    explain_opt "-v" "" "A flag"
}

p_define_opts()
{
    local optlist=""
    define_flag "-v" optlist || return 1
    save_opt_list optlist
}

p()
{
    echo ok
}

debasher_flagged_program()
{
    add_debasher_process "p" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_the_process_graph_of_a_program_with_a_flag_is_drawn(tmp_path):
    pfile = tmp_path / "debasher_flagged.sh"
    pfile.write_text(FLAG_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--gen-proc-graph")
    assert result.returncode == 0, result.stderr
    assert (outdir / "__graphs__" / "process_graph.dot").read_text().startswith("digraph G {")


def test_debasher_exec_ignores_an_option_that_no_process_knows(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "-s", "hi", "-nosuchopt", "3")
    assert result.returncode == 0, result.stderr
    assert (outdir / "__exec__" / "hello_world" / "hello_world.stdout").read_text() == "hi\n"


# An array of twelve tasks, and a process whose task asks for the number of
# tasks of the array while it runs
TWELVE_MODULE = """\
twelve_explain_opts()
{
    explain_opt "-x" "<int>" "A number"
    explain_opt "-s" "<string>" "A string"
}

twelve_define_opts()
{
    local i
    for i in $(seq 0 11); do
        local optlist=""
        define_opt "-x" "${i}" optlist || return 1
        define_opt "-s" "a b" optlist || return 1
        save_opt_list optlist
    done
}

twelve()
{
    :
}

asker_explain_opts()
{
    :
}

asker_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

asker()
{
    echo "tasks=$(get_process_num_tasks twelve)"
}

debasher_twelve_program()
{
    add_debasher_process "twelve" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "asker" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_the_options_of_an_array_reach_its_tasks_and_the_files_of_the_run(tmp_path):
    pfile = tmp_path / "debasher_twelve.sh"
    pfile.write_text(TWELVE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    # One line of .sched_opts per task, in the order of the tasks
    lines = (outdir / ".sched_opts" / "sched_opts_twelve").read_text().splitlines()
    assert len(lines) == 12
    for i, line in enumerate(lines):
        words = line.split("<_ARG_SEP_>")
        opts_of_line = dict(zip(words[::2], words[1::2]))
        assert opts_of_line == {"-x": str(i), "-s": "a b"}

    # Each task writes the options it received, quoted, one per line
    opts = (outdir / "__exec__" / "twelve" / "twelve_3.opts").read_text().splitlines()
    assert sorted(opts) == ["-s a\\ b", "-x 3"]

    # program.opts holds the number of tasks and the options of the first ten
    line = next(l for l in (outdir / "program.opts").read_text().splitlines() if l.startswith("PROCESS: twelve "))
    assert "NUM_TASKS: 12" in line
    assert "-x 9" in line and "-x 10" not in line
    assert line.rstrip().endswith("...")


def test_a_task_reads_the_number_of_tasks_of_another_process_from_the_execution_context(tmp_path):
    pfile = tmp_path / "debasher_twelve.sh"
    pfile.write_text(TWELVE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert (outdir / "__exec__" / "asker" / "asker.stdout").read_text() == "tasks=12\n"


# An array of three tasks that write the value of -x into their own task
# subdirectory; task 2 fails while the file that -failf names exists
PARTIAL_MODULE = """\
part_explain_opts()
{
    explain_opt "-x" "<string>" "The value that each task writes"
    explain_opt "-failf" "<file>" "File whose existence makes task 2 fail"
    explain_opt "-idx" "<int>" "Index of the task"
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

part_identify_cmdline_opts()
{
    opt_is_cmdline "-x"
    opt_is_cmdline "-failf"
}

part_define_opts()
{
    local cmdline=$1
    local i
    for i in 0 1 2; do
        local optlist=""
        define_cmdline_opt "${cmdline}" "-x" optlist || return 1
        define_cmdline_opt "${cmdline}" "-failf" optlist || return 1
        define_opt "-idx" "${i}" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}

part()
{
    local x=$(read_opt_value_from_func_args "-x" "$@")
    local failf=$(read_opt_value_from_func_args "-failf" "$@")
    local idx=$(read_opt_value_from_func_args "-idx" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    if [ "${idx}" -eq 2 ] && [ -f "${failf}" ]; then
        return 1
    fi
    echo "${x}" > "${outd}/out"
}

debasher_partial_program()
{
    add_debasher_process "part" "cpus=1 mem=32 time=00:01:00"
}
"""


def run_partial(sched, pfile, outdir, failf, x):
    extra = ["--wait"] if sched == "SLURM" else []
    return run_exec_with_sched(
        sched, "--pfile", str(pfile), "--outdir", str(outdir), "-x", x, "-failf", str(failf), *extra
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
def test_an_unfinished_array_whose_options_changed_runs_every_task_again(tmp_path, sched):
    pfile = tmp_path / "debasher_partial.sh"
    pfile.write_text(PARTIAL_MODULE)
    outdir = tmp_path / "out"
    failf = tmp_path / "fail"

    # Task 2 fails, tasks 0 and 1 finish with "a"
    failf.write_text("")
    run_partial(sched, pfile, outdir, failf, "a")
    execdir = outdir / "__exec__" / "part"
    assert (execdir / "part_0.finished").exists()
    assert not (execdir / "part_2.finished").exists()

    # The options change: the finished tasks ran on an input that no
    # longer holds, and run again, so no result is left from the first run
    failf.unlink()
    result = run_partial(sched, pfile, outdir, failf, "b")
    assert result.returncode == 0, result.stderr
    for i in range(3):
        assert (outdir / "part" / str(i) / "out").read_text() == "b\n"
        assert (execdir / f"part_{i}.finished").exists()


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
def test_an_unfinished_array_run_again_runs_only_its_unfinished_tasks(tmp_path, sched):
    pfile = tmp_path / "debasher_partial.sh"
    pfile.write_text(PARTIAL_MODULE)
    outdir = tmp_path / "out"
    failf = tmp_path / "fail"

    failf.write_text("")
    run_partial(sched, pfile, outdir, failf, "a")
    execdir = outdir / "__exec__" / "part"
    kept = [execdir / "part_0.finished", execdir / "part_1.finished",
            outdir / "part" / "0" / "out", outdir / "part" / "1" / "out"]
    before = [p.stat().st_mtime_ns for p in kept]
    assert not (outdir / "part" / "2" / "out").exists()

    # Nothing changes but the failure: only task 2 runs, and the finished
    # tasks keep their completion markers and their task subdirectories
    failf.unlink()
    result = run_partial(sched, pfile, outdir, failf, "a")
    assert result.returncode == 0, result.stderr
    assert [p.stat().st_mtime_ns for p in kept] == before
    for i in range(3):
        assert (outdir / "part" / str(i) / "out").read_text() == "a\n"
    assert (execdir / "part_2.finished").exists()


# Two processes, the second with a task subdirectory
LINKED_SUBDIR_MODULE = """\
lfirst_explain_opts()
{
    explain_opt "-outf" "<file>" "What the process writes"
}

lfirst_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/out.txt" optlist || return 1
    save_opt_list optlist
}

lfirst()
{
    echo done > "$(read_opt_value_from_func_args "-outf" "$@")"
}

lsecond_explain_opts()
{
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

lsecond_define_opts()
{
    local optlist=""
    define_opt_from_process_outdir "-outd" optlist --subdir "t" || return 1
    save_opt_list optlist
}

lsecond()
{
    :
}

debasher_linkedsub_program()
{
    add_debasher_process "lfirst" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "lsecond" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_failure_to_prepare_one_process_launches_no_process(tmp_path):
    pfile = tmp_path / "debasher_linkedsub.sh"
    pfile.write_text(LINKED_SUBDIR_MODULE)
    outdir = tmp_path / "out"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (outdir / "lsecond").mkdir(parents=True)
    (outdir / "lsecond" / "t").symlink_to(elsewhere)

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode != 0
    assert "the task subdirectory t of process lsecond" in result.stderr
    assert not (outdir / "__exec__" / "lfirst" / "lfirst.id").exists()
    assert not (outdir / "lfirst" / "out.txt").exists()


# Two arrays that write, task by task, a shared subdirectory and a task
# subdirectory, the arrays that read the one with their own index, and a
# process that reads the whole shared directory
SUBDEPS_MODULE = """\
debasher_subdeps_shared_dirs()
{
    define_shared_dir "data"
}

ws_explain_opts()
{
    explain_opt "-outd" "<dir>" "Shared subdirectory of the task"
}

ws_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_opt_from_shared_dir "-outd" "data" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}

ws()
{
    echo "ws" > "$(read_opt_value_from_func_args "-outd" "$@")/f"
}

rs_explain_opts()
{
    explain_opt "-ind" "<dir>" "Shared subdirectory that ws writes"
}

rs_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_opt "-ind" "$(get_absolute_shdirname data)/${i}" optlist || return 1
        save_opt_list optlist
    done
}

rs()
{
    :
}

wt_explain_opts()
{
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

wt_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}

wt()
{
    :
}

rt_explain_opts()
{
    explain_opt "-ind" "<dir>" "Task subdirectory of wt"
}

rt_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_opt_from_proc_task_out "-ind" "wt" "${i}" "-outd" optlist || return 1
        save_opt_list optlist
    done
}

rt()
{
    :
}

whole_explain_opts()
{
    explain_opt "-dir" "<dir>" "The whole shared directory"
}

whole_define_opts()
{
    local optlist=""
    define_opt_from_shared_dir "-dir" "data" optlist || return 1
    save_opt_list optlist
}

whole()
{
    :
}

debasher_subdeps_program()
{
    add_debasher_process "ws" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "rs" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "wt" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "rt" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "whole" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_validation_infers_dependencies_through_subdirectories_and_leaves_only_empty_directories(tmp_path):
    pfile = tmp_path / "debasher_subdeps.sh"
    pfile.write_text(SUBDEPS_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 0, result.stderr
    deps = dict(re.findall(r"^PROCESS: (\S+) ; STATUS: .* processdeps=(\S+)$", result.stderr, re.M))
    assert deps == {"ws": "none", "rs": "aftercorr:ws", "wt": "none", "rt": "aftercorr:wt", "whole": "none"}

    # A validation creates only empty directories that a run creates too,
    # besides its lock, and no shared subdirectory
    assert sorted(p.name for p in outdir.iterdir()) == ["__exec__", "__fifos__", "data", "lock"]
    assert list((outdir / "data").iterdir()) == []


# w writes a file and a fifo, and r reads both: the file gives r afterok
# on w, a dependency that the two ends of a fifo cannot have
FIFO_AND_FILE_MODULE = """\
w_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-outfifo" "<fifo>" "Output fifo"
}

w_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    define_fifo_opt "-outfifo" "fifo" optlist || return 1
    save_opt_list optlist
}

w()
{
    echo f > "$(read_opt_value_from_func_args "-outf" "$@")"
    echo line > "$(read_opt_value_from_func_args "-outfifo" "$@")"
}

r_explain_opts()
{
    explain_opt "-inf" "<file>" "File of w"
    explain_opt "-infifo" "<fifo>" "Fifo of w"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "w" "-outf" optlist || return 1
    define_opt_from_proc_out "-infifo" "w" "-outfifo" optlist || return 1
    save_opt_list optlist
}
@@DEFINE_OPT_DEPS@@
r()
{
    cat "$(read_opt_value_from_func_args "-infifo" "$@")"
}

debasher_fifofile_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "r" "cpus=1 mem=32 time=00:01:00"
}
"""

# Turns the afterok that the file gives into after
FIFO_AND_FILE_AFTER = """
r_define_opt_deps()
{
    echo after
}
"""


def test_a_dependency_stronger_than_after_between_the_two_ends_of_a_fifo_stops_the_preparation(tmp_path):
    pfile = tmp_path / "debasher_fifofile.sh"
    pfile.write_text(FIFO_AND_FILE_MODULE.replace("@@DEFINE_OPT_DEPS@@", ""))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 1
    assert "Error: process r depends on w with type afterok" in result.stderr
    assert "they are the two ends of fifo w/fifo" in result.stderr
    assert "processdeps=" not in result.stderr

    # With after, the two ends are accepted, and run together
    pfile.write_text(FIFO_AND_FILE_MODULE.replace("@@DEFINE_OPT_DEPS@@", FIFO_AND_FILE_AFTER))
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 0, result.stderr
    deps = dict(re.findall(r"^PROCESS: (\S+) ; STATUS: .* processdeps=(\S+)$", result.stderr, re.M))
    assert deps == {"w": "none", "r": "after:w"}


# One process per rule of the inference: w reads what it writes itself and
# a file of w2; w and w2 both write "common", which r reads; f owns two
# fifos, one read by r and one by g, whose option dependency method gives
# after; b, an array, reads in each task the other task of the array a,
# and c, an option generator, the task of a of its own index
INFERENCE_MODULE = """\
w2_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-outcommon" "<file>" "File written by w too"
}

w2_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    define_opt "-outcommon" "$(dirname "${process_outdir}")/common" optlist || return 1
    save_opt_list optlist
}

w2()
{
    :
}

w_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-self" "<file>" "Its own output file"
    explain_opt "-inf" "<file>" "File of w2"
    explain_opt "-outcommon" "<file>" "File written by w2 too"
}

w_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    define_opt "-self" "${process_outdir}/f" optlist || return 1
    define_opt_from_proc_out "-inf" "w2" "-outf" optlist || return 1
    define_opt "-outcommon" "$(dirname "${process_outdir}")/common" optlist || return 1
    save_opt_list optlist
}

w()
{
    :
}

f_explain_opts()
{
    explain_opt "-outfifo1" "<fifo>" "Fifo read by r"
    explain_opt "-outfifo2" "<fifo>" "Fifo read by g"
}

f_define_opts()
{
    local optlist=""
    define_fifo_opt "-outfifo1" "fifo1" optlist || return 1
    define_fifo_opt "-outfifo2" "fifo2" optlist || return 1
    save_opt_list optlist
}

f()
{
    :
}

r_explain_opts()
{
    explain_opt "-incommon" "<file>" "File of w and w2"
    explain_opt "-infifo" "<fifo>" "Fifo of f"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-incommon" "w" "-outcommon" optlist || return 1
    define_opt_from_proc_out "-infifo" "f" "-outfifo1" optlist || return 1
    save_opt_list optlist
}

r()
{
    :
}

g_explain_opts()
{
    explain_opt "-infifo" "<fifo>" "Fifo of f"
}

g_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-infifo" "f" "-outfifo2" optlist || return 1
    save_opt_list optlist
}

g_define_opt_deps()
{
    echo after
}

g()
{
    :
}

a_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file of the task"
}

a_define_opts()
{
    local process_outdir=$4
    local i
    for i in 0 1; do
        local optlist=""
        define_opt "-outf" "${process_outdir}/${i}" optlist || return 1
        save_opt_list optlist
    done
}

a()
{
    :
}

b_explain_opts()
{
    explain_opt "-inf" "<file>" "File of the other task of a"
}

b_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_opt_from_proc_task_out "-inf" "a" "$((1 - i))" "-outf" optlist || return 1
        save_opt_list optlist
    done
}

b()
{
    :
}

c_explain_opts()
{
    explain_opt "-inf" "<file>" "File of the task of a of the same index"
}

c_generate_opts_size()
{
    echo 2
}

c_generate_opts()
{
    local task_idx=$5
    local optlist=""
    define_opt_from_proc_task_out "-inf" "a" "${task_idx}" "-outf" optlist || return 1
    save_opt_list optlist
}

c()
{
    :
}

debasher_inference_program()
{
    local p
    for p in w2 w f r g a b c; do
        add_debasher_process "${p}" "cpus=1 mem=32 time=00:01:00"
    done
}
"""


def test_a_validation_infers_one_dependency_for_each_rule_of_the_inference(tmp_path):
    pfile = tmp_path / "debasher_inference.sh"
    pfile.write_text(INFERENCE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 0, result.stderr
    deps = dict(re.findall(r"^PROCESS: (\S+) ; STATUS: .* processdeps=(\S+)$", result.stderr, re.M))
    deps = {proc: set(value.split(",")) for proc, value in deps.items()}
    assert deps == {
        # A process never depends on itself
        "w2": {"none"},
        "w": {"afterok:w2"},
        # A path written by two processes gives a dependency on each, and a
        # fifo none
        "r": {"afterok:w", "afterok:w2"},
        "f": {"none"},
        # The option dependency method gives after on a fifo
        "g": {"after:f"},
        "a": {"none"},
        # Another index of an array gives afterok, the same index of an
        # option generator aftercorr
        "b": {"afterok:a"},
        "c": {"aftercorr:a"},
    }


def test_the_oneshot_mode_refuses_a_dependency_that_waits_for_a_process_to_end_and_launches_nothing(tmp_path):
    outdir = tmp_path / "out"

    result = run_exec(
        "--pfile", str(FILE_EXAMPLE), "--outdir", str(outdir), "-s", "hi", "--builtinsched-oneshot"
    )
    assert result.returncode == 1
    assert 'process "file_reader" has a "afterok" dependency' in result.stderr
    execdir = outdir / "__exec__"
    assert not (execdir / "file_writer" / "file_writer").exists()
    assert not (execdir / "file_reader" / "file_reader").exists()


# An array of four tasks, each recording when it starts and when it ends,
# in nanoseconds, in a file of its own under the directory -t
TIMED_ARRAY_MODULE = """\
timed_explain_opts()
{
    explain_opt "-t" "<dir>" "Directory of the times of the tasks"
    explain_opt "-idx" "<int>" "Index of the task"
}

timed_identify_cmdline_opts()
{
    opt_is_cmdline "-t"
}

timed_define_opts()
{
    local cmdline=$1
    local i
    for i in 0 1 2 3; do
        local optlist=""
        define_cmdline_opt "${cmdline}" "-t" optlist || return 1
        define_opt "-idx" "${i}" optlist || return 1
        save_opt_list optlist
    done
}

timed()
{
    local t=$(read_opt_value_from_func_args "-t" "$@")
    local idx=$(read_opt_value_from_func_args "-idx" "$@")
    local start=$(python3 -c 'import time; print(time.time_ns())')
    sleep 1
    echo "${start} $(python3 -c 'import time; print(time.time_ns())')" > "${t}/${idx}"
}

debasher_timed_program()
{
    add_debasher_process "timed" "cpus=1 mem=32 time=00:01:00THROTTLE"
}
"""


def _timed_array(tmp_path, throttle=""):
    pfile = tmp_path / "debasher_timed.sh"
    pfile.write_text(TIMED_ARRAY_MODULE.replace("THROTTLE", throttle))
    times = tmp_path / "times"
    times.mkdir()
    return pfile, times


def test_the_oneshot_mode_refuses_an_array_whose_tasks_do_not_all_fit_and_launches_nothing(tmp_path):
    pfile, times = _timed_array(tmp_path)
    outdir = tmp_path / "out"
    result = run_exec(
        "--pfile", str(pfile), "--outdir", str(outdir), "-t", str(times),
        "--builtinsched-cpus", "2", "--builtinsched-oneshot",
    )
    assert result.returncode == 1
    assert "need 4 cpus together and the budget has 2" in result.stderr
    assert not list((outdir / "__exec__" / "timed").glob("*.id"))


def test_the_oneshot_mode_refuses_a_process_that_would_not_fit_in_a_later_round_and_launches_nothing(tmp_path):
    # b, with after on a, becomes a candidate only once a has started, when
    # a holds the only cpu of the budget
    pfile = tmp_path / "debasher_later.sh"
    pfile.write_text(explicit_chain_module("debasher_later", "a|0|", "b|0|after:a"))
    outdir = tmp_path / "out"
    result = run_exec(
        "--pfile", str(pfile), "--outdir", str(outdir), "--builtinsched-cpus", "1", "--builtinsched-oneshot"
    )
    assert result.returncode == 1
    assert "need 2 cpus together and the budget has 1" in result.stderr
    assert not (outdir / "__exec__" / "a" / "a.id").exists()


@pytest.mark.parametrize(
    ("spec", "extra"), [(" throttle=2", []), ("", ["--dflt-throttle", "2"])], ids=["own", "default"]
)
def test_the_oneshot_mode_refuses_a_throttle_smaller_than_the_number_of_tasks(tmp_path, spec, extra):
    # The throttle of the process, or the default one of debasher_exec
    pfile, times = _timed_array(tmp_path, spec)
    outdir = tmp_path / "out"
    result = run_exec(
        "--pfile", str(pfile), "--outdir", str(outdir), "-t", str(times), "--builtinsched-oneshot", *extra
    )
    assert result.returncode == 1
    assert 'process "timed" has 4 tasks and a throttle of 2' in result.stderr
    assert not (outdir / "__exec__" / "timed" / "timed").exists()


def test_the_built_in_scheduler_never_runs_more_tasks_at_once_than_its_cpus_allow(tmp_path):
    pfile, times = _timed_array(tmp_path)
    outdir = tmp_path / "out"
    result = run_exec(
        "--pfile", str(pfile), "--outdir", str(outdir), "-t", str(times), "--builtinsched-cpus", "2"
    )
    assert result.returncode == 0, result.stderr

    intervals = [tuple(map(int, (times / str(i)).read_text().split())) for i in range(4)]
    for start, _ in intervals:
        running = sum(1 for s, e in intervals if s <= start < e)
        assert running <= 2


# Processes that exchange nothing, each with the exit status and the
# processdeps given, as "<name>|<status>|<processdeps>"
def explicit_chain_module(name, *processes):
    lines = []
    adds = []
    for entry in processes:
        proc, status, deps = entry.split("|")
        lines.append(f"{proc}_explain_opts()\n{{\n    :\n}}\n")
        lines.append(f"{proc}_define_opts()\n{{\n    local optlist=\"\"\n    save_opt_list optlist\n}}\n")
        lines.append(f"{proc}()\n{{\n    return {status}\n}}\n")
        specs = f' "processdeps={deps}"' if deps else ""
        adds.append(f'    add_debasher_process "{proc}" "cpus=1 mem=32 time=00:01:00"{specs}')
    return "\n".join(lines) + f"\n{name}_program()\n{{\n" + "\n".join(adds) + "\n}\n"


def test_a_task_whose_dependency_can_no_longer_hold_is_cancelled_with_its_cause_and_afterany_on_it_holds(tmp_path):
    pfile = tmp_path / "debasher_cancelchain.sh"
    pfile.write_text(explicit_chain_module("debasher_cancelchain", "p|1|", "c|0|afterok:p", "d|0|afterany:c"))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert "PROCESS: c (TASK_IDX: 0) ; CANCELLED: afterok:p" in result.stderr, result.stderr

    execdir = outdir / "__exec__"
    assert (execdir / "c" / "c.cancelled").read_text().strip() == "Cancelled task idx: 0 ; Total: 1 ; Cause: afterok:p"
    assert not (execdir / "c" / "c.id").exists()
    assert (execdir / "d" / "d.finished").exists()
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: p ; STATUS: UNFINISHED" in status
    assert "PROCESS: c ; STATUS: UNFINISHED" in status
    assert "PROCESS: d ; STATUS: FINISHED" in status


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_process_whose_dependency_on_a_process_not_launched_can_no_longer_hold_is_not_submitted_nor_its_dependent(tmp_path):
    pfile = tmp_path / "debasher_notsubmitted.sh"
    outdir = tmp_path / "out"

    # x finishes in a first run
    pfile.write_text(explicit_chain_module("debasher_notsubmitted", "x|0|"))
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir), "--wait")
    assert result.returncode == 0, result.stderr

    # In the second, x is not launched again, so afternotok on it can no
    # longer hold, nor afterok or afterany on q, which does not end in the
    # run
    pfile.write_text(
        explicit_chain_module(
            "debasher_notsubmitted", "x|0|", "q|0|afternotok:x", "z|0|afterok:q", "y|0|afterany:q"
        )
    )
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir), "--wait")
    assert "Process q is not launched: its dependencies (afternotok:x) cannot hold in this run" in result.stderr
    assert "Process z is not launched: its dependencies (afterok:q) cannot hold in this run" in result.stderr
    assert "Process y is not launched: its dependencies (afterany:q) cannot hold in this run" in result.stderr
    execdir = outdir / "__exec__"
    assert not (execdir / "q" / "q.id").exists()
    assert not (execdir / "z" / "z.id").exists()
    assert not (execdir / "y" / "y.id").exists()


# p has two attempts, and fails the first -fail of them, counting them in a
# file of the directory -t; q, with afterok on p, leaves a trace there
ATTEMPTS_MODULE = """\
p_explain_opts()
{
    explain_opt "-t" "<dir>" "Directory of the traces"
    explain_opt "-fail" "<int>" "Number of attempts that fail"
}

p_identify_cmdline_opts()
{
    opt_is_cmdline "-t"
    opt_is_cmdline "-fail"
}

p_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-t" optlist || return 1
    define_cmdline_opt "${cmdline}" "-fail" optlist || return 1
    save_opt_list optlist
}

p()
{
    local t=$(read_opt_value_from_func_args "-t" "$@")
    local fail=$(read_opt_value_from_func_args "-fail" "$@")
    local n=$(( $(cat "${t}/p_attempts" 2> /dev/null || echo 0) + 1 ))
    echo "${n}" > "${t}/p_attempts"
    [ "${n}" -gt "${fail}" ]
}

q_explain_opts()
{
    explain_opt "-t" "<dir>" "Directory of the traces"
}

q_identify_cmdline_opts()
{
    opt_is_cmdline "-t"
}

q_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-t" optlist || return 1
    save_opt_list optlist
}

q()
{
    local t=$(read_opt_value_from_func_args "-t" "$@")
    touch "${t}/q_ran"
}

debasher_attempts_program()
{
    add_debasher_process "p" "cpus=1 mem=32 time=00:01:00,00:02:00"
    add_debasher_process "q" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:p"
}
"""


def _run_attempts(tmp_path, fail):
    pfile = tmp_path / "debasher_attempts.sh"
    pfile.write_text(ATTEMPTS_MODULE)
    outdir = tmp_path / "out"
    traces = tmp_path / "traces"
    traces.mkdir()
    result = run_exec_with_sched(
        "SLURM", "--pfile", str(pfile), "--outdir", str(outdir), "-t", str(traces), "-fail", str(fail), "--wait"
    )
    # Every attempt failing leaves p and q unfinished, which the status says
    assert result.returncode == (3 if fail >= 2 else 0), result.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    return traces, status


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_task_whose_first_attempt_fails_runs_again_and_its_dependent_runs(tmp_path):
    traces, status = _run_attempts(tmp_path, 1)
    assert (traces / "p_attempts").read_text() == "2\n"
    assert "PROCESS: p ; STATUS: FINISHED" in status
    assert "PROCESS: q ; STATUS: FINISHED" in status
    assert (traces / "q_ran").exists()


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_task_whose_every_attempt_fails_does_not_finish_nor_its_dependent(tmp_path):
    traces, status = _run_attempts(tmp_path, 2)
    assert (traces / "p_attempts").read_text() == "2\n"
    assert "PROCESS: p ; STATUS: FINISHED" not in status
    assert "PROCESS: q ; STATUS: FINISHED" not in status
    assert not (traces / "q_ran").exists()


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_list_of_dependencies_joined_by_a_question_mark_with_more_than_one_attempt_is_refused(tmp_path):
    pfile = tmp_path / "debasher_attempts.sh"
    pfile.write_text(
        ATTEMPTS_MODULE.replace(
            '"cpus=1 mem=32 time=00:01:00" "processdeps=afterok:p"',
            '"cpus=1 mem=32 time=00:01:00,00:02:00" "processdeps=afterany:p?afternotok:p"',
        )
    )
    outdir = tmp_path / "out"
    args = ["--pfile", str(pfile), "--outdir", str(outdir), "-t", str(tmp_path), "-fail", "0", "--validate"]
    result = run_exec_with_sched("SLURM", *args)
    assert result.returncode == 1
    assert 'process q has a list of dependencies joined by "?"' in result.stderr

    # The built-in scheduler takes the first value of mem and time only
    result = run_exec_with_sched("BUILTIN", *args)
    assert result.returncode == 0, result.stderr


# o declares a FIFO that no process of the program reads, and finishes
# without opening it
EXTERNAL_FIFO_MODULE = """\
o_explain_opts()
{
    explain_opt "-outf" "<fifo>" "A FIFO for someone outside the program"
}

o_define_opts()
{
    local optlist=""
    define_fifo_opt "-outf" "o_fifo" optlist || return 1
    save_opt_list optlist
}

o()
{
    :
}

debasher_extfifo_program()
{
    add_debasher_process "o" "cpus=1 mem=32 time=00:01:00"
}
"""


def _rerun_list(stderr):
    """The processes that debasher_exec prints as marked to rerun."""
    if "Printing list of processes to rerun..." not in stderr:
        return []
    return stderr.split("Printing list of processes to rerun...")[1].split("\n")[1].split(",")


def test_the_owner_of_a_fifo_with_an_external_end_runs_again_on_every_run(tmp_path):
    pfile = tmp_path / "debasher_extfifo.sh"
    pfile.write_text(EXTERNAL_FIFO_MODULE)
    outdir = tmp_path / "out"
    for _ in range(2):
        result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
        assert result.returncode == 0, result.stderr
    # The owner, and only it: the external end is not a process
    assert _rerun_list(result.stderr) == ["o"]
    assert "PROCESS: o ; STATUS: FINISHED" in run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout


# slow writes -s into its output directory after sleeping -z seconds
SLOW_MODULE = """\
slow_explain_opts()
{
    explain_opt "-s" "<string>" "The value written"
    explain_opt "-z" "<int>" "Seconds to sleep"
}

slow_identify_cmdline_opts()
{
    opt_is_cmdline "-s"
    opt_is_cmdline "-z"
}

slow_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-s" optlist || return 1
    define_cmdline_opt "${cmdline}" "-z" optlist || return 1
    save_opt_list optlist
}

slow()
{
    local s=$(read_opt_value_from_func_args "-s" "$@")
    local z=$(read_opt_value_from_func_args "-z" "$@")
    sleep "${z}"
    echo "${s}"
}

debasher_slow_program()
{
    add_debasher_process "slow" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_run_stopped_before_its_end_leaves_the_old_options_of_the_run_before(tmp_path):
    pfile = tmp_path / "debasher_slow.sh"
    pfile.write_text(SLOW_MODULE)
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "first", "-z", "0")
    assert result.returncode == 0, result.stderr
    old_opts = outdir / "program.opts_old"
    assert "first" in old_opts.read_text()

    # A second run, with other options, is stopped while slow runs
    run = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "-s", "second", "-z", "60",
         "--sched", "BUILTIN"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until(
            lambda: "STATUS: IN-PROGRESS" in run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
        )
        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
        assert stop.returncode == 0, stop.stdout + stop.stderr
        run.wait(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()
    assert "first" in old_opts.read_text()
    assert "second" not in old_opts.read_text()

    # The next run still finds that the options changed
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-s", "second", "-z", "0")
    assert result.returncode == 0, result.stderr
    assert "slow" in _rerun_list(result.stderr)
    assert "second" in old_opts.read_text()


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_process_marked_for_an_unfinished_producer_that_is_not_submitted_waits_for_a_later_run(tmp_path):
    pfile = tmp_path / "debasher_prod.sh"
    outdir = tmp_path / "out"

    # x finishes, p fails and c, with afterany on p, finishes
    pfile.write_text(explicit_chain_module("debasher_prod", "x|0|", "p|1|", "c|0|afterany:p"))
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir), "--wait")
    assert result.returncode == 3, result.stderr
    assert "PROCESS: c ; STATUS: FINISHED" in run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout

    # p now has afternotok on x, which finished in the earlier run and can
    # no longer fail: p is not submitted, and c, marked since p has not
    # finished, loses its completion marker and is not submitted either
    pfile.write_text(explicit_chain_module("debasher_prod", "x|0|", "p|1|afternotok:x", "c|0|afterany:p"))
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir), "--wait")
    assert _rerun_list(result.stderr) == ["c"]
    assert "Process p is not launched" in result.stderr
    assert "Process c is not launched" in result.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: x ; STATUS: FINISHED" in status
    assert "PROCESS: c ; STATUS: FINISHED" not in status
    assert not (outdir / "__exec__" / "c" / "c.finished").exists()


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
def test_debasher_exec_that_waits_for_its_run_ends_with_3_when_a_process_does_not_finish(tmp_path, sched):
    pfile = tmp_path / "debasher_status3.sh"
    extra = ["--wait"] if sched == "SLURM" else []

    pfile.write_text(explicit_chain_module("debasher_status3", "ok|0|", "bad|1|"))
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(tmp_path / "out1"), *extra)
    assert result.returncode == 3, result.stderr
    assert "Not every process of the program finished" in result.stderr

    pfile.write_text(explicit_chain_module("debasher_status3", "ok|0|"))
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(tmp_path / "out2"), *extra)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_debasher_exec_that_only_submits_to_slurm_ends_with_0_whatever_the_processes_do(tmp_path):
    pfile = tmp_path / "debasher_status3.sh"
    pfile.write_text(explicit_chain_module("debasher_status3", "bad|1|"))
    outdir = tmp_path / "out"
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert wait_until(lambda: "STATUS: UNFINISHED" in run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout, timeout=60)


@pytest.mark.parametrize(
    "specs, message",
    [
        ('"cpus=1 mem=32 time=00:01:00 thottle=2"', "has an unknown computational specification: thottle=2"),
        (
            '"cpus=1 mem=32 time=00:01:00 processdeps=afterany:a"',
            "processdeps is written among the computational specifications of process b",
        ),
    ],
)
def test_a_validation_refuses_an_attribute_that_the_engine_would_ignore(tmp_path, specs, message):
    pfile = tmp_path / "debasher_specs.sh"
    module = explicit_chain_module("debasher_specs", "a|0|", "b|0|")
    module = module.replace('add_debasher_process "b" "cpus=1 mem=32 time=00:01:00"', f'add_debasher_process "b" {specs}')
    pfile.write_text(module)
    result = run_exec("--pfile", str(pfile), "--outdir", str(tmp_path / "out"), "--validate")
    assert result.returncode == 1
    assert message in result.stderr


RESIDENT_EXAMPLE = REPO_ROOT / "data" / "webui_programs" / "webui_running_sum" / "webui_running_sum.sh"


def test_a_resident_program_runs_on_the_built_in_scheduler_in_oneshot_mode(tmp_path):
    result = run_exec("--pfile", str(RESIDENT_EXAMPLE), "--outdir", str(tmp_path / "out"), "--validate")
    assert "forcing the built-in scheduler in oneshot mode" in result.stderr


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_a_resident_program_refuses_the_slurm_scheduler(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec_with_sched("SLURM", "--pfile", str(RESIDENT_EXAMPLE), "--outdir", str(outdir), "--validate")
    assert result.returncode == 1
    assert "program only supports the built-in scheduler (requested: SLURM)" in result.stderr


CYCLE_EXAMPLE = REPO_ROOT / "data" / "programs" / "debasher_cycle.sh"

# An option dependency method that gives after to the fifo that a process
# of debasher_cycle.sh reads
CYCLE_AFTER = """
{proc}_define_opt_deps()
{{
    echo after
}}
"""


@pytest.mark.parametrize(
    "after_on,deps",
    [
        ((), {"process_a": "none", "process_b": "none"}),
        (("process_b",), {"process_a": "none", "process_b": "after:process_a"}),
        (("process_a", "process_b"), None),
    ],
    ids=["none", "after_on_one_link", "after_on_both_links"],
)
def test_a_loop_through_fifos_is_a_cycle_only_with_after_on_every_link(tmp_path, after_on, deps):
    pfile = tmp_path / CYCLE_EXAMPLE.name
    pfile.write_text(CYCLE_EXAMPLE.read_text() + "".join(CYCLE_AFTER.format(proc=p) for p in after_on))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-n", "3", "--validate")
    if deps is None:
        assert result.returncode == 1
        assert re.search(r"circular dependency detected at 'process_[ab]'", result.stderr), result.stderr
    else:
        assert result.returncode == 0, result.stderr
        found = dict(re.findall(r"^PROCESS: (\S+) ; STATUS: .* processdeps=(\S+)$", result.stderr, re.M))
        assert found == deps


# x and y each read a file of the other
FILE_CYCLE_MODULE = """\
x_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-inf" "<file>" "File of y"
}

x_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    define_opt_from_proc_out "-inf" "y" "-outf" optlist || return 1
    save_opt_list optlist
}

x()
{
    :
}

y_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-inf" "<file>" "File of x"
}

y_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    define_opt_from_proc_out "-inf" "x" "-outf" optlist || return 1
    save_opt_list optlist
}

y()
{
    :
}

debasher_filecycle_program()
{
    add_debasher_process "x" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "y" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_cycle_of_files_is_refused_naming_a_process_of_it(tmp_path):
    pfile = tmp_path / "debasher_filecycle.sh"
    pfile.write_text(FILE_CYCLE_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 1
    assert re.search(r"circular dependency detected at '[xy]'", result.stderr), result.stderr


# w writes the file <outdir>/w/data after a while and owns a fifo also
# named data, which it does not open; r reads the file
FIFO_FILE_CLASH_MODULE = """\
w_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
    explain_opt "-outfifo" "<fifo>" "Fifo named like the file"
}

w_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/data" optlist || return 1
    define_fifo_opt "-outfifo" "data" optlist || return 1
    save_opt_list optlist
}

w()
{
    sleep 2
    echo written > "$(read_opt_value_from_func_args "-outf" "$@")"
}

r_explain_opts()
{
    explain_opt "-inf" "<file>" "File of w"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "w" "-outf" optlist || return 1
    save_opt_list optlist
}

r()
{
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_fifofileclash_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "r" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_file_named_like_a_fifo_of_its_writer_is_read_as_a_file_after_the_writer_ends(tmp_path):
    pfile = tmp_path / "debasher_fifofileclash.sh"
    pfile.write_text(FIFO_FILE_CLASH_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert re.search(r"^PROCESS: r .*processdeps=afterok:w$", result.stderr, re.M), result.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert "PROCESS: w ; STATUS: FINISHED" in status.stdout, status.stdout
    assert "PROCESS: r ; STATUS: FINISHED" in status.stdout, status.stdout
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "r")
    assert stdout.stdout.strip() == "written", stdout.stdout + stdout.stderr


# ring is an array of two tasks: task 0 writes the fifo ring_0, which task 1
# reads; task 1 reads it whole and then fails while the file @@MARKER@@ is
# missing, which it creates
ARRAY_FIFO_RERUN_MODULE = """\
ring_explain_opts()
{
    explain_opt "-outf" "<fifo>" "Fifo of task 0"
    explain_opt "-inf" "<fifo>" "Fifo that task 1 reads"
}

ring_generate_opts_size()
{
    echo 2
}

ring_generate_opts()
{
    local task_idx=$5
    local optlist=""
    if [ "${task_idx}" -eq 0 ]; then
        define_fifo_opt "-outf" "ring_0" optlist || return 1
    else
        define_opt_from_proc_task_out "-inf" "ring" 0 "-outf" optlist || return 1
    fi
    save_opt_list optlist
}

ring()
{
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    if [ "${outf}" != "${DEBASHER_OPT_NOT_FOUND}" ]; then
        echo line > "${outf}"
        return 0
    fi
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
    if [ ! -f "@@MARKER@@" ]; then
        touch "@@MARKER@@"
        return 1
    fi
}

debasher_arrayfiforerun_program()
{
    add_debasher_process "ring" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_fifo_between_a_finished_task_and_a_failed_one_of_an_array_reruns_both_tasks(tmp_path):
    marker = tmp_path / "failed_once"
    pfile = tmp_path / "debasher_arrayfiforerun.sh"
    pfile.write_text(ARRAY_FIFO_RERUN_MODULE.replace("@@MARKER@@", str(marker)))
    outdir = tmp_path / "out"

    first = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert first.returncode != 0, first.stderr
    assert marker.exists()

    # Task 1 alone would block on opening the fifo, whose other end has
    # finished
    second = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert second.returncode == 0, second.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert "PROCESS: ring ; STATUS: FINISHED" in status.stdout, status.stdout


# w writes two lines into the fifo f, declared with @@MIRROR@@, and then
# runs @@END@@; r reads f. w runs on every run
MIRROR_MODULE = """\
w_explain_opts()
{
    explain_opt "-outf" "<fifo>" "Fifo that r reads"
}

w_define_opts()
{
    local optlist=""
    define_fifo_opt "-outf" "f" optlist @@MIRROR@@ || return 1
    save_opt_list optlist
}

w()
{
    # One open: with no mirror, a reader that reads until the end of the data
    # would end at the first close
    printf 'a\nb\n' > "$(read_opt_value_from_func_args "-outf" "$@")"
    @@END@@
}

r_explain_opts()
{
    explain_opt "-inf" "<fifo>" "Fifo of w"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "w" "-outf" optlist || return 1
    save_opt_list optlist
}

r()
{
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_mirror_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00" "force=yes"
    add_debasher_process "r" "cpus=1 mem=32 time=00:01:00"
}
"""

DEBASHER_GET_FIFO_MIRROR = REPO_ROOT / "bin" / "debasher_get_fifo_mirror"


def write_mirror_module(path, mirror="--mirror", end="return 0"):
    path.write_text(MIRROR_MODULE.replace("@@MIRROR@@", mirror).replace("@@END@@", end))


def test_a_mirrored_fifo_reaches_its_reader_and_its_mirror_log(tmp_path):
    pfile = tmp_path / "debasher_mirror.sh"
    write_mirror_module(pfile)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert result.returncode == 0, result.stderr
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "r")
    assert stdout.stdout.split() == ["a", "b"], stdout.stdout + stdout.stderr
    mirror = run_tool(DEBASHER_GET_FIFO_MIRROR, "-d", str(outdir), "-p", "w", "-f", "f")
    assert mirror.returncode == 0, mirror.stderr
    assert mirror.stdout.split() == ["a", "b"]


def test_the_reader_of_a_mirrored_fifo_ends_when_its_writer_exits_without_returning(tmp_path):
    pfile = tmp_path / "debasher_mirror.sh"
    write_mirror_module(pfile, end="exit 1")
    outdir = tmp_path / "out"

    # The mirror tap ends with the task of w, so r sees the end of the data
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert result.returncode != 0
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert "PROCESS: r ; STATUS: FINISHED" in status.stdout, status.stdout
    assert "PROCESS: w ; STATUS: UNFINISHED" in status.stdout, status.stdout
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "r")
    assert stdout.stdout.split() == ["a", "b"], stdout.stdout + stdout.stderr


def test_a_reader_of_a_mirrored_fifo_that_is_gone_does_not_keep_the_task_of_the_owner_from_ending(tmp_path):
    pfile = tmp_path / "debasher_mirror.sh"
    write_mirror_module(pfile)
    # The owner writes less than the shim holds, so that its process function
    # returns, and the reader takes one line and goes: the mirror tap gives
    # the rest up instead of keeping the task waiting, and every line still
    # reaches the mirror log. An owner that writes more than the shim holds
    # after its reader is gone stays blocked (see "Mirror taps")
    module = pfile.read_text()
    module = module.replace("printf 'a\nb\n' >", "seq 1 1000 >")
    module = module.replace('cat "$(read_opt_value_from_func_args "-inf"', 'head -n 1 "$(read_opt_value_from_func_args "-inf"')
    assert "seq 1 1000 >" in module and "head -n 1" in module
    pfile.write_text(module)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=120)
    assert result.returncode == 0, result.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir))
    assert "PROCESS: w ; STATUS: FINISHED" in status.stdout, status.stdout
    assert "PROCESS: r ; STATUS: FINISHED" in status.stdout, status.stdout
    mirror = run_tool(DEBASHER_GET_FIFO_MIRROR, "-d", str(outdir), "-p", "w", "-f", "f")
    assert len(mirror.stdout.split()) == 1000


def test_a_fifo_no_longer_declared_with_mirror_is_not_mirrored_in_the_next_run(tmp_path):
    pfile = tmp_path / "debasher_mirror.sh"
    write_mirror_module(pfile)
    outdir = tmp_path / "out"
    assert run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60).returncode == 0

    # w has force=yes, so it runs again, and r with it
    write_mirror_module(pfile, mirror="")
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert result.returncode == 0, result.stderr
    mirror = run_tool(DEBASHER_GET_FIFO_MIRROR, "-d", str(outdir), "-p", "w", "-f", "f")
    assert mirror.returncode != 0
    assert "could not be found" in mirror.stderr


# r reads a file of w, and its option dependency method answers with a
# type that does not exist; @@SPECS@@ is the processdeps of r
EXPLICIT_DEPS_MODULE = """\
w_explain_opts()
{
    explain_opt "-outf" "<file>" "Output file"
}

w_define_opts()
{
    local process_outdir=$4
    local optlist=""
    define_opt "-outf" "${process_outdir}/f" optlist || return 1
    save_opt_list optlist
}

w()
{
    echo f > "$(read_opt_value_from_func_args "-outf" "$@")"
}

r_explain_opts()
{
    explain_opt "-inf" "<file>" "File of w"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_out "-inf" "w" "-outf" optlist || return 1
    save_opt_list optlist
}

r_define_opt_deps()
{
    echo afterbogus
}

r()
{
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_explicitdeps_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "r" "cpus=1 mem=32 time=00:01:00" "@@SPECS@@"
}
"""


def test_explicit_dependencies_take_a_process_out_of_the_inference(tmp_path):
    pfile = tmp_path / "debasher_explicitdeps.sh"
    outdir = tmp_path / "out"

    # Inferred, the type of the option dependency method is refused
    pfile.write_text(EXPLICIT_DEPS_MODULE.replace(' "@@SPECS@@"', ""))
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 1
    assert "unknown process dependency type: afterbogus" in result.stderr

    # With processdeps, the method is never called and nothing is inferred
    pfile.write_text(EXPLICIT_DEPS_MODULE.replace("@@SPECS@@", "processdeps=none"))
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 0, result.stderr
    deps = dict(re.findall(r"^PROCESS: (\S+) ; STATUS: .* processdeps=(\S+)$", result.stderr, re.M))
    assert deps == {"w": "none", "r": "none"}


@pytest.mark.parametrize(
    "processdeps,error",
    [
        ("afterok:w,", "Error: the dependencies of process r (afterok:w,) have an empty element"),
        (
            "afterok:w,afternotok:w",
            "Error: the dependencies of process r on w (afterok and afternotok, which all have to hold) cannot both be satisfied by any run of w",
        ),
    ],
)
def test_explicit_dependencies_are_refused_before_the_dependency_graph_is_drawn(tmp_path, processdeps, error):
    pfile = tmp_path / "debasher_explicitdeps.sh"
    pfile.write_text(EXPLICIT_DEPS_MODULE.replace("@@SPECS@@", f"processdeps={processdeps}"))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "--validate")
    assert result.returncode == 1
    assert error in result.stderr
    assert "incorrect definition of process dependency" not in result.stderr


# Two processes, each with a shared subdirectory of "data"
SHARED_LEFT_MODULE = """\
debasher_shleft_shared_dirs()
{
    define_shared_dir "data"
}

a_explain_opts()
{
    explain_opt "-outd" "<dir>" "Shared subdirectory"
}

a_define_opts()
{
    local optlist=""
    define_opt_from_shared_dir "-outd" "data" optlist --subdir "a" || return 1
    save_opt_list optlist
}

a()
{
    echo a > "$(read_opt_value_from_func_args "-outd" "$@")/f"
}

b_explain_opts()
{
    explain_opt "-outd" "<dir>" "Shared subdirectory"
}

b_define_opts()
{
    local optlist=""
    define_opt_from_shared_dir "-outd" "data" optlist --subdir "b" || return 1
    save_opt_list optlist
}

b()
{
    echo b > "$(read_opt_value_from_func_args "-outd" "$@")/f"
}

debasher_shleft_program()
{
    add_debasher_process "a" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "b" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_process_that_left_the_program_loses_its_shared_subdirectory_and_a_finished_one_keeps_its_own(tmp_path):
    pfile = tmp_path / "debasher_shleft.sh"
    pfile.write_text(SHARED_LEFT_MODULE)
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    kept = outdir / "data" / "a" / "f"
    before = kept.stat().st_mtime_ns

    pfile.write_text(SHARED_LEFT_MODULE.replace('    add_debasher_process "b" "cpus=1 mem=32 time=00:01:00"\n', ""))
    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    assert not (outdir / "data" / "b").exists()
    assert f"Removing {outdir}/data/b, which no option asks for" in result.stderr
    assert kept.read_text() == "a\n"
    assert kept.stat().st_mtime_ns == before


# An array of two tasks, each with a task subdirectory where it writes the
# value of -x; task 1 is skipped when -x is "b". The options come from
# _define_opts, or from an option generator
TASK_SUBDIR_MODULE = """\
ts_explain_opts()
{
    explain_opt "-x" "<string>" "The value that each task writes"
    explain_opt "-idx" "<int>" "Index of the task"
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

ts_identify_cmdline_opts()
{
    opt_is_cmdline "-x"
}

ts_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_cmdline_opt "$1" "-x" optlist || return 1
        define_opt "-idx" "${i}" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}

ts_skip()
{
    [ "$(read_opt_value_from_func_args "-idx" "$@")" = "1" ] && [ "$(read_opt_value_from_func_args "-x" "$@")" = "b" ]
}

ts()
{
    echo "$(read_opt_value_from_func_args "-x" "$@")" > "$(read_opt_value_from_func_args "-outd" "$@")/out"
}

debasher_tsub_program()
{
    add_debasher_process "ts" "cpus=1 mem=32 time=00:01:00"
}
"""

TASK_SUBDIR_GEN_MODULE = TASK_SUBDIR_MODULE.replace(
    """ts_define_opts()
{
    local i
    for i in 0 1; do
        local optlist=""
        define_cmdline_opt "$1" "-x" optlist || return 1
        define_opt "-idx" "${i}" optlist || return 1
        define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
        save_opt_list optlist
    done
}""",
    """ts_generate_opts_size()
{
    echo 2
}

ts_generate_opts()
{
    local i=$5
    local optlist=""
    define_cmdline_opt "$1" "-x" optlist || return 1
    define_opt "-idx" "${i}" optlist || return 1
    define_opt_from_process_outdir "-outd" optlist --subdir "${i}" || return 1
    save_opt_list optlist
}""",
)


@pytest.mark.parametrize("module", [TASK_SUBDIR_MODULE, TASK_SUBDIR_GEN_MODULE], ids=["define_opts", "generator"])
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
def test_a_task_empties_its_task_subdirectories_and_a_skipped_one_finds_them_as_prepared(tmp_path, sched, module):
    pfile = tmp_path / "debasher_tsub.sh"
    pfile.write_text(module)
    outdir = tmp_path / "out"
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), "-x", "a", *extra)
    assert result.returncode == 0, result.stderr

    # What a task left in its task subdirectory after the first run
    for i in range(2):
        (outdir / "ts" / str(i) / "stale").write_text("")

    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), "-x", "b", *extra)
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (outdir / "ts" / "0").iterdir()) == ["out"]
    assert (outdir / "ts" / "0" / "out").read_text() == "b\n"
    assert sorted(p.name for p in (outdir / "ts" / "1").iterdir()) == ["out", "stale"]
    assert (outdir / "ts" / "1" / "out").read_text() == "a\n"


# An array of two tasks that write the value of -x into the process
# output directory
OUTDIR_ARRAY_MODULE = """\
oa_explain_opts()
{
    explain_opt "-x" "<string>" "The value that each task writes"
    explain_opt "-outf" "<file>" "What the task writes"
}

oa_identify_cmdline_opts()
{
    opt_is_cmdline "-x"
}

oa_define_opts()
{
    local process_outdir=$4
    local i
    for i in 0 1; do
        local optlist=""
        define_cmdline_opt "$1" "-x" optlist || return 1
        define_opt "-outf" "${process_outdir}/${i}.txt" optlist || return 1
        save_opt_list optlist
    done
}

oa()
{
    echo "$(read_opt_value_from_func_args "-x" "$@")" > "$(read_opt_value_from_func_args "-outf" "$@")"
}

debasher_outdarray_program()
{
    add_debasher_process "oa" "cpus=1 mem=32 time=00:01:00"
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
def test_a_process_output_directory_removed_after_a_run_is_created_again(tmp_path, sched):
    pfile = tmp_path / "debasher_outdarray.sh"
    pfile.write_text(OUTDIR_ARRAY_MODULE)
    outdir = tmp_path / "out"
    extra = ["--wait"] if sched == "SLURM" else []
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), "-x", "a", *extra)
    assert result.returncode == 0, result.stderr

    shutil.rmtree(outdir / "oa")
    result = run_exec_with_sched(sched, "--pfile", str(pfile), "--outdir", str(outdir), "-x", "b", *extra)
    assert result.returncode == 0, result.stderr
    for i in range(2):
        assert (outdir / "oa" / f"{i}.txt").read_text() == "b\n"


# --- the rules of the ends of a FIFO in real runs ---------------------------

def fifo_rules_module(name, *processes):
    """
    A module named `name` with the processes given as (process, cpus,
    option definitions, body) tuples: each option definition is a line of
    its _define_opts method, in which $process_outdir is available, and the
    body is that of its process function, in which opt <option> prints the
    value of an option. A process with a method named <process>_post in
    `body` after a line "---" gets it as well.
    """
    lines = ["opt() { read_opt_value_from_func_args \"$1\" \"${ARGS[@]}\"; }\n"]
    adds = []
    for proc, cpus, defines, body in processes:
        body, _, post = body.partition("---")
        define_lines = "\n".join(
            f"    {line if line.endswith(' optlist') else line + ' optlist'} || return 1" for line in defines
        )
        explains = "\n".join(f'    explain_opt "{line.split()[1].strip(chr(34))}" "<value>" "Option"' for line in defines)
        lines.append(f"{proc}_explain_opts()\n{{\n    :\n{explains}\n}}\n")
        lines.append(
            f"{proc}_define_opts()\n{{\n    local process_outdir=$4\n    local optlist=\"\"\n"
            f"{define_lines}\n    save_opt_list optlist\n}}\n"
        )
        lines.append(f"{proc}()\n{{\n    ARGS=(\"$@\")\n{body}\n}}\n")
        if post.strip():
            lines.append(f"{proc}_post()\n{{\n    ARGS=(\"$@\")\n{post}\n}}\n")
        adds.append(f'    add_debasher_process "{proc}" "cpus={cpus} mem=32 time=00:01:00"')
    return "\n".join(lines) + f"\n{name}_program()\n{{\n" + "\n".join(adds) + "\n}\n"


def test_an_end_of_a_fifo_waits_while_its_other_end_waits_for_a_process_to_end(tmp_path):
    # x takes the two CPUs; r reads a file of x and the fifo of w. Launched
    # with x, w would hold a CPU that x needs, waiting for r, which waits for
    # x: w is held back until x has ended
    pfile = tmp_path / "debasher_heldback.sh"
    pfile.write_text(fifo_rules_module(
        "debasher_heldback",
        ("x", 2, ['define_opt "-outf" "${process_outdir}/done"'], '    sleep 1; date +%s%N > "$(opt -outf)"'),
        ("w", 1, ['define_fifo_opt "-outf" "f" optlist', 'define_opt "-outts" "${process_outdir}/start"'],
         '    date +%s%N > "$(opt -outts)"; echo hi > "$(opt -outf)"'),
        ("r", 1, ['define_opt_from_proc_out "-inx" "x" "-outf" optlist',
                  'define_opt_from_proc_out "-inf" "w" "-outf" optlist'], '    cat "$(opt -inf)"'),
    ))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir),
                      "--builtinsched-cpus", "2", "--builtinsched-mem", "128", timeout=60)
    assert result.returncode == 0, result.stderr
    x_end = int((outdir / "x" / "done").read_text())
    w_start = int((outdir / "w" / "start").read_text())
    assert w_start >= x_end


def test_an_end_of_a_fifo_whose_other_end_is_cancelled_is_cancelled_with_its_cause(tmp_path):
    pfile = tmp_path / "debasher_endcancelled.sh"
    pfile.write_text(fifo_rules_module(
        "debasher_endcancelled",
        ("f", 1, ['define_opt "-outf" "${process_outdir}/out"'], '    return 1'),
        ("w", 1, ['define_fifo_opt "-outf" "f" optlist'], '    echo hi > "$(opt -outf)"'),
        ("r", 1, ['define_opt_from_proc_out "-inx" "f" "-outf" optlist',
                  'define_opt_from_proc_out "-inf" "w" "-outf" optlist'], '    cat "$(opt -inf)"'),
    ))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert result.returncode != 0
    cancelled = (outdir / "__exec__" / "w" / "w.cancelled").read_text()
    assert "Cause: fifo w/f (other end r, task 0, cancelled)" in cancelled, cancelled
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: w ; STATUS: UNFINISHED" in status
    assert "PROCESS: r ; STATUS: UNFINISHED" in status


def test_the_ends_of_a_chain_of_fifos_are_launched_together_under_a_cpu_limit(tmp_path):
    # With three CPUs, launching z and part of the chain a -> b -> c would
    # leave the rest of the chain without a CPU, and the run would not end
    pfile = tmp_path / "debasher_chain.sh"
    pfile.write_text(fifo_rules_module(
        "debasher_chain",
        ("z", 1, [], '    sleep 1'),
        ("a", 1, ['define_fifo_opt "-outf" "fa" optlist'], '    seq 1 3 > "$(opt -outf)"'),
        ("b", 1, ['define_opt_from_proc_out "-inf" "a" "-outf" optlist', 'define_fifo_opt "-outf" "fb" optlist'],
         '    cat "$(opt -inf)" > "$(opt -outf)"'),
        ("c", 1, ['define_opt_from_proc_out "-inf" "b" "-outf" optlist'], '    cat "$(opt -inf)"'),
    ))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir),
                      "--builtinsched-cpus", "3", "--builtinsched-mem", "128", timeout=60)
    assert result.returncode == 0, result.stderr
    stdout = run_tool(REPO_ROOT / "bin" / "debasher_get_stdout", "-d", str(outdir), "-p", "c")
    assert stdout.stdout.split() == ["1", "2", "3"]


def test_a_loop_through_fifos_with_after_on_one_link_runs_and_both_processes_finish(tmp_path):
    pfile = tmp_path / CYCLE_EXAMPLE.name
    pfile.write_text(CYCLE_EXAMPLE.read_text() + CYCLE_AFTER.format(proc="process_b"))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-n", "10", timeout=60)
    assert result.returncode == 0, result.stderr
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: process_a ; STATUS: FINISHED" in status
    assert "PROCESS: process_b ; STATUS: FINISHED" in status


def test_an_end_that_fails_before_opening_its_fifo_leaves_the_other_in_progress_until_debasher_stop(tmp_path):
    pfile = tmp_path / "debasher_oneend.sh"
    pfile.write_text(fifo_rules_module(
        "debasher_oneend",
        ("w", 1, ['define_fifo_opt "-outf" "f" optlist'], '    echo hi > "$(opt -outf)"'),
        ("r", 1, ['define_opt_from_proc_out "-inf" "w" "-outf" optlist'], '    return 1'),
    ))
    outdir = tmp_path / "out"

    run = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until(lambda: "PROCESS: r ; STATUS: UNFINISHED" in run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout)
        status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
        assert "PROCESS: w ; STATUS: IN-PROGRESS" in status, status
        assert run.poll() is None
        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
        assert stop.returncode == 0, stop.stdout + stop.stderr
        run.wait(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: w ; STATUS: UNFINISHED" in status, status


def test_a_writer_whose_shell_is_ended_by_sigpipe_is_unfinished_and_runs_no_post(tmp_path):
    # r reads one line and leaves; the shell of w writes, and SIGPIPE ends it
    pfile = tmp_path / "debasher_sigpipe.sh"
    pfile.write_text(fifo_rules_module(
        "debasher_sigpipe",
        ("w", 1, ['define_fifo_opt "-outf" "f" optlist', 'define_opt "-outpost" "${process_outdir}/post_ran"'],
         '    for (( i = 0; i < 1000000; i++ )); do echo "${i}"; done > "$(opt -outf)"\n'
         '---\n    touch "$(opt -outpost)"'),
        ("r", 1, ['define_opt_from_proc_out "-inf" "w" "-outf" optlist'], '    head -n 1 "$(opt -inf)"'),
    ))
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir), timeout=60)
    assert result.returncode != 0
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    assert "PROCESS: w ; STATUS: UNFINISHED" in status, status
    assert "PROCESS: r ; STATUS: FINISHED" in status, status
    assert not (outdir / "w" / "post_ran").exists()


DEBASHER_LAUNCH_PROCESS = REPO_ROOT / "libexec" / "debasher_launch_process"


def test_launch_process_refuses_a_process_that_is_not_in_the_run_and_writes_nothing(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr

    launch = run_tool(DEBASHER_LAUNCH_PROCESS, "-d", str(outdir), "-p", "nosuch")

    assert launch.returncode != 0
    assert "nosuch is not a process of the program" in launch.stderr
    assert not (outdir / "__exec__" / "nosuch").exists()


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_launch_process_refuses_a_run_of_the_slurm_scheduler(tmp_path):
    outdir = tmp_path / "out"
    result = run_exec_with_sched("SLURM", "--pfile", str(HELLO_WORLD), "--outdir", str(outdir), "--wait")
    assert result.returncode == 0, result.stderr
    id_file = outdir / "__exec__" / "hello_world" / "hello_world.id"
    job_id = id_file.read_text()

    launch = run_tool(DEBASHER_LAUNCH_PROCESS, "-d", str(outdir), "-p", "hello_world")

    assert launch.returncode != 0
    assert "launches a task of a run of the built-in scheduler only" in launch.stderr
    # The job id and the completion marker of the run are left as they were
    assert id_file.read_text() == job_id
    assert (outdir / "__exec__" / "hello_world" / "hello_world.finished").exists()


def sleeping_module(name, *processes):
    """A module whose processes, given as "name|seconds|processdeps", sleep
    for their seconds and then leave a trace in the directory that TRACES
    names."""
    lines = []
    adds = []
    for entry in processes:
        proc, secs, deps = entry.split("|")
        lines.append(f"{proc}_explain_opts()\n{{\n    :\n}}\n")
        lines.append(f"{proc}_define_opts()\n{{\n    local optlist=\"\"\n    save_opt_list optlist\n}}\n")
        lines.append(f"{proc}()\n{{\n    sleep {secs}\n    touch \"TRACES/{proc}\"\n}}\n")
        specs = f' "processdeps={deps}"' if deps else ""
        adds.append(f'    add_debasher_process "{proc}" "cpus=1 mem=32 time=00:05:00"{specs}')
    return "\n".join(lines) + f"\n{name}_program()\n{{\n" + "\n".join(adds) + "\n}\n"


def _status_of(outdir, process):
    status = run_tool(DEBASHER_STATUS, "-d", str(outdir)).stdout
    match = re.search(rf"^PROCESS: {re.escape(process)} ; STATUS: (\S+)", status, re.MULTILINE)
    return match.group(1) if match else None


# A process whose _define_opts sleeps, so that the first run of a directory
# stays in its preparation for a while, and whose function leaves a trace
SLOW_PREPARATION_MODULE = """\
slowprep_explain_opts()
{
    :
}

slowprep_define_opts()
{
    sleep 6
    local optlist=""
    save_opt_list optlist
}

slowprep()
{
    touch "__TRACE__"
}

debasher_slowprep_program()
{
    add_debasher_process "slowprep" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_debasher_stop_stops_the_first_run_of_a_directory_while_it_is_being_prepared(tmp_path):
    pfile = tmp_path / "debasher_slowprep.sh"
    trace = tmp_path / "ran"
    pfile.write_text(SLOW_PREPARATION_MODULE.replace("__TRACE__", str(trace)))
    outdir = tmp_path / "out"
    execution = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        # The lock is held, and the command line file of the run is not
        # written yet
        assert wait_until(lambda: (outdir / "lock").exists(), timeout=30)
        time.sleep(1)
        assert not (outdir / "command_line.sh").exists()

        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
        assert stop.returncode == 0, stop.stdout + stop.stderr
        assert "was being prepared: debasher_exec is stopped, and no process was launched" in stop.stderr
        execution.wait(timeout=60)
    finally:
        if execution.poll() is None:
            os.killpg(execution.pid, 9)

    # Nothing was launched, then or later
    time.sleep(7)
    assert not trace.exists()
    assert not list((outdir / "__exec__").glob("*/*.id"))


# An array of two tasks, each with a fifo of its own through -outf, and a
# reader of the fifo of the first task only
FIFOS_READ_BY_SOME_MODULE = """\
w_explain_opts()
{
    explain_opt "-outf" "<fifo>" "Fifo of the task"
}

w_define_opts()
{
    local task_idx
    for task_idx in 0 1; do
        local optlist=""
        define_fifo_opt "-outf" "f${task_idx}" optlist || return 1
        save_opt_list optlist
    done
}

w()
{
    echo hi > "$(read_opt_value_from_func_args "-outf" "$@")"
}

r_explain_opts()
{
    explain_opt "-inf" "<fifo>" "Fifo of the first task of w"
}

r_define_opts()
{
    local optlist=""
    define_opt_from_proc_task_out "-inf" "w" 0 "-outf" optlist || return 1
    save_opt_list optlist
}

r()
{
    cat "$(read_opt_value_from_func_args "-inf" "$@")"
}

debasher_someread_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "r" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_program_whose_fifos_of_one_option_are_read_for_some_tasks_only_is_refused(tmp_path):
    pfile = tmp_path / "debasher_someread.sh"
    pfile.write_text(FIFOS_READ_BY_SOME_MODULE)
    outdir = tmp_path / "out"

    result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 1
    assert "the fifos that process w defines through -outf are read inside the program for task 0 but not for task 1" in result.stderr
    assert not list((outdir / "__exec__").glob("*/*.id"))


# Two processes that count their runs, one of them forced
FORCED_MODULE = """\
forced_explain_opts()
{
    :
}

forced_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

forced()
{
    echo run >> "__DIR__/forced.count"
}

plain_explain_opts()
{
    :
}

plain_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

plain()
{
    echo run >> "__DIR__/plain.count"
}

debasher_forced_program()
{
    add_debasher_process "forced" "cpus=1 mem=32 time=00:01:00" "force=yes"
    add_debasher_process "plain" "cpus=1 mem=32 time=00:01:00"
}
"""


def test_a_forced_process_runs_again_in_every_run_and_a_finished_one_does_not(tmp_path):
    pfile = tmp_path / "debasher_forced.sh"
    pfile.write_text(FORCED_MODULE.replace("__DIR__", str(tmp_path)))
    outdir = tmp_path / "out"

    for _ in range(2):
        result = run_exec("--pfile", str(pfile), "--outdir", str(outdir))
        assert result.returncode == 0, result.stderr

    assert (tmp_path / "forced.count").read_text().count("run") == 2
    assert (tmp_path / "plain.count").read_text().count("run") == 1


def test_debasher_exec_warns_when_it_runs_the_builtin_scheduler_without_ps(tmp_path):
    # A PATH with every command of the system but ps
    nops = tmp_path / "nops"
    nops.mkdir()
    for directory in ("/usr/bin", "/bin", "/usr/local/bin"):
        if not os.path.isdir(directory):
            continue
        for entry in os.listdir(directory):
            link = nops / entry
            if entry != "ps" and not link.exists():
                link.symlink_to(os.path.join(directory, entry))
    assert not (nops / "ps").exists()
    warning = "Warning: ps not found"

    with_ps = run_exec("--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "with"))
    assert with_ps.returncode == 0, with_ps.stderr
    assert warning not in with_ps.stderr

    without_ps = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(HELLO_WORLD), "--outdir", str(tmp_path / "without"), "--sched", "BUILTIN"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(nops)},
    )
    assert without_ps.returncode == 0, without_ps.stderr
    assert warning in without_ps.stderr


def _many_processes_module(num, sleep_secs):
    procs = "".join(
        f"p{i}_explain_opts()\n{{\n    :\n}}\n\np{i}_define_opts()\n{{\n    local optlist=\"\"\n    save_opt_list optlist\n}}\n\n"
        f"p{i}()\n{{\n    sleep {sleep_secs}\n}}\n\n"
        for i in range(num)
    )
    adds = "".join(f'    add_debasher_process "p{i}" "cpus=1 mem=1 time=00:10:00"\n' for i in range(num))
    return procs + "debasher_many_program()\n{\n" + adds + "}\n"


def test_a_stop_while_the_builtin_scheduler_launches_leaves_no_task_half_launched(tmp_path):
    # Forty processes in rounds of ten: the stop falls after the first round
    # has started, while its tasks run and the next round waits for them
    pfile = tmp_path / "debasher_many.sh"
    pfile.write_text(_many_processes_module(40, 3))
    outdir = tmp_path / "out"
    execution = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN", "--builtinsched-cpus", "10"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert wait_until(lambda: any((outdir / "__exec__").glob("p*/p*.id")), timeout=120)
        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
        assert stop.returncode == 0, stop.stdout + stop.stderr
        execution.wait(timeout=60)
    finally:
        if execution.poll() is None:
            os.killpg(execution.pid, 9)

    # Every task launched has its id, so that the stop reached it; the stop
    # came between two rounds, and nothing of the run is left running
    launched = [d for d in (outdir / "__exec__").glob("p*") if (d / f"{d.name}.id").exists()]
    with_script = [d for d in (outdir / "__exec__").glob("p*") if (d / d.name).exists()]
    assert 0 < len(launched) < 40 and len(launched) % 10 == 0
    assert {d.name for d in with_script} <= {d.name for d in launched}
    alive = subprocess.run(["pgrep", "-f", str(outdir / "__exec__")], capture_output=True, text=True)
    assert alive.stdout == ""


def test_a_stopped_run_of_the_builtin_scheduler_launches_nothing_more(tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    pfile = tmp_path / "debasher_stopchain.sh"
    pfile.write_text(sleeping_module("debasher_stopchain", "first|60|", "second|0|afterok:first").replace("TRACES", str(traces)))
    outdir = tmp_path / "out"

    run = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until(lambda: _status_of(outdir, "first") == "IN-PROGRESS")
        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))
        assert stop.returncode == 0, stop.stdout + stop.stderr
        run.wait(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()

    # The process that waited for the stopped one was never launched
    assert _status_of(outdir, "first") == "UNFINISHED"
    assert _status_of(outdir, "second") == "TO-DO"
    assert not (outdir / "__exec__" / "second" / "second.id").exists()
    assert not (traces / "second").exists()


def test_stopping_one_process_of_a_general_program_lets_the_rest_finish(tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    pfile = tmp_path / "debasher_stopone.sh"
    pfile.write_text(sleeping_module("debasher_stopone", "long|60|", "short|3|").replace("TRACES", str(traces)))
    outdir = tmp_path / "out"

    run = subprocess.Popen(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until(lambda: _status_of(outdir, "long") == "IN-PROGRESS")
        stop = run_tool(DEBASHER_STOP, "-d", str(outdir), "-p", "long")
        assert stop.returncode == 0, stop.stdout + stop.stderr
        run.wait(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()

    assert _status_of(outdir, "long") == "UNFINISHED"
    assert not (traces / "long").exists()
    assert _status_of(outdir, "short") == "FINISHED"
    assert (traces / "short").exists()


def _slurm_job_is_queued(job_id):
    squeue = subprocess.run(["squeue", "-h", "-j", job_id, "-o", "%i"], capture_output=True, text=True)
    return job_id in squeue.stdout.split()


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_debasher_stop_ends_the_jobs_of_a_process_in_progress_under_slurm(tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    pfile = tmp_path / "debasher_stopslurm.sh"
    pfile.write_text(sleeping_module("debasher_stopslurm", "long|120|").replace("TRACES", str(traces)))
    outdir = tmp_path / "out"

    # Without --wait, debasher_exec submits the job and ends
    result = run_exec_with_sched("SLURM", "--pfile", str(pfile), "--outdir", str(outdir))
    assert result.returncode == 0, result.stderr
    job_id = (outdir / "__exec__" / "long" / "long.id").read_text().strip()
    try:
        assert wait_until(lambda: _status_of(outdir, "long") == "IN-PROGRESS", timeout=60)

        stop = run_tool(DEBASHER_STOP, "-d", str(outdir))

        assert stop.returncode == 0, stop.stdout + stop.stderr
        assert wait_until(lambda: not _slurm_job_is_queued(job_id), timeout=60)
    finally:
        subprocess.run(["scancel", job_id], capture_output=True)
    assert not (traces / "long").exists()


# A process that runs, as a step, a sequential process whose steps go to Slurm
SLURM_STEP_MODULE = """\
runner_explain_opts()
{
    :
}

runner_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

runner()
{
    seq_execute slurmstep
}

slurmstep()
{
    :
}

debasher_slurmstep_program()
{
    add_debasher_process "runner" "cpus=1 mem=32 time=00:01:00"
    add_debasher_seq_process "slurmstep" "" "sched=SLURM"
}
"""


def _path_without(tmp_path, *commands):
    """A directory that links every program of /usr/bin and /bin but the given
    ones, to stand for a PATH where they are not installed."""
    bindir = tmp_path / "bin_without"
    bindir.mkdir()
    for sysdir in ("/usr/bin", "/bin"):
        for entry in os.scandir(sysdir):
            target = bindir / entry.name
            if entry.name in commands or target.exists() or target.is_symlink():
                continue
            target.symlink_to(entry.path)
    return str(bindir)


def test_a_run_with_a_sequential_process_on_slurm_is_refused_without_srun_and_launches_nothing(tmp_path):
    pfile = tmp_path / "debasher_slurmstep.sh"
    pfile.write_text(SLURM_STEP_MODULE)
    outdir = tmp_path / "out"
    env = {**os.environ, "PATH": _path_without(tmp_path, "srun")}

    result = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", str(outdir), "--sched", "BUILTIN"],
        capture_output=True, text=True, env=env,
    )

    assert result.returncode != 0
    assert "sequential process slurmstep has sched=SLURM, but srun is not found" in result.stderr
    assert not (outdir / "__exec__" / "runner" / "runner.id").exists()


# A process that runs one step per file of the list -list, recording each
# step with a step marker in its task subdirectory, as
# debasher_dynamic_fanout_stepdone.sh does: work copies a file into the
# directory, leaves its name in TRACES/ran, and fails for a file next to
# which a <file>.fail exists. -v only changes the options of the run
STEP_MARKERS_MODULE = """\
steps_explain_opts()
{
    explain_opt "-list" "<file>" "Files to process, one per line"
    explain_opt "-v" "<int>" "A value that only changes the options"
    explain_opt "-outd" "<dir>" "Task subdirectory"
}

steps_identify_cmdline_opts()
{
    opt_is_cmdline "-list"
    opt_is_cmdline "-v"
}

steps_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-list" optlist || return 1
    define_cmdline_opt "${cmdline}" "-v" optlist || return 1
    define_opt_from_process_outdir "-outd" optlist --subdir 0 || return 1
    save_opt_list optlist
}

steps_reset_outfiles()
{
    # The step markers in the task subdirectory survive to the next run
    :
}

work()
{
    echo "$(basename "$1")" >> "TRACES/ran"
    [ -e "$1.fail" ] && return 1
    cp "$1" "$2"
}

steps()
{
    local list=$(read_opt_value_from_func_args "-list" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    local exit_code=0
    local filepath
    while IFS= read -r filepath; do
        local base=$(basename "${filepath}")
        local sum=$(cksum < "${filepath}" | awk '{print $1}')
        local stepid="${base}_${sum}"
        is_step_done "${outd}" "${stepid}" && continue
        unmark_steps "${outd}" "${base}_" || return 1
        if seq_execute work "${filepath}" "${outd}/${base}" < /dev/null; then
            mark_step_done "${outd}" "${stepid}" || return 1
        else
            exit_code=1
        fi
    done < "${list}"
    return "${exit_code}"
}

debasher_stepmarkers_program()
{
    add_debasher_process "steps" "cpus=1 mem=32 time=00:01:00"
    add_debasher_seq_process "work"
}
"""


def test_step_markers_skip_the_steps_that_finished_and_run_again_the_step_of_a_changed_input(tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (data / name).write_text(f"{name}\n")
    (data / "b.txt.fail").write_text("")
    listfile = tmp_path / "list"
    listfile.write_text("".join(f"{data / name}\n" for name in ("a.txt", "b.txt", "c.txt")))
    pfile = tmp_path / "debasher_stepmarkers.sh"
    pfile.write_text(STEP_MARKERS_MODULE.replace("TRACES", str(traces)))
    outdir = tmp_path / "out"
    taskdir = outdir / "steps" / "0"
    ran = traces / "ran"

    def run(value):
        return run_exec("--pfile", str(pfile), "--outdir", str(outdir), "-list", str(listfile), "-v", value)

    def markers(base):
        return sorted(p.name for p in taskdir.glob(f"DEBASHER_STEP_DONE_{base}_*"))

    # The step of b fails: the run does not finish, and a and c are marked
    result = run("1")
    assert result.returncode == 3, result.stderr
    assert ran.read_text().split() == ["a.txt", "b.txt", "c.txt"]
    assert markers("a.txt") and markers("c.txt") and not markers("b.txt")

    # The next run skips the steps that the markers record and runs b
    (data / "b.txt.fail").unlink()
    ran.unlink()
    result = run("1")
    assert result.returncode == 0, result.stderr
    assert ran.read_text().split() == ["b.txt"]
    assert (taskdir / "b.txt").read_text() == "b.txt\n"

    # With a changed input, a run that reruns the process runs only the step
    # of that input, and its old marker is gone
    old_a_marker = markers("a.txt")
    (data / "a.txt").write_text("changed\n")
    ran.unlink()
    result = run("2")
    assert result.returncode == 0, result.stderr
    assert ran.read_text().split() == ["a.txt"]
    assert (taskdir / "a.txt").read_text() == "changed\n"
    assert len(markers("a.txt")) == 1 and markers("a.txt") != old_a_marker
