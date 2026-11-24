"""Tests for engine/debasher_check_prg_files.py, which checks the process
specification of a run and prints it reordered or as graphs."""

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "engine" / "debasher_check_prg_files.py"


def _run(tmp_path, *args):
    (tmp_path / "program.procspec").write_text(
        "writer cpus=1 mem=32 time=00:01:00\n"
        "reader cpus=1 mem=32 time=00:01:00 ||| processdeps=afterok:writer\n"
    )
    return subprocess.run(
        [sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=tmp_path
    )


def test_the_long_and_the_short_option_of_the_prefix_are_the_same(tmp_path):
    short = _run(tmp_path, "-p", "program", "-d")
    long = _run(tmp_path, "--prefix", "program", "-d")
    assert short.returncode == 0, short.stderr
    assert long.returncode == 0, long.stderr
    assert long.stdout == short.stdout
    assert "reader" in long.stdout
