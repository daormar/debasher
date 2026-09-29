"""
Launching and stopping a program from the web UI (see "Launching a run" and
"Running a resident program" in doc/design_doc_webui.md): the debasher_exec
command of a general and of a resident program; the launch of a resident
program, which /run waits for, in a session of its own and with its output
in the run log, and whose failure it reports at once; the program state
that tells a program never launched from one stopped; and the orderly stop
and the hard kill of a resident program.
"""

import os
import stat
import subprocess
import sys
import time

import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (the API's own requirements live in the
# project's virtualenv, see api/README.md).
pytest.importorskip("fastapi")

# The API reads and writes programs with pydantic 2 (api/requirements.txt).
import pydantic  # noqa: E402

if int(pydantic.VERSION.split(".")[0]) < 2:
    pytest.skip(
        f"the API needs pydantic 2, and the Python of this pytest has {pydantic.VERSION}: "
        "create the virtual environment of api/README.md, install pytest into it, and "
        "run ./configure PYTEST=<venv>/bin/pytest",
        allow_module_level=True,
    )

from api import paths, program_state, tool_sessions  # noqa: E402
from api.models import (  # noqa: E402
    AdditionalSpecs,
    ComputationalSpecs,
    ExecutionOptions,
    NodeCode,
    OptionsHandler,
    Position,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
)
from api.routers import execution  # noqa: E402

_ALL_EXECUTION_OPTIONS = ExecutionOptions(
    scheduler="SLURM",
    builtinSchedCpus="4",
    builtinSchedMem="2G",
    dfltNodes="node01",
    dfltThrottle="2",
    rerunOutdatedProcs=True,
    condaSupport=True,
    dockerSupport=True,
)

_NODE_CODE = NodeCode(
    processData=(
        "for line in data.splitlines():\n"
        "    self.send(\"-outf\", line)"
    ),
    captureNodeState="return {}",
    restoreNodeState="pass",
    initializeRuntime="pass",
)


def _option(option_id, label, direction, **fields):
    defaults = {
        "id": option_id,
        "label": label,
        "direction": direction,
        "dataType": "string",
        "description": label,
        "value": "",
        "commandLine": False,
    }
    return ProgramOption(**{**defaults, **fields})


def _process(name, kind, options=(), **fields):
    defaults = {
        "id": name,
        "name": name,
        "description": f"the {name} node",
        "position": Position(x=0, y=0),
        "options": list(options),
        "optionsHandler": OptionsHandler(mode="standard"),
        "language": "python",
        "code": "",
        "computationalSpecs": ComputationalSpecs(cpus=1, mem=32, time="00:10:00"),
        "additionalSpecs": AdditionalSpecs(force=False),
        "nodeKind": kind,
        "nodeCode": None if kind == "Supervisor" else _NODE_CODE.model_copy(),
    }
    return ProgramProcess(**{**defaults, **fields})


def _relay(tmp_path, *, with_supervisor=True, unreached_node=False, **program_fields):
    """Relay, an initiator with an external input, feeds Sink; with
    `unreached_node`, Lone is a node that no initiator reaches, which the
    engine refuses when it loads the program."""
    relay = _process(
        "Relay",
        "FBPProcess",
        [
            _option("r-ext", "-ext", "input", channel="fifo", fifoTag="external", value="relay_ext"),
            _option("r-outf", "-outf", "output", channel="fifo", value="relay_out"),
        ],
        initiator=True,
    )
    sink = _process("Sink", "FBPProcess", [_option("s-in", "-inf", "input", value="[Relay;-outf]")])
    processes = [relay, sink]
    if unreached_node:
        processes.append(_process("Lone", "FBPProcess"))
    if with_supervisor:
        processes.append(_process("Sup", "Supervisor"))
    defaults = {
        "id": "relay",
        "name": "relay",
        "programType": "resident",
        "preamble": "",
        "envVars": {},
        "homeDir": str(tmp_path / "home"),
        "outputDir": str(tmp_path / "out"),
        "executionOptions": ExecutionOptions(scheduler="BUILTIN"),
        "programOptions": {},
        "processes": processes,
        "edges": [
            ProgramEdge(
                id="r-outf->s-in",
                sourceProcessId="Relay",
                sourceOptionId="r-outf",
                targetProcessId="Sink",
                targetOptionId="s-in",
            )
        ],
    }
    return Program(**{**defaults, **program_fields})


def _general(tmp_path, **program_fields):
    process = _process(
        "Step",
        None,
        [_option("s-n", "-n", "input", dataType="int", commandLine=True)],
        language="bash",
        code="echo hello",
        nodeCode=None,
    )
    defaults = {
        "id": "gen",
        "name": "gen",
        "preamble": "",
        "envVars": {},
        "homeDir": str(tmp_path / "home"),
        "outputDir": str(tmp_path / "out"),
        "executionOptions": ExecutionOptions(scheduler="BUILTIN"),
        "programOptions": {},
        "processes": [process],
        "edges": [],
    }
    return Program(**{**defaults, **program_fields})


def _flags(command):
    """The command after `--pfile <script> --outdir <dir>`."""
    return command[5:]


# --- the command --------------------------------------------------------------


def test_a_general_program_is_given_every_execution_option_and_waited_for(tmp_path):
    program = _general(tmp_path, executionOptions=_ALL_EXECUTION_OPTIONS, programOptions={"-n": "3"})

    command = execution._prepare_debasher_exec_command(program, "--wait")

    assert _flags(command) == [
        "--sched", "SLURM",
        "--builtinsched-cpus", "4",
        "--builtinsched-mem", "2G",
        "--dflt-nodes", "node01",
        "--dflt-throttle", "2",
        "--rerun-outdated-procs",
        "--conda-support",
        "--docker-support",
        "--wait",
        "-n", "3",
    ]


def test_a_resident_program_gets_the_built_in_scheduler_and_its_limits_only(tmp_path):
    program = _relay(tmp_path, executionOptions=_ALL_EXECUTION_OPTIONS)

    command = execution._prepare_debasher_exec_command(program, None)

    assert _flags(command) == [
        "--sched", "BUILTIN",
        "--builtinsched-cpus", "4",
        "--builtinsched-mem", "2G",
    ]


def test_the_flag_of_the_supervisor_is_given_alone_when_set(tmp_path):
    program = _relay(tmp_path, programOptions={"-no-hold-fifos": "true"})

    command = execution._prepare_debasher_exec_command(program, None)

    assert _flags(command) == ["--sched", "BUILTIN", "-no-hold-fifos"]


def test_the_flag_of_the_supervisor_is_left_out_when_not_set(tmp_path):
    program = _relay(tmp_path, programOptions={"-no-hold-fifos": ""})

    command = execution._prepare_debasher_exec_command(program, None)

    assert _flags(command) == ["--sched", "BUILTIN"]


# --- the session and the output of a tool -------------------------------------

_REPORT_SESSION_AND_OUTPUT = (
    "import os, stat, sys\n"
    "print(os.getsid(0))\n"
    "print(stat.S_ISFIFO(os.fstat(1).st_mode))\n"
    "print('to stderr', file=sys.stderr)\n"
    "sys.exit(3)\n"
)


def test_a_tool_runs_in_a_session_of_its_own_and_writes_into_a_file(tmp_path):
    output_path = tmp_path / "tool.log"

    exit_code = tool_sessions.run_in_own_session(
        [sys.executable, "-u", "-c", _REPORT_SESSION_AND_OUTPUT], dict(os.environ), output_path
    )

    session, is_pipe, stderr_line = output_path.read_text().splitlines()
    assert exit_code == 3
    assert int(session) != os.getsid(0)
    assert is_pipe == "False"
    assert stderr_line == "to stderr"


def test_a_tool_with_a_temporary_output_file_leaves_no_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(tool_sessions.tempfile, "tempdir", str(tmp_path))

    output, exit_code = tool_sessions.run_with_temp_output(
        [sys.executable, "-u", "-c", _REPORT_SESSION_AND_OUTPUT], dict(os.environ)
    )

    assert exit_code == 3
    assert output.splitlines()[2] == "to stderr"
    assert list(tmp_path.iterdir()) == []


# --- program state --------------------------------------------------------------


def _exec_dir(outdir, process, *entries):
    exec_dir = outdir / "__exec__" / process
    exec_dir.mkdir(parents=True)
    for entry in entries:
        (exec_dir / entry).write_text("")


def test_an_output_directory_never_launched_has_no_program_state(tmp_path):
    assert not program_state.has_program_state(str(tmp_path / "missing"))
    assert not program_state.has_program_state(str(tmp_path))


def test_the_files_of_the_engine_alone_are_no_program_state(tmp_path):
    _exec_dir(tmp_path, "Relay", "Relay.opts", "Relay.stdout", "Relay.finished", "node_info")

    assert not program_state.has_program_state(str(tmp_path))


@pytest.mark.parametrize("entry", ["checkpoints", "log", "halted", "checkpoints_3", "log_0"])
def test_what_a_node_keeps_in_its_exec_directory_is_program_state(tmp_path, entry):
    _exec_dir(tmp_path, "Relay", "Relay.opts", entry)

    assert program_state.has_program_state(str(tmp_path))


def test_the_output_directory_of_a_process_is_program_state(tmp_path):
    _exec_dir(tmp_path, "Relay", "Relay.opts")
    (tmp_path / "Relay").mkdir()

    assert program_state.has_program_state(str(tmp_path))


# --- /run of a resident program -------------------------------------------------


def _fake_debasher_exec(tmp_path, monkeypatch, body):
    tool = tmp_path / "debasher_exec"
    tool.write_text(f"#!/bin/sh\n{body}\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: tool if name == "debasher_exec" else None)
    monkeypatch.setattr(execution, "_get_program_state", lambda program: ("unfinished", ""))


def test_a_resident_launch_answers_with_the_exit_code_and_output(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, 'echo "refused: $*"\nexit 1')
    program = _relay(tmp_path)

    response = execution.run_program(program)

    assert response.started is False
    assert response.exitCode == 1
    assert response.output.startswith("refused: --pfile")
    assert "--wait" not in response.output
    assert (tmp_path / "out" / ".debasher_webui_run.log").read_text() == response.output


def test_a_resident_launch_that_ends_with_0_has_started(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)

    response = execution.run_program(program)

    assert response.started is True
    assert response.exitCode == 0
    assert response.output == "launched\n"


# --- a launch with the engine ---------------------------------------------------

_DEBASHER_EXEC = paths.find_bin_tool("debasher_exec")
_needs_engine = pytest.mark.skipif(_DEBASHER_EXEC is None, reason="debasher_exec not installed: run make install")


@_needs_engine
def test_a_launch_that_the_engine_refuses_is_reported_at_once(tmp_path):
    program = _relay(tmp_path, unreached_node=True)

    response = execution.run_program(program)

    assert response.started is False
    assert response.exitCode != 0
    assert "no round can reach Lone" in response.output


def _wait_for_statuses(program, expected, timeout_secs=30):
    deadline = time.monotonic() + timeout_secs
    while True:
        output, _ = execution._run_debasher_dir_tool(program, "debasher_status")
        statuses = execution._parse_process_statuses(output)
        if set(statuses.values()) == {expected} or time.monotonic() > deadline:
            return statuses
        time.sleep(0.5)


def _hard_kill(program):
    subprocess.run(
        [str(paths.find_bin_tool("debasher_stop")), "-d", program.outputDir],
        capture_output=True,
        timeout=60,
    )


@_needs_engine
def test_a_resident_program_is_launched_and_the_launch_ends(tmp_path):
    program = _relay(tmp_path)

    response = execution.run_program(program)

    try:
        assert response.exitCode == 0, response.output
        statuses = _wait_for_statuses(program, "IN-PROGRESS")
        assert statuses == {"Relay": "IN-PROGRESS", "Sink": "IN-PROGRESS", "Sup": "IN-PROGRESS"}
    finally:
        _hard_kill(program)


@_needs_engine
def test_a_resident_program_is_stopped_in_order_and_keeps_its_state(tmp_path):
    program = _relay(tmp_path)
    assert not execution.get_process_statuses(program).hasProgramState

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        response = execution.stop_program(program)

        assert response.exitCode == 0, response.output
        assert "stopped cleanly" in response.output
        statuses = execution.get_process_statuses(program)
        assert set(statuses.statuses.values()) == {"FINISHED"}
        assert statuses.hasProgramState
    finally:
        _hard_kill(program)


@_needs_engine
def test_a_resident_program_is_killed_at_once(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        response = execution.kill_program(program)

        assert response.exitCode == 0, response.output
        statuses = execution.get_process_statuses(program)
        assert "IN-PROGRESS" not in statuses.statuses.values()
        assert set(statuses.statuses.values()) != {"FINISHED"}
        assert statuses.hasProgramState
    finally:
        _hard_kill(program)
