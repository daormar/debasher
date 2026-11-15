"""
Refusals of the tools for resident programs that come before any program
is loaded, so that no program has to run: each test calls the tool that
make install puts under bin/ on a scratch output directory.
"""

import fcntl
import subprocess
from pathlib import Path

import pytest

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
