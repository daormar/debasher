"""Tests for engine/debasher_run_py_func.py, which runs the Python function
of a process kept in a file of its own (tasks(run) of an array or an option
generator, skip(task) of the skip method) and prints what it returns in the
form that the functions of the engine read."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "engine" / "debasher_run_py_func.py"
_SPEC = importlib.util.spec_from_file_location("debasher_run_py_func", _TOOL)
run_py_func = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_py_func)


def _run(tmp_path, mode, code, *args, process="proc", outdir="/outd/proc", name="func.py"):
    path = tmp_path / name
    path.write_text(code)
    head = [mode, str(path), process] + ([] if mode == "skip" else [outdir])
    return subprocess.run(
        [sys.executable, str(_TOOL), *head, "--", *args], capture_output=True, cwd=tmp_path
    )


# --- Reading the options -------------------------------------------------------


def test_an_option_is_read_as_the_engine_reads_it():
    opts = run_py_func.Options(["-w", "4", "-flag", "-n", "-5", "-empty", "--next", "x", "-last"])
    assert opts.value("-w") == "4"
    # A negative number is a value, not an option
    assert opts.value("-n") == "-5"
    # An option followed by another option, or by nothing, has no value
    assert opts.value("-empty") is None
    assert opts.value("-last", "dflt") == "dflt"
    assert opts.value("-missing") is None
    assert opts.given("-flag") and not opts.given("-missing")


def test_a_task_reads_the_value_that_a_value_descriptor_holds(tmp_path):
    desc = tmp_path / ".__VAL_DESCRIPTOR__-outv_0"
    desc.write_text("7\n")
    task = run_py_func.Task(["-val", str(desc), "-outv", str(desc), "-x", "1"], "proc")
    assert task.value("-val") == "7"
    # An output option names the descriptor, which it is to write
    assert task.value("-outv") == str(desc)
    assert task.value("-x") == "1"
    # The command line of a run holds no descriptors, and is read as it is
    assert run_py_func.Run(["-val", str(desc)], "proc", "/o").value("-val") == str(desc)


# --- tasks(run) of an array ---------------------------------------------------


def test_an_array_prints_each_element_followed_by_a_nul(tmp_path):
    code = (
        "from pathlib import Path\n"
        "def tasks(run):\n"
        "    return ['a b', 3, 1.5, Path('x/y'), run.process, run.outdir, run.value('-s')]\n"
    )
    result = _run(tmp_path, "array", code, "-s", "given")
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"a b\x003\x001.5\x00x/y\x00proc\x00/outd/proc\x00given\x00"


def test_an_array_may_be_empty_and_given_as_any_iterable(tmp_path):
    assert _run(tmp_path, "array", "def tasks(run):\n    return []\n").stdout == b""
    result = _run(tmp_path, "array", "def tasks(run):\n    return (str(i) for i in range(2))\n")
    assert result.stdout == b"0\x001\x00"


@pytest.mark.parametrize(
    "returned, message",
    [
        ("'abc'", b"returned str, not a list of the elements of the array"),
        ("{'a': 1}", b"returned dict, not a list"),
        ("3", b"returned int, not a list"),
        ("[True]", b"element 0 of type bool"),
        ("['a', None]", b"element 1 of type NoneType"),
        ("['a\\0b']", b"element 0 with a NUL character"),
    ],
)
def test_an_array_refuses_what_is_not_a_list_of_elements(tmp_path, returned, message):
    result = _run(tmp_path, "array", f"def tasks(run):\n    return {returned}\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    assert result.stdout == b""
    assert message in result.stderr


# --- tasks(run) of an option generator ------------------------------------------


def test_an_option_generator_prints_the_number_of_tasks(tmp_path):
    result = _run(tmp_path, "count", "def tasks(run):\n    return int(run.value('-w')) + 1\n", "-w", "2")
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"3\n"


@pytest.mark.parametrize("returned", ["-1", "True", "2.0", "'2'", "[1]"])
def test_an_option_generator_refuses_what_is_not_a_number_of_tasks(tmp_path, returned):
    result = _run(tmp_path, "count", f"def tasks(run):\n    return {returned}\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    assert result.stdout == b""
    assert b"not a number of tasks" in result.stderr


# --- skip(task) ---------------------------------------------------------------


def test_skip_gives_its_decision_as_the_exit_status(tmp_path):
    code = "def skip(task):\n    return task.process == 'proc' and task.given('-done')\n"
    assert _run(tmp_path, "skip", code, "-done").returncode == 0
    assert _run(tmp_path, "skip", code, "-x", "1").returncode == 1


def test_skip_refuses_what_is_not_true_or_false(tmp_path):
    result = _run(tmp_path, "skip", "def skip(task):\n    return 1\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    assert b"returned 1, not True or False" in result.stderr


# --- Errors and what the file prints ----------------------------------------------


def test_an_exception_gives_the_traceback_from_the_code_of_the_user(tmp_path):
    result = _run(tmp_path, "skip", "def skip(task):\n    return int(task.value('-x'))\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    stderr = result.stderr.decode()
    assert "TypeError" in stderr
    assert 'func.py", line 2, in skip' in stderr
    assert "debasher_run_py_func" not in stderr.split("Error:")[0]
    assert "the Python function of" in stderr and "(process proc)" in stderr


def test_a_file_that_exits_is_an_error_even_with_status_zero(tmp_path):
    result = _run(tmp_path, "skip", "import sys\nsys.exit(0)\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    assert b"exited instead of returning" in result.stderr


def test_a_file_without_the_function_is_an_error(tmp_path):
    result = _run(tmp_path, "array", "def skip(task):\n    return True\n")
    assert result.returncode == run_py_func.ERROR_STATUS
    assert b"defines no function tasks" in result.stderr


def test_what_the_file_prints_goes_to_the_standard_error(tmp_path):
    code = (
        "import os\n"
        "print('at load')\n"
        "def tasks(run):\n"
        "    print('in tasks')\n"
        "    os.system('echo from a child')\n"
        "    return ['x']\n"
    )
    result = _run(tmp_path, "array", code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"x\x00"
    for line in (b"at load", b"in tasks", b"from a child"):
        assert line in result.stderr


def test_a_file_imports_the_files_beside_it(tmp_path):
    (tmp_path / "sheet.py").write_text("SAMPLES = ['s1', 's2']\n")
    result = _run(tmp_path, "array", "from sheet import SAMPLES\ndef tasks(run):\n    return SAMPLES\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"s1\x00s2\x00"


@pytest.mark.parametrize(
    "argv",
    [[], ["array", "f.py", "p", "o"], ["bogus", "f.py", "p", "o", "--"], ["skip", "f.py", "p", "o", "--"]],
)
def test_a_malformed_command_line_is_an_error(argv):
    assert run_py_func.main(argv) == run_py_func.ERROR_STATUS
