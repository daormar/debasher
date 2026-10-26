"""
The rule that tells an option from a value, the rule of an output option
and the prefix of a value descriptor are written in Bash in the engine and
copied in its Python tools (debasher_run_py_func.py, debasher_compare_opts.py
and debasher_prg_lib.py). These tests check that every copy agrees with the
Bash one on the same words.
"""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "engine"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ENGINE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_py_func = _load("debasher_run_py_func")
compare_opts = _load("debasher_compare_opts")
prg_lib = _load("debasher_prg_lib")

WORDS = [
    "-a", "--out", "-_x", "--b1", "-outf", "--outdir", "-out", "-o", "-in",
    "-5", "-0.5", "--1", "-", "--", "", "value", "a-b", "/abs/path", "-.x",
    "- a", "-é", "--ñx",
]


def _bash_answers(function):
    """Whether the Bash function takes each of WORDS for its kind, by
    sourcing the source of the library of the engine."""
    script = (
        f'source "{ENGINE / "debasher_lib_utils.sh"}"\n'
        'for word in "$@"; do\n'
        f'    if debasher::{function} "$word"; then echo 1; else echo 0; fi\n'
        "done\n"
    )
    # A UTF-8 locale where a range of letters may match more than ASCII
    env = dict(os.environ, LC_ALL="en_US.UTF-8")
    result = subprocess.run(
        ["bash", "-c", script, "bash", *WORDS], capture_output=True, text=True, check=True, env=env
    )
    return [line == "1" for line in result.stdout.splitlines()]


@pytest.mark.parametrize(
    "copy",
    [
        lambda word: run_py_func._OPTION_RE.match(word) is not None,
        compare_opts.is_option,
        lambda word: prg_lib.ProcessGraph.str_is_option(None, word),
    ],
    ids=["debasher_run_py_func", "debasher_compare_opts", "debasher_prg_lib"],
)
def test_every_copy_of_the_rule_of_an_option_agrees_with_the_engine(copy):
    expected = _bash_answers("_str_is_option")
    assert len(expected) == len(WORDS)
    assert {word: copy(word) for word in WORDS} == dict(zip(WORDS, expected))


def test_the_rule_of_an_output_option_agrees_with_the_engine():
    expected = _bash_answers("_str_is_output_option")
    copy = {word: prg_lib.ProcessGraph.str_is_output_option(None, word) for word in WORDS}
    assert copy == dict(zip(WORDS, expected))


def test_the_prefix_of_a_value_descriptor_is_that_of_the_engine():
    source = (ENGINE / "debasher_lib.sh").read_text()
    match = re.search(r'^DEBASHER_VALUE_DESCRIPTOR_NAME_PREFIX="([^"]*)"', source, re.MULTILINE)
    assert match is not None
    assert run_py_func._VALUE_DESCRIPTOR_PREFIX == match.group(1)
