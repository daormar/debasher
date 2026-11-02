"""Tests for engine/debasher_compare_opts.py, which compares the program.opts
of two runs to decide which processes have to run again."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "debasher_compare_opts",
    Path(__file__).resolve().parents[2] / "engine" / "debasher_compare_opts.py",
)
compare_opts_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(compare_opts_mod)


def _array_line(name, num_tasks, listed=10):
    elems = " ||| ".join(f"-in /data/s{i}.txt" for i in range(min(num_tasks, listed)))
    ellipsis = " ..." if num_tasks > listed else ""
    return f"PROCESS: {name} ; NUM_TASKS: {num_tasks} ; OPTIONS: {elems}{ellipsis}\n"


def _compare(tmp_path, old_text, new_text):
    old = tmp_path / "program.opts_old"
    new = tmp_path / "program.opts"
    old.write_text(old_text)
    new.write_text(new_text)
    return compare_opts_mod.compare_opts(
        compare_opts_mod.parse_opts_file(str(old)),
        compare_opts_mod.parse_opts_file(str(new)),
    )


def test_an_array_that_grows_beyond_the_listed_tasks_is_changed(tmp_path):
    result = _compare(tmp_path, _array_line("worker", 12), _array_line("worker", 15))
    assert result["changed"] == ["worker"]


def test_an_array_with_the_same_number_of_tasks_and_listed_options_is_unchanged(tmp_path):
    result = _compare(tmp_path, _array_line("worker", 12), _array_line("worker", 12))
    assert result["unchanged"] == ["worker"]


def test_a_file_without_the_number_of_tasks_is_compared_by_its_listed_options(tmp_path):
    old = "PROCESS: single ; OPTIONS: -s hello\n"
    assert _compare(tmp_path, old, "PROCESS: single ; NUM_TASKS: 1 ; OPTIONS: -s hello\n")["unchanged"] == ["single"]
    assert _compare(tmp_path, old, "PROCESS: single ; NUM_TASKS: 1 ; OPTIONS: -s bye\n")["changed"] == ["single"]


def test_an_invalid_number_of_tasks_is_an_error(tmp_path):
    path = tmp_path / "program.opts"
    path.write_text("PROCESS: single ; NUM_TASKS: many ; OPTIONS: -s hello\n")
    with pytest.raises(compare_opts_mod.OptsParseError):
        compare_opts_mod.parse_opts_file(str(path))


def test_a_flag_and_an_option_with_an_empty_value_differ(tmp_path):
    flag = "PROCESS: p ; NUM_TASKS: 1 ; OPTIONS: -x\n"
    empty = "PROCESS: p ; NUM_TASKS: 1 ; OPTIONS: -x ''\n"
    assert _compare(tmp_path, flag, empty)["changed"] == ["p"]


def test_a_negative_number_is_a_value(tmp_path):
    path = tmp_path / "program.opts"
    path.write_text("PROCESS: p ; NUM_TASKS: 1 ; OPTIONS: -n -5 -f\n")
    opts = compare_opts_mod.parse_opts_file(str(path))
    assert opts["p"].instances == [{"-n": "-5", "-f": None}]


def test_a_process_with_no_options_is_read(tmp_path):
    old = "PROCESS: p ; OPTIONS: ''\n"
    new = "PROCESS: p ; NUM_TASKS: 1 ; OPTIONS: \n"
    assert _compare(tmp_path, old, new)["unchanged"] == ["p"]


# --- the command line, as debasher_exec runs it ---------------------------------

_OLD = "PROCESS: a ; NUM_TASKS: 1 ; OPTIONS: -x 1\nPROCESS: b ; NUM_TASKS: 1 ; OPTIONS: -x 1\nPROCESS: gone ; NUM_TASKS: 1 ; OPTIONS: -x 1\n"
_NEW = "PROCESS: a ; NUM_TASKS: 1 ; OPTIONS: -x 1\nPROCESS: b ; NUM_TASKS: 1 ; OPTIONS: -x 2\nPROCESS: c ; NUM_TASKS: 1 ; OPTIONS: -x 1\n"


def _main(monkeypatch, capsys, tmp_path, *flags, old_text=_OLD, new_text=_NEW):
    old = tmp_path / "program.opts_old"
    new = tmp_path / "program.opts"
    old.write_text(old_text)
    new.write_text(new_text)
    monkeypatch.setattr("sys.argv", ["debasher_compare_opts", *flags, str(old), str(new)])
    status = compare_opts_mod.main()
    out, err = capsys.readouterr()
    return status, out, err


@pytest.mark.parametrize(
    ("flags", "listed"),
    [
        (["--changed"], "b\n"),
        (["--new"], "c\n"),
        (["--removed"], "gone\n"),
        (["--unchanged"], "a\n"),
        ([], "b\nc\n"),
        (["--to-rerun"], "b\nc\n"),
    ],
)
def test_the_command_line_lists_the_processes_of_each_category(monkeypatch, capsys, tmp_path, flags, listed):
    status, out, err = _main(monkeypatch, capsys, tmp_path, *flags)
    assert status == 0
    assert out == listed
    assert err == ""


def test_the_command_line_prints_a_report_for_a_person(monkeypatch, capsys, tmp_path):
    status, out, _ = _main(monkeypatch, capsys, tmp_path, "--human")
    assert status == 0
    assert "Changed processes (parameters modified) (1):\n  - b\n" in out
    assert "New processes (1):\n  - c\n" in out


def test_the_command_line_ends_with_2_and_says_why_when_a_file_cannot_be_read(monkeypatch, capsys, tmp_path):
    status, out, err = _main(monkeypatch, capsys, tmp_path, "--changed", old_text="garbage line\n")
    assert status == 2
    assert out == ""
    assert err.startswith("error: ") and "malformed line" in err
