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
