"""
The skip example, described with the SDK (data/sdk_programs/python/sdk_skip_py),
is the program that the editor saved as data/webui_programs/webui_skip_py: a
process sums two numbers into a value descriptor, and another reads the sum
and is skipped by a skip file in Python when it is odd.
"""

import pytest

pytest.importorskip("pydantic")

from api import persistence  # noqa: E402

from examples import as_webui_twin, webui_home  # noqa: E402
from test_hello_world import comparable  # noqa: E402

_EXAMPLE = "sdk_skip_py"


def test_the_sdk_writes_the_program_metadata_of_the_editor(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    written = persistence.load_program(str(tmp_path))
    shipped = persistence.load_program(str(webui_home(_EXAMPLE)))
    assert comparable(written) == comparable(shipped)
    assert written.processes[1].additionalMethods.skipLanguage == "python"


def test_the_sdk_writes_the_module_of_the_editor(tmp_path):
    script = as_webui_twin(_EXAMPLE).write(tmp_path)

    assert script.read_text() == (webui_home(_EXAMPLE) / "webui_skip_py.sh").read_text()


def test_the_skip_file_is_written_beside_the_module(tmp_path):
    as_webui_twin(_EXAMPLE).write(tmp_path)

    assert (tmp_path / "value_reader_skip.py").read_text() == (
        webui_home(_EXAMPLE) / "value_reader_skip.py"
    ).read_text()
