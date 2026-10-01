"""
The program model of a resident program (see "The program model of a
resident program" in doc/design_doc_webui.md): the fields it adds, their
defaults for program metadata saved without them, and their round trip
through the program metadata.
"""

import json

import pytest

# The API reads and writes programs with pydantic 2 (api/requirements.txt).
# A pytest whose Python has an older one, such as that of the system, skips
# this module instead of failing it.
import pydantic  # noqa: E402

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip(
        f"the API needs pydantic 2, and the Python of this pytest has {pydantic.VERSION}: "
        "create the virtual environment of api/README.md, install pytest into it, and "
        "run ./configure PYTEST=<venv>/bin/pytest",
        allow_module_level=True,
    )

from api import persistence
from api.models import (
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    NodeCode,
    OptionsHandler,
    Position,
    Program,
    ProgramOption,
    ProgramProcess,
)
from api.script_generation import generate_script


def _process(name, **fields):
    defaults = {
        "id": f"id-{name}",
        "name": name,
        "description": "",
        "position": Position(x=0, y=0),
        "options": [],
        "optionsHandler": OptionsHandler(mode="standard"),
        "language": "python",
        "code": "",
        "computationalSpecs": ComputationalSpecs(),
        "additionalSpecs": AdditionalSpecs(force=False),
    }
    return ProgramProcess(**{**defaults, **fields})


def _program(processes, **fields):
    return Program(
        id="prog",
        name="relay",
        preamble="",
        envVars={},
        outputDir="",
        executionOptions=ExecutionOptions(scheduler="BUILTIN"),
        programOptions={},
        processes=processes,
        edges=[],
        **fields,
    )


def _resident_program():
    counter = _process(
        "counter",
        nodeKind="FBPProcess",
        initiator=True,
        nodeCode=NodeCode(
            preamble="import os",
            classBody="def __init__(self):\n    super().__init__()\n    self.count = 0",
            processData="self.count += 1\nself.send_data(\"outf\", self.count)",
        ),
        computationalSpecs=ComputationalSpecs(cpus=1, input_log_max_mb=50, startup_timeout_s=30),
    )
    counter.options = [
        ProgramOption(
            id="in",
            label="-inf",
            direction="input",
            dataType="string",
            channel="fifo",
            fifoTag="external",
            description="",
            value="counter_in",
            commandLine=False,
        ),
    ]
    sup = _process(
        "sup",
        nodeKind="Supervisor",
        computationalSpecs=ComputationalSpecs(heartbeat_timeout_s=20),
    )
    return _program([counter, sup], programType="resident")


def test_program_metadata_saved_without_the_fields_is_a_general_program(tmp_path):
    saved = json.loads(_program([_process("count")]).model_dump_json())
    del saved["programType"]
    for process in saved["processes"]:
        for field in ("nodeKind", "initiator", "nodeCode"):
            del process[field]
    metadata = tmp_path / ".debasher" / "program.json"
    metadata.parent.mkdir()
    metadata.write_text(json.dumps(saved))

    program = persistence.load_program(str(tmp_path))

    assert program.programType == "general"
    process = program.processes[0]
    assert process.nodeKind is None
    assert process.initiator is False
    assert process.nodeCode is None


def test_a_resident_program_keeps_what_it_adds_in_its_metadata(tmp_path):
    program = _resident_program()

    persistence.save(str(tmp_path), program)
    loaded = persistence.load_program(str(tmp_path))

    assert loaded.programType == "resident"
    counter, sup = loaded.processes
    assert counter.nodeKind == "FBPProcess"
    assert counter.initiator is True
    assert counter.nodeCode == program.processes[0].nodeCode
    assert counter.options[0].fifoTag == "external"
    assert counter.computationalSpecs.input_log_max_mb == 50
    assert counter.computationalSpecs.startup_timeout_s == 30
    assert sup.nodeKind == "Supervisor"
    assert sup.nodeCode is None
    assert sup.computationalSpecs.heartbeat_timeout_s == 20


def test_the_script_of_a_resident_program_declares_its_type():
    assert 'debasher::program_type "resident"' in generate_script(_resident_program())
