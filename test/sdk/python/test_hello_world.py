"""
The hello world of the quickstart, described with the SDK
(data/sdk_programs/python/sdk_hello_world_py), is the program that the
web UI saved as data/webui_programs/webui_hello_world_py: the same program
metadata, apart from the ids, which the editor draws at random and the
SDK derives from the names, and the same generated module, byte for byte.
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402

from examples import as_webui_twin, webui_home  # noqa: E402

_EXAMPLE = "sdk_hello_world_py"


def comparable(program) -> dict:
    """The program metadata without what differs between two saves of the
    same program: the ids, the digest and the home directory. A count
    source is named by its label instead of its id, and a connection by
    the names and labels of its ends."""
    data = program.model_dump(exclude={"id", "digest", "homeDir"})
    process_names = {process.id: process.name for process in program.processes}
    option_labels = {option.id: option.label for process in program.processes for option in process.options}
    for process in data["processes"]:
        del process["id"]
        # The paths of the files of a process are the description's own
        del process["files"]
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
    as_webui_twin(_EXAMPLE).write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(webui_home(_EXAMPLE)))
    assert comparable(written) == comparable(shipped)


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    script = as_webui_twin(_EXAMPLE).write(tmp_path)

    assert script.read_text() == (webui_home(_EXAMPLE) / "webui_hello_world_py.sh").read_text()
