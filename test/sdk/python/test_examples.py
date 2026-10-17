"""
The examples that ship under data/sdk_programs/python, as they are: each
is a description named after its program that debasher_build writes into
a home directory the web UI loads, with the files of its processes beside
it. What each one reproduces of the web UI is checked by its own test
module (test_hello_world, test_dynamic_fanout_fifos, test_running_sum,
test_skip_py, test_conda_envs).
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher.build import main  # noqa: E402

from examples import SDK_PROGRAMS_DIR, TWINS, example_file  # noqa: E402

_EXAMPLES = sorted(path.name for path in SDK_PROGRAMS_DIR.iterdir() if path.is_dir())


def test_every_example_has_a_twin_of_the_web_ui():
    assert _EXAMPLES == sorted(TWINS)


@pytest.mark.parametrize("name", _EXAMPLES)
def test_an_example_builds_into_a_program_the_web_ui_loads(name, tmp_path, capsys):
    assert main([str(example_file(name)), "-o", str(tmp_path)]) == 0

    program = persistence.load_program(str(tmp_path))
    assert program.name == name
    assert capsys.readouterr().out.strip() == str(tmp_path / f"{name}.sh")
