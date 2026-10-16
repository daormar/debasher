"""
The dynamic fanout example of the web UI, written with the SDK, is the
program that the editor saved as data/webui_programs/webui_dynamic_fanout_fifos:
an array process shaped by its Bash tasks file, a family of FIFOs counted
by a command line option, a family of inputs gathering the task
subdirectories of the array, a dispatcher run as a script, and an explicit
dependency. The process files under data/dynamic_fanout_fifos hold the
code exactly as the editor saved it, without a final newline, so that the
metadata compares exactly.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher.build import load_program  # noqa: E402

from test_hello_world import comparable  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEBUI_HOME = _REPO_ROOT / "data" / "webui_programs" / "webui_dynamic_fanout_fifos"
_SDK_FILE = Path(__file__).parent / "data" / "dynamic_fanout_fifos" / "webui_dynamic_fanout_fifos.py"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    program.write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(_WEBUI_HOME))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    script = program.write(tmp_path)

    assert script.read_text() == (_WEBUI_HOME / "webui_dynamic_fanout_fifos.sh").read_text()


def test_the_script_is_copied_beside_the_module(tmp_path):
    load_program(_SDK_FILE).write(tmp_path)

    assert (tmp_path / "dynamic_fanout_dispatcher.py").read_text() == (
        _WEBUI_HOME / "dynamic_fanout_dispatcher.py"
    ).read_text()
