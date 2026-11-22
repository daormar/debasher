"""
Tests of read_lengths.py, the process of webui_read_lengths, run with
debasher_test: the summary of a text file of read lengths, and of one
with no lengths.
"""

import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "read_lengths.py")


def summarize(tmp_path, text, *extra):
    infile = tmp_path / "reads.txt"
    infile.write_text(text)
    outsummary = tmp_path / "summary.json"
    subprocess.run([sys.executable, SCRIPT, "-infile", str(infile), "-outsummary", str(outsummary), *extra], check=True)
    return json.loads(outsummary.read_text())


def test_the_summary_of_a_text_file_of_lengths(tmp_path):
    summary = summarize(tmp_path, "300\n500\n4000\n8000\n")

    assert summary["format"] == "text"
    assert summary["count"] == 4
    assert summary["total_bases"] == 12800
    assert summary["median"] == 2250
    assert summary["n50"] == 8000
    assert summary["short_fraction"] == 0.5


def test_the_short_threshold_is_an_option(tmp_path):
    summary = summarize(tmp_path, "300\n500\n4000\n8000\n", "-short-bases", "5000")

    assert summary["short_fraction"] == 0.75


def test_lines_that_are_not_lengths_are_skipped(tmp_path):
    summary = summarize(tmp_path, "a line\n\n1200\n")

    assert summary["count"] == 1
    assert summary["median"] == 1200


def test_a_file_with_no_lengths_has_an_empty_summary(tmp_path):
    summary = summarize(tmp_path, "a line\n")

    assert summary["count"] == 0
    assert summary["median"] is None
    assert summary["short_fraction"] is None
