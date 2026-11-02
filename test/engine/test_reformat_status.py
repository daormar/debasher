"""Tests for engine/debasher_reformat_status.py, which turns what
debasher_status prints into one row with the status of each process."""

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "engine" / "debasher_reformat_status.py"

STATUS = (
    "PROCESS: a ; STATUS: FINISHED ; SCHED_IDS: 1\n"
    "\n"
    "PROCESS: b ; STATUS: TO-DO ; SCHED_IDS: \n"
    "* SUMMARY: num_processes= 2 ; finished= 1\n"
)


def _run(tmp_path, *args):
    status = tmp_path / "status.txt"
    status.write_text(STATUS)
    return subprocess.run(
        [sys.executable, str(TOOL), "-p", str(status), *args], capture_output=True, text=True
    )


def test_the_long_and_the_short_option_of_the_format_are_the_same(tmp_path):
    short = _run(tmp_path, "-f", "1", "-l", "10")
    long = _run(tmp_path, "--format=1", "-l", "10")
    assert short.returncode == 0, short.stderr
    assert long.returncode == 0, long.stderr
    assert long.stdout == short.stdout


def test_a_row_with_a_header_names_each_process_and_its_status_and_an_empty_line_is_skipped(tmp_path):
    result = _run(tmp_path, "-f", "1", "-l", "10")
    assert result.returncode == 0, result.stderr
    header, row = result.stdout.splitlines()
    assert header.split() == ["a", "b"]
    assert row.split() == ["FINISHED", "TO-DO"]


def test_a_row_without_a_header_gives_the_statuses_alone(tmp_path):
    result = _run(tmp_path, "-f", "2", "-l", "10")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["FINISHED", "TO-DO"]
