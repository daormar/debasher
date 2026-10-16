"""
The running sum example of the web UI, written with the SDK, is the
resident program that the editor saved as
data/webui_programs/webui_running_sum: a node given as a Python file with
its class, an external input and an output through FIFOs, and a
Supervisor.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher.build import load_program  # noqa: E402

from test_hello_world import comparable  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEBUI_HOME = _REPO_ROOT / "data" / "webui_programs" / "webui_running_sum"
_SDK_FILE = Path(__file__).parent / "data" / "running_sum" / "webui_running_sum.py"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    program.write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(_WEBUI_HOME))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    script = program.write(tmp_path)

    assert script.read_text() == (_WEBUI_HOME / "webui_running_sum.sh").read_text()
