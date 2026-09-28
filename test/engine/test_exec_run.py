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

from resident_run import DEBASHER_EXEC, REPO_ROOT, real_run

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
