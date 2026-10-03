"""
The revision of the program metadata (see "Revisions of the program
metadata" in doc/design_doc_webui.md): every save that changes the program
metadata increments it, and a save into the program's own home directory is
refused when the metadata there holds another revision than the one the
program was loaded with, so that a tab or an agent never overwrites what
another saved since. A save that changes nothing keeps the revision, and a
program that script generation refuses writes nothing.
"""

import json
import stat
import threading
from pathlib import Path

import pytest

# The routers under test import fastapi, which the system Python used by
# `make check` may not have (see api/README.md).
pytest.importorskip("fastapi")

import pydantic  # noqa: E402

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip("the API needs pydantic 2", allow_module_level=True)

from api import paths, persistence  # noqa: E402
from api.models import (  # noqa: E402
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    OptionsHandler,
    Position,
    Program,
    ProgramOption,
    ProgramProcess,
)
from api.routers import execution, programs  # noqa: E402


@pytest.fixture(autouse=True)
def no_tools(monkeypatch):
    """No engine tool is found unless a test fakes one: no run is ever in
    progress."""
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: None)


def _program(tmp_path: Path, name: str = "rev", home: str = "home") -> Program:
    step = ProgramProcess(
        id="step",
        name="step",
        description="",
        position=Position(x=0, y=0),
        options=[],
        optionsHandler=OptionsHandler(mode="standard"),
        language="bash",
        code="step()\n{\n    :\n}",
        computationalSpecs=ComputationalSpecs(),
        additionalSpecs=AdditionalSpecs(force=False),
    )
    return Program(
        id=name,
        name=name,
        preamble="",
        envVars={},
        homeDir=str(tmp_path / home),
        outputDir=str(tmp_path / "out"),
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=[step],
        edges=[],
    )


def _save(program: Program, into: str | None = None):
    return programs.save_program_to_dir(
        programs.SaveProgramRequest(outputDir=into or program.homeDir, program=program)
    )


def _conflict(call):
    with pytest.raises(programs.HTTPException) as refused:
        call()
    assert refused.value.status_code == 409
    assert refused.value.detail["code"] == "revision"
    return refused.value.detail


def test_every_save_that_changes_the_program_increments_its_revision(tmp_path):
    program = _program(tmp_path)

    assert _save(program).revision == 1
    loaded = persistence.load_program(program.homeDir)
    assert loaded.revision == 1

    assert _save(loaded.model_copy(update={"description": "changed"})).revision == 2
    assert persistence.load_program(program.homeDir).revision == 2


def test_a_save_on_a_stale_revision_is_refused_and_writes_nothing(tmp_path):
    program = _program(tmp_path)
    _save(program)
    first = persistence.load_program(program.homeDir)
    _save(first.model_copy(update={"description": "from the other tab"}))
    metadata = Path(program.homeDir) / ".debasher" / "program.json"
    before = metadata.read_text()

    detail = _conflict(lambda: _save(first.model_copy(update={"description": "from this tab"})))

    assert detail["revision"] == 2
    assert "changed on disk" in detail["message"]
    assert metadata.read_text() == before


def test_a_save_that_changes_nothing_keeps_the_revision_whatever_it_names(tmp_path):
    program = _program(tmp_path)
    _save(program)
    _save(persistence.load_program(program.homeDir).model_copy(update={"description": "x"}))

    stale_but_same = program.model_copy(update={"description": "x", "revision": 0})

    assert _save(stale_but_same).revision == 2


def test_a_save_into_another_directory_replaces_what_is_there(tmp_path):
    other = _program(tmp_path, name="other", home="elsewhere")
    _save(other)
    _save(persistence.load_program(other.homeDir).model_copy(update={"description": "x"}))

    mine = _program(tmp_path)

    assert _save(mine, into=other.homeDir).revision == 3
    assert persistence.load_program(other.homeDir).name == "rev"
    assert not (Path(other.homeDir) / "other.sh").exists()


def test_metadata_saved_without_a_revision_is_at_revision_zero(tmp_path):
    program = _program(tmp_path)
    _save(program)
    metadata = Path(program.homeDir) / ".debasher" / "program.json"
    data = json.loads(metadata.read_text())
    del data["revision"]
    metadata.write_text(json.dumps(data))

    loaded = persistence.load_program(program.homeDir)

    assert loaded.revision == 0
    assert _save(loaded.model_copy(update={"description": "x"})).revision == 1


def test_a_program_that_script_generation_refuses_writes_nothing(tmp_path):
    program = _program(tmp_path)
    _save(program)
    metadata = Path(program.homeDir) / ".debasher" / "program.json"
    before = metadata.read_text()
    refused = program.model_copy(deep=True, update={"revision": 1})
    refused.processes[0].options = [
        ProgramOption(
            id="o", label="-n", direction="input", dataType="int", description="",
            value="cpus", commandLine=True, fromProcessSpec=True,
        )
    ]

    with pytest.raises(programs.HTTPException) as error:
        _save(refused)

    assert error.value.status_code == 400
    assert metadata.read_text() == before


def test_of_two_saves_arriving_together_on_one_revision_only_one_goes_through(tmp_path):
    program = _program(tmp_path)
    _save(program)
    loaded = persistence.load_program(program.homeDir)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def save(description):
        barrier.wait()
        try:
            _save(loaded.model_copy(update={"description": description}))
            outcomes.append("saved")
        except programs.HTTPException as error:
            outcomes.append(error.detail["code"])

    threads = [threading.Thread(target=save, args=(d,)) for d in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["revision", "saved"]
    assert persistence.load_program(program.homeDir).revision == 2


def test_what_saves_before_running_answers_with_the_revision_it_wrote(tmp_path, monkeypatch):
    tool = tmp_path / "debasher_exec"
    tool.write_text("#!/bin/sh\necho ok\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: tool if name == "debasher_exec" else None)
    program = _program(tmp_path)

    assert execution.validate_program(program).revision == 1
    assert execution.check_program_options(program).revision == 1

    changed = program.model_copy(update={"description": "changed"})
    with pytest.raises(execution.HTTPException) as refused:
        execution.validate_program(changed)
    assert refused.value.status_code == 409

    assert execution.validate_program(changed.model_copy(update={"revision": 1})).revision == 2


def _revision(home_dir: str):
    return programs.get_program_revision(programs.ProgramRevisionRequest(homeDir=home_dir)).revision


def test_the_revision_is_read_without_loading_the_program(tmp_path):
    program = _program(tmp_path)
    _save(program)
    assert _revision(program.homeDir) == 1

    loaded = persistence.load_program(program.homeDir)
    _save(loaded.model_copy(update={"description": "changed"}))

    assert _revision(program.homeDir) == 2


def test_a_directory_with_no_program_metadata_has_no_revision(tmp_path):
    assert _revision(str(tmp_path)) is None
    assert _revision(str(tmp_path / "missing")) is None


def test_the_revision_of_a_blank_home_directory_is_refused(tmp_path):
    with pytest.raises(programs.HTTPException) as refused:
        _revision("  ")
    assert refused.value.status_code == 400
