"""
The reference of the runtime library that the code prompt of a node carries
(see api/node_reference.py), read from the library itself.
"""

import re
from pathlib import Path

import pytest

from api import node_reference, paths

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def sources_of_the_library(monkeypatch):
    # The sources in engine/, which these tests check, rather than a copy
    # installed from an older tree.
    monkeypatch.setenv("DEBASHER_WEBUI_PYTHON_DIR", str(_REPO_ROOT / "engine"))


def test_a_business_node_gets_the_contract_of_its_hooks():
    reference = node_reference.node_reference("FBPProcess")

    assert reference.startswith("### FBPProcess\n\nThe base class of every node")
    assert "`def process_data(self, port_name, packet)`\n\nProcesses one message" in reference
    assert "It must be deterministic" in reference
    assert "`def send_data(self, tag, payload)`" in reference
    assert "- `OBSERVE_PORT = None`: The name under which what observe() brings in" in reference
    assert "DirectoryWatcher" not in reference


@pytest.mark.parametrize("kind", ["DirectoryWatcher", "ProgramLauncher"])
def test_a_node_of_a_derived_class_gets_its_class_after_fbpprocess(kind):
    reference = node_reference.node_reference(kind)

    assert reference.index("### FBPProcess") < reference.index(f"### {kind}")
    assert f"#### Class attributes of {kind}" in reference


def test_the_attributes_of_a_class_come_with_their_value_and_documentation():
    reference = node_reference.node_reference("ProgramLauncher")

    assert "- `PFILE = None`: The module of the general program to launch (required)." in reference


def test_a_supervisor_has_no_reference():
    assert node_reference.node_reference("Supervisor") == ""


def test_a_runtime_library_that_is_not_found_is_an_error(monkeypatch):
    monkeypatch.setattr(paths, "find_runtime_module", lambda name: None)

    with pytest.raises(node_reference.NodeReferenceError, match="not found"):
        node_reference.node_reference("FBPProcess")


def test_a_name_that_the_library_does_not_document_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "debasher_runtime_fbp.py").write_text('class FBPProcess:\n    """Doc."""\n')
    monkeypatch.setenv("DEBASHER_WEBUI_PYTHON_DIR", str(tmp_path))

    with pytest.raises(node_reference.NodeReferenceError, match="no method FBPProcess.process_data"):
        node_reference.node_reference("FBPProcess")


def test_the_names_are_those_of_the_page_of_the_documentation():
    # The page lists, for each class, what a module uses of it; the
    # reference names the same, but for run(), which script generation
    # calls, and the Supervisor, which has no code prompt.
    page = (_REPO_ROOT / "rtdocs" / "source" / "api_resident_nodes.rst").read_text()
    listed = {}
    for cls, name in re.findall(r"\.\. auto(?:method|attribute):: debasher_runtime_lib\.(\w+)\.(\w+)", page):
        listed.setdefault(cls, []).append(name)
    listed["FBPProcess"].remove("run")
    del listed["Supervisor"]

    assert {cls: tuple(names) for cls, names in listed.items()} == node_reference.documented_names()
