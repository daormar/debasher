"""
The running sum example of the web UI, described with the SDK
(data/sdk_programs/python/sdk_running_sum), is the resident program that
the editor saved as data/webui_programs/webui_running_sum: a node given as
a Python file with its class, an external input and an output through
FIFOs, and a Supervisor.
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402

from examples import as_webui_twin, webui_home  # noqa: E402
from test_hello_world import comparable  # noqa: E402

_EXAMPLE = "sdk_running_sum"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(webui_home(_EXAMPLE)))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    script = as_webui_twin(_EXAMPLE).write(tmp_path)

    assert script.read_text() == (webui_home(_EXAMPLE) / "webui_running_sum.sh").read_text()
