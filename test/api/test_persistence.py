"""
The branches of saving that decide not to delete or not to copy (see
"Loading, saving and the local state" in doc/design_doc_webui.md): a
program renamed loses the module of its old name, whether the old name
comes from the topology file or from the program metadata of before the
artifact, and nothing is deleted when the old name cannot be read; the
scripts of an imported program are copied beside its module, except
those that are missing, absolute, outside the home directory or already
in place; a file that cannot be read never counts as holding the text a
save would write.
"""

import os
from pathlib import Path

import pytest

import pydantic

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip("the API needs pydantic 2", allow_module_level=True)

from api import persistence  # noqa: E402
from api.models import (  # noqa: E402
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    OptionsHandler,
    Position,
    Program,
    ProgramProcess,
)


def _process(name: str, external_alias: str = "") -> ProgramProcess:
    return ProgramProcess(
        id=name,
        name=name,
        description="",
        position=Position(x=0, y=0),
        options=[],
        optionsHandler=OptionsHandler(mode="standard"),
        language="bash",
        code="" if external_alias else f"{name}()\n{{\n    :\n}}",
        computationalSpecs=ComputationalSpecs(),
        additionalSpecs=AdditionalSpecs(force=False, externalAlias=external_alias),
    )


def _program(name: str, processes: list[ProgramProcess], source_dir: str = "") -> Program:
    return Program(
        id=name,
        name=name,
        preamble="",
        envVars={},
        homeDir="",
        outputDir="",
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=processes,
        edges=[],
        sourceDir=source_dir,
    )


# --- the module of the old name ------------------------------------------------


def test_a_program_renamed_loses_the_module_of_its_old_name(tmp_path):
    persistence.save(str(tmp_path), _program("old", [_process("step")]))
    assert (tmp_path / "old.sh").is_file()

    persistence.save(str(tmp_path), _program("new", [_process("step")]))

    assert not (tmp_path / "old.sh").exists()
    assert (tmp_path / "new.sh").is_file()


def test_the_old_name_comes_from_the_program_metadata_of_before_the_artifact(tmp_path):
    metadata = tmp_path / ".debasher" / "program.json"
    metadata.parent.mkdir()
    metadata.write_text('{"name": "old"}')
    (tmp_path / "old.sh").write_text("# the module of before\n")

    persistence.delete_stale_script(str(tmp_path), "new")

    assert not (tmp_path / "old.sh").exists()


def test_a_topology_file_that_cannot_be_read_deletes_no_module(tmp_path):
    (tmp_path / "program.yaml").write_text("name: [unclosed\n")
    (tmp_path / "old.sh").write_text("# a module\n")

    persistence.delete_stale_script(str(tmp_path), "new")

    assert (tmp_path / "old.sh").is_file()


# --- the scripts of an imported program -----------------------------------------


def test_the_script_of_an_imported_program_is_copied_beside_its_module(tmp_path):
    source = tmp_path / "source"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "t.sh").write_text("echo t\n")
    home = tmp_path / "home"

    persistence.copy_ext_alias_files(_program("prg", [_process("t", "tools/t.sh")], str(source)), str(home))

    assert (home / "tools" / "t.sh").read_text() == "echo t\n"


def test_a_missing_or_absolute_script_is_not_copied_and_stops_nothing(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / "abs.sh").write_text("echo abs\n")
    home = tmp_path / "home"
    home.mkdir()
    program = _program("prg", [_process("gone", "gone.sh"), _process("abs", str(tmp_path / "abs.sh"))], str(source))

    persistence.copy_ext_alias_files(program, str(home))

    assert list(home.iterdir()) == []


def test_a_script_that_climbs_out_of_the_home_directory_is_not_copied(tmp_path):
    source = tmp_path / "source"
    (source / "home").mkdir(parents=True)
    (source / "tools").mkdir()
    (source / "tools" / "t.sh").write_text("echo source\n")
    (tmp_path / "out" / "home").mkdir(parents=True)
    (tmp_path / "out" / "tools").mkdir()
    (tmp_path / "out" / "tools" / "t.sh").write_text("echo theirs\n")
    program = _program("prg", [_process("t", "../tools/t.sh")], str(source / "home"))

    persistence.copy_ext_alias_files(program, str(tmp_path / "out" / "home"))

    assert (tmp_path / "out" / "tools" / "t.sh").read_text() == "echo theirs\n"


def test_a_script_saved_back_into_its_own_directory_is_left_as_it_is(tmp_path):
    (tmp_path / "t.sh").write_text("echo t\n")

    persistence.copy_ext_alias_files(_program("prg", [_process("t", "t.sh")], str(tmp_path)), str(tmp_path))

    assert (tmp_path / "t.sh").read_text() == "echo t\n"


# --- a file that cannot be read ---------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_a_file_that_cannot_be_read_does_not_hold_the_text_of_a_save(tmp_path):
    path = tmp_path / "step.sh"
    path.write_text("step\n")
    path.chmod(0)
    try:
        assert not persistence._same_text(path, "step\n")
    finally:
        path.chmod(0o644)
    assert persistence._same_text(Path(path), "step\n")
