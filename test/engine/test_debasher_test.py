"""
Tests of the business tests of a program as installed: debasher_test,
the test helpers (debasher_process, debasher_skip_without_conda_env), the
features of debasher_exec_process that serve them, and
debasher_get_node_source, run from bin/ and libexec/ as make install puts
them, on program directories built in tmp_path. Like the other tests that
run the installed tools, they are skipped unless DEBASHER_RUN_CHAOS_TEST is
set.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from resident_run import REPO_ROOT, real_run

pytestmark = real_run

DEBASHER_TEST = REPO_ROOT / "bin" / "debasher_test"
DEBASHER_EXEC_PROCESS = REPO_ROOT / "bin" / "debasher_exec_process"
DEBASHER_GET_NODE_SOURCE = REPO_ROOT / "libexec" / "debasher_get_node_source"
BATS_HELPERS = REPO_ROOT / "lib" / "debasher" / "debasher_bats_helpers"

needs_bats = pytest.mark.skipif(shutil.which("bats") is None, reason="bats is not installed")

# A program written by hand: greet writes a greeting to its standard
# output and a note to its standard error, and fails with status 3 on the
# text "fail"
GREET_MODULE = """\
greet_explain_opts()
{
    explain_opt "-text" "<string>" "Text to greet"
}

greet_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "${cmdline}" "-text" optlist || return 1
    save_opt_list optlist
}

greet()
{
    local text=$(read_opt_value_from_func_args "-text" "$@")
    echo "greeting ${text}" >&2
    [ "${text}" = "fail" ] && return 3
    echo "Hello ${text}"
}

debasher_handmade_program()
{
    add_debasher_process "greet" "cpus=1 mem=32 time=00:01:00"
}
"""

# A process test of greet: only the process writes to the standard error
# (-q), and the status of debasher_process is that of the process function
GREET_TEST = """\
load "${DEBASHER_BATS_HELPERS}"

@test "greet greets" {
    run --separate-stderr debasher_process greet -text Ann
    [ "${status}" -eq 0 ]
    [ "${output}" = "Hello Ann" ]
    [ "${stderr}" = "greeting Ann" ]
}

@test "greet fails with its own status" {
    run --separate-stderr debasher_process greet -text fail
    [ "${status}" -eq 3 ]
}
"""

FAILING_TEST = """\
load "${DEBASHER_BATS_HELPERS}"

@test "greet greets someone else" {
    run --separate-stderr debasher_process greet -text Ann
    [ "${output}" = "Hello Bob" ]
}
"""

PYTEST_TEST = """\
import os


def test_the_program_file_is_given():
    assert os.environ["DEBASHER_TEST_PFILE"].endswith("debasher_handmade.sh")
"""


def program_dir(tmp_path, name="prog", bats=None, pytest_file=None):
    prgdir = tmp_path / name
    prgdir.mkdir()
    (prgdir / "debasher_handmade.sh").write_text(GREET_MODULE)
    testdir = prgdir / "test"
    testdir.mkdir()
    if bats is not None:
        (testdir / "greet.bats").write_text(bats)
    if pytest_file is not None:
        (testdir / "test_prog.py").write_text(pytest_file)
    return prgdir


def debasher_test(prgdir, env=None):
    return subprocess.run(
        [str(DEBASHER_TEST), str(prgdir)], capture_output=True, text=True, env={**os.environ, **(env or {})}
    )


@needs_bats
def test_the_tests_of_a_program_written_by_hand_run_on_its_only_script(tmp_path):
    prgdir = program_dir(tmp_path, bats=GREET_TEST)

    result = debasher_test(prgdir)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_directory_with_no_script_or_several_is_refused(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = debasher_test(empty)
    assert result.returncode == 2
    assert "has no *.sh file at its top" in result.stderr

    several = program_dir(tmp_path, name="several", bats=GREET_TEST)
    (several / "other.sh").write_text("")
    result = debasher_test(several)
    assert result.returncode == 2
    assert "cannot tell which one is the program" in result.stderr


def test_a_program_without_tests_ends_with_77(tmp_path):
    prgdir = program_dir(tmp_path)

    result = debasher_test(prgdir)

    assert result.returncode == 77, result.stdout + result.stderr


@needs_bats
def test_a_test_that_fails_ends_with_1(tmp_path):
    prgdir = program_dir(tmp_path, bats=FAILING_TEST)

    result = debasher_test(prgdir)

    assert result.returncode == 1, result.stdout + result.stderr


def test_debasher_pytest_gives_the_pytest_that_runs_the_node_tests(tmp_path):
    prgdir = program_dir(tmp_path, pytest_file=PYTEST_TEST)
    calls = tmp_path / "calls"
    wrapper = tmp_path / "pytest_wrapper"
    pytest_tool = os.environ.get("DEBASHER_PYTEST") or shutil.which("pytest") or str(REPO_ROOT / ".venv" / "bin" / "pytest")
    wrapper.write_text(f'#!/bin/sh\necho called >> "{calls}"\nexec "{pytest_tool}" "$@"\n')
    wrapper.chmod(0o755)

    result = debasher_test(prgdir, env={"DEBASHER_PYTEST": str(wrapper)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text() == "called\n"


@needs_bats
def test_the_tests_of_a_read_only_program_pass_and_write_nothing_into_it(tmp_path):
    prgdir = program_dir(tmp_path, bats=GREET_TEST, pytest_file=PYTEST_TEST)
    before = sorted(p.relative_to(prgdir) for p in prgdir.rglob("*"))
    paths = [prgdir, *prgdir.rglob("*")]
    for path in paths:
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        result = debasher_test(prgdir)
    finally:
        for path in paths:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)

    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(p.relative_to(prgdir) for p in prgdir.rglob("*")) == before


def test_debasher_exec_process_with_q_leaves_only_the_process_on_the_standard_error(tmp_path):
    prgdir = program_dir(tmp_path)
    pfile = prgdir / "debasher_handmade.sh"

    quiet = subprocess.run([str(DEBASHER_EXEC_PROCESS), "-q", str(pfile), "greet", "--", "-text", "Ann"],
                           capture_output=True, text=True)
    assert quiet.returncode == 0, quiet.stderr
    assert quiet.stdout == "Hello Ann\n"
    assert quiet.stderr == "greeting Ann\n"

    failing = subprocess.run([str(DEBASHER_EXEC_PROCESS), "-q", str(pfile), "greet", "--", "-text", "fail"],
                             capture_output=True, text=True)
    assert failing.returncode == 3


def test_debasher_exec_process_refuses_a_program_whose_program_method_fails(tmp_path):
    pfile = tmp_path / "debasher_prgfail.sh"
    pfile.write_text(
        GREET_MODULE.replace("debasher_handmade_program", "debasher_prgfail_program")
        .replace('add_debasher_process "greet" "cpus=1 mem=32 time=00:01:00"',
                 'add_debasher_process "greet" "cpus=1 mem=32 time=00:01:00"\n    return 1')
    )

    result = subprocess.run([str(DEBASHER_EXEC_PROCESS), "-q", str(pfile), "greet", "--", "-text", "Ann"],
                            capture_output=True, text=True)

    assert result.returncode == 1
    assert "the _program method of" in result.stderr
    assert "Hello" not in result.stdout


def test_debasher_exec_process_runs_a_sequential_process_and_refuses_any_other_function(tmp_path):
    example = REPO_ROOT / "data" / "programs" / "debasher_seq_process_example.sh"
    outf = tmp_path / "doubled.txt"

    step = subprocess.run([str(DEBASHER_EXEC_PROCESS), "-q", str(example), "double", "--", "3", str(outf)],
                          capture_output=True, text=True)
    assert step.returncode == 0, step.stderr
    assert outf.read_text() == "6"

    other = subprocess.run([str(DEBASHER_EXEC_PROCESS), "-q", str(example), "debasher::_get_num_processes", "--"],
                           capture_output=True, text=True)
    assert other.returncode == 1
    assert "is neither a process nor a sequential process of the program" in other.stderr


@needs_bats
def test_debasher_process_stops_with_its_message_without_a_program_file(tmp_path):
    testfile = tmp_path / "nopfile.bats"
    testfile.write_text(
        'load "${DEBASHER_BATS_HELPERS}"\n\n'
        '@test "no program file" {\n'
        '    run --separate-stderr debasher_process greet -text Ann\n'
        '    [ "${status}" -eq 1 ]\n'
        '    [[ "${stderr}" == *"DEBASHER_TEST_PFILE is not set"* ]]\n'
        '}\n'
    )
    env = {k: v for k, v in os.environ.items() if k != "DEBASHER_TEST_PFILE"}
    env["DEBASHER_BATS_HELPERS"] = str(BATS_HELPERS)

    result = subprocess.run(["bats", str(testfile)], capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stdout + result.stderr


def _skip_test(tmp_path, env_name):
    testfile = tmp_path / "skip.bats"
    testfile.write_text(
        'load "${DEBASHER_BATS_HELPERS}"\n\n'
        f'@test "needs an environment" {{\n    debasher_skip_without_conda_env {env_name}\n    false\n}}\n'
    )
    return testfile


@needs_bats
def test_debasher_skip_without_conda_env_skips_where_conda_is_missing(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("CONDA_EXE", "DEBASHER_CONDA")}
    env["DEBASHER_BATS_HELPERS"] = str(BATS_HELPERS)

    result = subprocess.run(["bats", str(_skip_test(tmp_path, "py27"))], capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "# skip conda was not found" in result.stdout


@needs_bats
@pytest.mark.skipif(not (os.environ.get("CONDA_EXE") or shutil.which("conda")), reason="conda is not installed")
def test_debasher_skip_without_conda_env_skips_an_environment_that_does_not_exist(tmp_path):
    env = dict(os.environ)
    env["DEBASHER_CONDA"] = os.environ.get("CONDA_EXE") or shutil.which("conda")
    env["DEBASHER_BATS_HELPERS"] = str(BATS_HELPERS)

    result = subprocess.run(["bats", str(_skip_test(tmp_path, "no_such_debasher_env"))],
                            capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "# skip the conda environment no_such_debasher_env does not exist" in result.stdout


NOISY_MODULE = """\
echo "the module prints when it loads"

Echo_heredoc_py()
{
    cat <<'PYEOF'
class Echo(FBPProcess):
    pass
PYEOF
}

plain()
{
    :
}
"""


def test_debasher_get_node_source_prints_the_code_alone_or_fails_without_a_heredoc(tmp_path):
    pfile = tmp_path / "debasher_noisy.sh"
    pfile.write_text(NOISY_MODULE)

    source = subprocess.run([str(DEBASHER_GET_NODE_SOURCE), str(pfile), "Echo"], capture_output=True, text=True)
    assert source.returncode == 0, source.stderr
    assert source.stdout == "class Echo(FBPProcess):\n    pass\n"

    missing = subprocess.run([str(DEBASHER_GET_NODE_SOURCE), str(pfile), "plain"], capture_output=True, text=True)
    assert missing.returncode == 1
    assert "process plain has no Python heredoc" in missing.stderr
