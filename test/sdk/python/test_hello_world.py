"""
The hello world of the quickstart, written with the SDK, is the program
that the web UI saved as data/webui_programs/webui_hello_world_py: the
same program metadata, apart from the ids, which the editor draws at
random and the SDK derives from the names, and the same generated module,
byte for byte.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402
from debasher.build import load_program  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEBUI_HOME = _REPO_ROOT / "data" / "webui_programs" / "webui_hello_world_py"
_SDK_FILE = Path(__file__).parent / "data" / "hello_world" / "webui_hello_world_py.py"


def comparable(program) -> dict:
    """The program metadata without what differs between two saves of the
    same program: the ids, the revision and the home directory. A count
    source is named by its label instead of its id, and a connection by
    the names and labels of its ends."""
    data = program.model_dump(exclude={"id", "revision", "homeDir"})
    process_names = {process.id: process.name for process in program.processes}
    option_labels = {option.id: option.label for process in program.processes for option in process.options}
    for process in data["processes"]:
        del process["id"]
        for option in process["options"]:
            del option["id"]
            if option["countSourceOptionId"] is not None:
                option["countSourceOptionId"] = option_labels[option["countSourceOptionId"]]
    data["edges"] = sorted(
        (
            process_names[edge["sourceProcessId"]],
            option_labels[edge["sourceOptionId"]],
            process_names[edge["targetProcessId"]],
            option_labels[edge["targetOptionId"]],
            edge["display"],
        )
        for edge in data["edges"]
    )
    return data


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    program.write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(_WEBUI_HOME))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    program = load_program(_SDK_FILE)
    script = program.write(tmp_path)

    assert script.read_text() == (_WEBUI_HOME / "webui_hello_world_py.sh").read_text()
