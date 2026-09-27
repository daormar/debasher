"""
Tests that run a general program for real with debasher_exec, as installed
under bin/ by make install, on the built-in scheduler. Like the tests of
resident programs, they are skipped unless DEBASHER_RUN_CHAOS_TEST is set.
"""

import fcntl
import os
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
