"""
The digest of the artifact (see "Loading, saving and the local state" in
doc/design_doc_webui.md): loading gives the program the digest of the files
it read, a save into the program's own home directory is refused when the
artifact there holds another digest than the one the program names, so
that a tab or an agent never overwrites what another wrote since, by any
means. A save that changes nothing keeps the digest, and a program that
script generation refuses writes nothing. The program metadata of before
the artifact is read when a home directory holds no topology file, and
replaced by the artifact at the next save; the output directory is local
state.
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
    assert refused.value.detail["code"] == "digest"
    return refused.value.detail


def _artifact_files(home_dir: str) -> dict[str, str]:
    home = Path(home_dir)
    return {str(path.relative_to(home)): path.read_text() for path in home.rglob("*") if path.is_file()}


# --- the artifact on disk ------------------------------------------------------


def test_a_save_writes_the_topology_file_the_process_files_and_the_script(tmp_path):
    program = _program(tmp_path)

    saved = _save(program)

    home = Path(program.homeDir)
    assert saved.path == str(home / "program.yaml")
    assert (home / "program.yaml").read_text().startswith("# yaml-language-server:")
    assert "name: rev" in (home / "program.yaml").read_text()
    assert (home / "step.sh").read_text() == "step()\n{\n    :\n}\n"
    assert (home / "rev.sh").is_file()
    assert not (home / ".debasher" / "program.json").exists()
    assert json.loads((home / ".debasher" / "local.json").read_text()) == {"outputDir": str(tmp_path / "out")}


def test_loading_gives_the_program_back_with_its_digest_and_its_local_output_directory(tmp_path):
    program = _program(tmp_path)
    saved = _save(program)

    loaded = persistence.load_program(program.homeDir)

    assert loaded.name == "rev"
    assert loaded.processes[0].code == "step()\n{\n    :\n}"
    assert loaded.processes[0].files.code == "step.sh"
    assert loaded.homeDir == str(Path(program.homeDir).resolve())
    assert loaded.outputDir == str(tmp_path / "out")
    assert loaded.digest == saved.digest
    assert loaded.digest


def test_every_save_that_changes_the_program_changes_its_digest(tmp_path):
    program = _program(tmp_path)

    first = _save(program).digest
    loaded = persistence.load_program(program.homeDir)
    assert loaded.digest == first

    second = _save(loaded.model_copy(update={"description": "changed"})).digest
    assert second != first
    assert persistence.load_program(program.homeDir).digest == second


def test_a_file_a_process_was_loaded_with_is_written_back_where_it_was(tmp_path):
    program = _program(tmp_path)
    _save(program)
    home = Path(program.homeDir)
    (home / "src").mkdir()
    (home / "src" / "work.sh").write_text("step()\n{\n    echo work\n}\n")
    (home / "step.sh").unlink()
    text = (home / "program.yaml").read_text().replace("code: step.sh", "code: src/work.sh")
    (home / "program.yaml").write_text(text)
    loaded = persistence.load_program(program.homeDir)
    assert loaded.processes[0].code == "step()\n{\n    echo work\n}"

    loaded.processes[0].code = "step()\n{\n    echo more\n}"
    _save(loaded)

    assert (home / "src" / "work.sh").read_text() == "step()\n{\n    echo more\n}\n"
    assert not (home / "step.sh").exists()
    assert "code: src/work.sh" in (home / "program.yaml").read_text()


def test_a_file_that_holds_what_it_should_is_not_written_again(tmp_path):
    program = _program(tmp_path)
    _save(program)
    step = Path(program.homeDir) / "step.sh"
    before = step.stat().st_mtime_ns
    loaded = persistence.load_program(program.homeDir)

    _save(loaded.model_copy(update={"description": "changed"}))

    assert step.stat().st_mtime_ns == before


# --- the digest as a guard -------------------------------------------------------


def test_a_save_on_a_stale_digest_is_refused_and_writes_nothing(tmp_path):
    program = _program(tmp_path)
    _save(program)
    first = persistence.load_program(program.homeDir)
    other = _save(first.model_copy(update={"description": "from the other tab"}))
    before = _artifact_files(program.homeDir)

    detail = _conflict(lambda: _save(first.model_copy(update={"description": "from this tab"})))

    assert detail["digest"] == other.digest
    assert "changed on disk" in detail["message"]
    assert _artifact_files(program.homeDir) == before


def test_a_file_edited_by_hand_refuses_a_save_until_the_program_is_loaded_again(tmp_path):
    program = _program(tmp_path)
    _save(program)
    loaded = persistence.load_program(program.homeDir)
    step = Path(program.homeDir) / "step.sh"
    step.write_text("step()\n{\n    echo edited by hand\n}\n")

    _conflict(lambda: _save(loaded.model_copy(update={"description": "from this tab"})))

    reloaded = persistence.load_program(program.homeDir)
    assert reloaded.processes[0].code == "step()\n{\n    echo edited by hand\n}"
    _save(reloaded.model_copy(update={"description": "from this tab"}))
    assert "echo edited by hand" in step.read_text()


def test_a_save_that_changes_nothing_keeps_the_digest_whatever_it_names(tmp_path):
    program = _program(tmp_path)
    _save(program)
    changed = _save(persistence.load_program(program.homeDir).model_copy(update={"description": "x"}))

    stale_but_same = program.model_copy(update={"description": "x", "digest": "stale"})

    assert _save(stale_but_same).digest == changed.digest


def test_a_save_into_another_directory_replaces_what_is_there(tmp_path):
    other = _program(tmp_path, name="other", home="elsewhere")
    _save(other)
    _save(persistence.load_program(other.homeDir).model_copy(update={"description": "x"}))

    mine = _program(tmp_path)

    _save(mine, into=other.homeDir)
    assert persistence.load_program(other.homeDir).name == "rev"
    assert not (Path(other.homeDir) / "other.sh").exists()


def test_a_program_that_script_generation_refuses_writes_nothing(tmp_path):
    program = _program(tmp_path)
    saved = _save(program)
    before = _artifact_files(program.homeDir)
    refused = program.model_copy(deep=True, update={"digest": saved.digest})
    refused.processes[0].options = [
        ProgramOption(
            id="o", label="-n", direction="input", dataType="int", description="",
            value="cpus", commandLine=True, fromProcessSpec=True,
        )
    ]

    with pytest.raises(programs.HTTPException) as error:
        _save(refused)

    assert error.value.status_code == 400
    assert _artifact_files(program.homeDir) == before


def test_of_two_saves_arriving_together_on_one_digest_only_one_goes_through(tmp_path):
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

    assert sorted(outcomes) == ["digest", "saved"]
    assert persistence.load_program(program.homeDir).description in ("one", "two")


def test_what_saves_before_running_answers_with_the_digest_it_wrote(tmp_path, monkeypatch):
    tool = tmp_path / "debasher_exec"
    tool.write_text("#!/bin/sh\necho ok\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: tool if name == "debasher_exec" else None)
    program = _program(tmp_path)

    first = execution.validate_program(program).digest
    assert first == persistence.saved_digest(program.homeDir)
    assert execution.check_program_options(program).digest == first

    changed = program.model_copy(update={"description": "changed"})
    with pytest.raises(execution.HTTPException) as refused:
        execution.validate_program(changed)
    assert refused.value.status_code == 409

    assert execution.validate_program(changed.model_copy(update={"digest": first})).digest != first


def _digest(home_dir: str):
    return programs.get_program_digest(programs.ProgramDigestRequest(homeDir=home_dir)).digest


def test_the_digest_is_read_without_loading_the_program(tmp_path):
    program = _program(tmp_path)
    first = _save(program).digest
    assert _digest(program.homeDir) == first

    loaded = persistence.load_program(program.homeDir)
    second = _save(loaded.model_copy(update={"description": "changed"})).digest

    assert _digest(program.homeDir) == second != first


def test_a_directory_with_no_program_has_no_digest(tmp_path):
    assert _digest(str(tmp_path)) is None
    assert _digest(str(tmp_path / "missing")) is None


def test_the_digest_of_a_blank_home_directory_is_refused(tmp_path):
    with pytest.raises(programs.HTTPException) as refused:
        _digest("  ")
    assert refused.value.status_code == 400


def test_a_topology_file_that_cannot_be_read_still_has_a_digest_and_is_refused_on_load(tmp_path):
    program = _program(tmp_path)
    _save(program)
    (Path(program.homeDir) / "program.yaml").write_text("schema_version: 1\nname: rev\nname: twice\n")

    assert _digest(program.homeDir)
    with pytest.raises(programs.HTTPException) as refused:
        programs.load_program_from_dir(programs.LoadProgramRequest(inputDir=program.homeDir))
    assert refused.value.status_code == 400
    assert "given twice" in refused.value.detail


# --- the program metadata of before the artifact ---------------------------------


def _write_metadata(program: Program) -> Path:
    metadata = Path(program.homeDir) / ".debasher" / "program.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(program.model_copy(update={"homeDir": ""}).model_dump_json(indent=2))
    return metadata


def test_program_metadata_is_loaded_when_there_is_no_topology_file(tmp_path):
    program = _program(tmp_path)
    _write_metadata(program)

    loaded = persistence.load_program(program.homeDir)

    assert loaded.name == "rev"
    assert loaded.homeDir == str(Path(program.homeDir).resolve())
    assert loaded.outputDir == str(tmp_path / "out")
    assert loaded.digest == _digest(program.homeDir)


def test_the_first_save_replaces_the_program_metadata_with_the_artifact(tmp_path):
    program = _program(tmp_path)
    metadata = _write_metadata(program)
    loaded = persistence.load_program(program.homeDir)

    _save(loaded.model_copy(update={"description": "migrated"}))

    home = Path(program.homeDir)
    assert not metadata.exists()
    assert (home / "program.yaml").is_file()
    assert (home / "step.sh").is_file()
    assert persistence.load_program(program.homeDir).description == "migrated"


def test_program_metadata_changed_since_it_was_loaded_refuses_the_save(tmp_path):
    program = _program(tmp_path)
    metadata = _write_metadata(program)
    loaded = persistence.load_program(program.homeDir)
    metadata.write_text(program.model_copy(update={"description": "by hand"}).model_dump_json())

    _conflict(lambda: _save(loaded.model_copy(update={"description": "from this tab"})))

    assert metadata.exists()


def test_a_save_into_a_directory_with_program_metadata_of_another_program_replaces_it(tmp_path):
    other = _program(tmp_path, name="other", home="elsewhere")
    _write_metadata(other)

    _save(_program(tmp_path), into=other.homeDir)

    assert not (Path(other.homeDir) / ".debasher" / "program.json").exists()
    assert persistence.load_program(other.homeDir).name == "rev"


# --- the local state ---------------------------------------------------------------


def test_the_output_directory_is_local_state_that_a_copied_program_does_not_carry(tmp_path):
    program = _program(tmp_path)
    _save(program)
    home = Path(program.homeDir)
    assert "out" not in (home / "program.yaml").read_text()

    copy = tmp_path / "copy"
    copy.mkdir()
    for path in home.iterdir():
        if path.name != ".debasher":
            (copy / path.name).write_text(path.read_text())

    assert persistence.load_program(str(copy)).outputDir == ""
    assert persistence.load_program(str(copy)).digest == persistence.load_program(program.homeDir).digest


def test_changing_the_output_directory_alone_is_saved(tmp_path):
    program = _program(tmp_path)
    _save(program)
    loaded = persistence.load_program(program.homeDir)

    saved = _save(loaded.model_copy(update={"outputDir": str(tmp_path / "other_out")}))

    assert saved.digest == loaded.digest
    assert persistence.load_program(program.homeDir).outputDir == str(tmp_path / "other_out")
    assert persistence.saved_output_dir(program.homeDir) == str(tmp_path / "other_out")
