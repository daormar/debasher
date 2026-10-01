"""
The backend refuses to change a program under a run in progress (see "The
home directory" and "The output directory" in doc/design_doc_webui.md):
saving, which writes the generated script that the processes of a run read
each time one starts, running, validating or checking the options of a
program, which save it first, and resetting the output directory, whose
files the processes of a run may still use. A save that changes the output
directory is refused too while a run is in progress in the old one.
"""

import stat
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
    ProgramProcess,
)
from api.routers import execution, programs  # noqa: E402


def _program(tmp_path: Path, output_dir: str = "out") -> Program:
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
        id="p",
        name="guarded",
        preamble="",
        envVars={},
        homeDir=str(tmp_path / "home"),
        outputDir=str(tmp_path / output_dir),
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=[step],
        edges=[],
    )


@pytest.fixture
def running_in(tmp_path, monkeypatch):
    """
    A fake debasher_status that reports a run in progress in the directories
    added to the returned set, and none elsewhere; the other tools are not
    found.
    """
    running: set[str] = set()
    tool = tmp_path / "debasher_status"
    listing = tmp_path / "running"

    def write_listing():
        listing.write_text("".join(f"{d}\n" for d in running))

    tool.write_text(f'#!/bin/sh\ngrep -qxF -- "$2" "{listing}" && exit 2\nexit 3\n')
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    write_listing()
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: tool if name == "debasher_status" else None)

    class Running:
        def add(self, directory):
            running.add(str(directory))
            write_listing()

    return Running()


def _save(program: Program):
    return programs.save_program_to_dir(programs.SaveProgramRequest(outputDir=program.homeDir, program=program))


def _refused(call):
    with pytest.raises(execution.HTTPException) as refused:
        call()
    assert refused.value.status_code == 409
    return refused.value.detail


def test_a_save_goes_through_with_no_run_in_progress(tmp_path, running_in):
    program = _program(tmp_path)

    _save(program)

    assert persistence.load_program(program.homeDir).name == "guarded"


def test_a_save_is_refused_while_a_run_is_in_progress_in_the_output_directory(tmp_path, running_in):
    program = _program(tmp_path)
    _save(program)
    script = Path(program.homeDir) / "guarded.sh"
    before = script.read_text()
    running_in.add(program.outputDir)

    changed = program.model_copy(update={"description": "changed"})

    assert "run is in progress" in _refused(lambda: _save(changed))
    assert script.read_text() == before
    assert persistence.load_program(program.homeDir).description == ""


def test_a_save_that_changes_the_output_directory_is_refused_while_the_old_one_runs(tmp_path, running_in):
    program = _program(tmp_path)
    _save(program)
    running_in.add(program.outputDir)

    moved = program.model_copy(update={"outputDir": str(tmp_path / "elsewhere")})

    assert str(tmp_path / "out") in _refused(lambda: _save(moved))


@pytest.mark.parametrize(
    "call",
    [execution.validate_program, execution.check_program_options, execution.run_program],
    ids=["validate", "check-options", "run"],
)
def test_what_saves_before_running_is_refused_while_a_run_is_in_progress(tmp_path, running_in, call):
    program = _program(tmp_path)
    running_in.add(program.outputDir)

    _refused(lambda: call(program))

    assert not (Path(program.homeDir) / "guarded.sh").exists()


def test_a_reset_of_the_output_directory_is_refused_while_a_run_is_in_progress(tmp_path, running_in):
    program = _program(tmp_path)
    left = Path(program.outputDir) / "left_by_a_run"
    left.parent.mkdir(parents=True)
    left.write_text("still in use")
    running_in.add(program.outputDir)

    _refused(lambda: execution.reset_output_dir(program))

    assert left.read_text() == "still in use"
