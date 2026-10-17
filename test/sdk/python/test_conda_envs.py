"""
The conda example with its environment given as data, described with the
SDK (data/sdk_programs/python/sdk_conda_envs), is the program that the
editor saved as data/webui_programs/webui_conda_envs: a process whose
Conda environment is a name and a YAML file, from which the module writes
the line that creates it.
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402

from examples import as_webui_twin, webui_home  # noqa: E402
from test_hello_world import comparable  # noqa: E402

_EXAMPLE = "sdk_conda_envs"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(webui_home(_EXAMPLE)))
    assert comparable(written) == comparable(shipped)
    assert [(env.name, env.file) for env in written.processes[0].additionalMethods.condaEnvs] == [
        ("py27", "py27.yml")
    ]


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    script = as_webui_twin(_EXAMPLE).write(tmp_path)

    assert script.read_text() == (webui_home(_EXAMPLE) / "webui_conda_envs.sh").read_text()
