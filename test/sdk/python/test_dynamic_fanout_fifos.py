"""
The dynamic fanout example of the web UI, described with the SDK
(data/sdk_programs/python/sdk_dynamic_fanout_fifos), is the program that
the editor saved as data/webui_programs/webui_dynamic_fanout_fifos: an
array process shaped by its tasks file in Python, a family of FIFOs counted by
a command line option, a family of inputs gathering the task
subdirectories of the array, a dispatcher run as a script, and an explicit
dependency.
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402

from examples import as_webui_twin, webui_home  # noqa: E402
from test_hello_world import comparable  # noqa: E402

_EXAMPLE = "sdk_dynamic_fanout_fifos"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(webui_home(_EXAMPLE)))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    script = as_webui_twin(_EXAMPLE).write(tmp_path)

    assert script.read_text() == (webui_home(_EXAMPLE) / "webui_dynamic_fanout_fifos.sh").read_text()


def test_the_script_is_copied_beside_the_module(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    assert (tmp_path / "dynamic_fanout_dispatcher.py").read_text() == (
        webui_home(_EXAMPLE) / "dynamic_fanout_dispatcher.py"
    ).read_text()
