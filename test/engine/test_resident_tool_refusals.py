"""
Refusals of the tools for resident programs. Those that come before any
program is loaded need no program to run: each of those tests calls the
tool that make install puts under bin/ on a scratch output directory. The
refusal of a general program needs one run of it, a real run.
"""

import fcntl
import subprocess
from pathlib import Path

import pytest
from resident_run import DEBASHER_EXEC, real_run

REPO_ROOT = Path(__file__).resolve().parents[2]
BINDIR = REPO_ROOT / "bin"

pytestmark = pytest.mark.skipif(
    not (BINDIR / "debasher_reset_resident").exists(),
    reason="the tools are not installed under bin/ (make install)",
)


@pytest.fixture
def outdir(tmp_path):
    """An output directory with a command line file, as debasher_exec
    leaves it, and nothing else."""
    d = tmp_path / "out"
    d.mkdir()
    (d / "command_line.sh").write_text("")
    return d


def test_a_reset_is_refused_while_a_debasher_exec_holds_the_lock_for_a_run(outdir):
    lockfile = outdir / "lock"
    with open(lockfile, "w") as lock:
        # The process id of a debasher_exec, with no mark of a validation
        lock.write("12345\n")
        lock.flush()
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = subprocess.run(
            [str(BINDIR / "debasher_reset_resident"), "-d", str(outdir)],
            capture_output=True,
            text=True,
        )
    assert result.returncode == 1, result.stderr
    assert "a debasher_exec is preparing or running the program" in result.stderr


HELLO_WORLD = REPO_ROOT / "data" / "programs" / "debasher_hello_world.sh"


@real_run
@pytest.mark.parametrize(
    "tool, args",
    [
        ("debasher_stop_resident", []),
        ("debasher_snapshot_resident", []),
        ("debasher_reset_resident", []),
        ("debasher_inspect_resident", ["-p", "hello_world", "summary"]),
    ],
)
def test_a_tool_for_resident_programs_refuses_a_general_one(tmp_path, tool, args):
    outdir = tmp_path / "out"
    run = subprocess.run(
        [str(DEBASHER_EXEC), "--pfile", str(HELLO_WORLD), "--outdir", str(outdir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr

    result = subprocess.run([str(BINDIR / tool), "-d", str(outdir), *args], capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "is not a resident program" in result.stderr
