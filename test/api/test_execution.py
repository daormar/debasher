"""
Launching and stopping a program from the web UI (see "Launching a run" and
"Running a resident program" in doc/design_doc_webui.md): the debasher_exec
command of a general and of a resident program; the launch of a resident
program, which /run waits for, in a session of its own and with its output
in the run log, and whose failure it reports at once; the program state
that tells a program never launched from one stopped, and "Reset program
state", which takes it away; the launch record, against which a launch on
program state compares the program; the orderly stop and
the hard kill of a resident program; "Restart node", a crash of the node
that the Supervisor relaunches, or the backend without a Supervisor, as
"Relaunch node" does under the relaunch lock; and the snapshots, one round
at a time or periodically from the launch.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

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

from api import launch_record, node_relaunch, paths, persistence, program_state, tool_sessions  # noqa: E402
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


def test_a_general_program_is_given_every_execution_option(tmp_path):
    program = _general(tmp_path, executionOptions=_ALL_EXECUTION_OPTIONS, programOptions={"-n": "3"})

    command = execution._prepare_debasher_exec_command(program, None)

    assert _flags(command) == [
        "--sched", "SLURM",
        "--builtinsched-cpus", "4",
        "--builtinsched-mem", "2G",
        "--dflt-nodes", "node01",
        "--dflt-throttle", "2",
        "--rerun-outdated-procs",
        "--conda-support",
        "--docker-support",
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


def test_what_a_process_left_in_its_output_directory_is_program_state(tmp_path):
    _exec_dir(tmp_path, "Relay", "Relay.opts")
    (tmp_path / "Relay").mkdir()
    (tmp_path / "Relay" / "result").write_text("")

    assert program_state.has_program_state(str(tmp_path))


def test_an_empty_output_directory_of_a_process_is_no_program_state(tmp_path):
    _exec_dir(tmp_path, "Relay", "Relay.opts")
    (tmp_path / "Relay").mkdir()

    assert not program_state.has_program_state(str(tmp_path))


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
        # A round leaves checkpoints: program state, which the next launch
        # resumes.
        assert execution.take_snapshot(program).exitCode == 0

        response = execution.kill_program(program)

        assert response.exitCode == 0, response.output
        statuses = execution.get_process_statuses(program)
        assert "IN-PROGRESS" not in statuses.statuses.values()
        assert set(statuses.statuses.values()) != {"FINISHED"}
        assert statuses.hasProgramState
    finally:
        _hard_kill(program)


def _node_pid(program, process):
    pid_file = Path(program.outputDir) / "__exec__" / process / f"{process}.id"
    try:
        return pid_file.read_text().strip()
    except FileNotFoundError:
        return None


@_needs_engine
def test_a_restarted_node_is_relaunched_by_the_supervisor(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        first_pid = _node_pid(program, "Sink")

        response = execution.restart_node(execution.StopProcessRequest(program=program, processName="Sink"))

        assert response.exitCode == 0, response.output
        deadline = time.monotonic() + 60
        while _node_pid(program, "Sink") in (first_pid, None) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert _node_pid(program, "Sink") not in (first_pid, None)
        statuses = _wait_for_statuses(program, "IN-PROGRESS")
        assert statuses == {"Relay": "IN-PROGRESS", "Sink": "IN-PROGRESS", "Sup": "IN-PROGRESS"}
    finally:
        _hard_kill(program)


@_needs_engine
@pytest.mark.parametrize("flag_value, expected", [("true", True), ("", False)])
def test_the_launch_says_whether_the_supervisor_holds_the_fifos(tmp_path, flag_value, expected):
    program = _relay(tmp_path, programOptions={"-no-hold-fifos": flag_value})

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        # The tab may hold other program options than those of the launch.
        edited = program.model_copy(update={"programOptions": {}})
        response = execution.launched_with_no_hold_fifos(edited)

        assert response.launchedWithNoHoldFifos is expected
    finally:
        _hard_kill(program)


def test_a_program_never_launched_or_without_a_supervisor_holds_its_fifos(tmp_path):
    assert not execution.launched_with_no_hold_fifos(_relay(tmp_path)).launchedWithNoHoldFifos
    assert not execution.launched_with_no_hold_fifos(
        _relay(tmp_path, with_supervisor=False)
    ).launchedWithNoHoldFifos


# --- snapshots ------------------------------------------------------------------


def _wait_for_text(path, text, timeout_secs=60):
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if path.exists() and text in path.read_text():
            return True
        time.sleep(0.5)
    return False


@_needs_engine
def test_a_snapshot_closes_a_round_at_every_node(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        response = execution.take_snapshot(program)

        assert response.exitCode == 0, response.output
        assert response.epoch is not None
        assert f"Round {response.epoch} closed at every node" in response.output
        assert response.pendingNodes == []
    finally:
        _hard_kill(program)


@_needs_engine
def test_the_launch_starts_periodic_snapshots_that_end_with_the_program(tmp_path):
    program = _relay(tmp_path, executionOptions=ExecutionOptions(scheduler="BUILTIN", snapshotEverySecs="2"))
    snapshot_log = tmp_path / "out" / ".debasher_webui_snapshots.log"

    try:
        assert execution.run_program(program).exitCode == 0

        assert _wait_for_text(snapshot_log, "closed at every node"), snapshot_log.read_text()

        assert execution.stop_program(program).exitCode == 0
        assert _wait_for_text(snapshot_log, "is running any more, no more rounds"), snapshot_log.read_text()
    finally:
        _hard_kill(program)


def test_a_snapshot_period_that_is_not_a_positive_number_launches_nothing(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, f"touch {tmp_path / 'launched'}")
    program = _relay(tmp_path, executionOptions=ExecutionOptions(scheduler="BUILTIN", snapshotEverySecs="0"))

    with pytest.raises(execution.HTTPException) as refused:
        execution.run_program(program)

    assert refused.value.status_code == 400
    assert not (tmp_path / "launched").exists()


def test_a_round_that_did_not_close_names_its_nodes(tmp_path, monkeypatch):
    output = (
        "Error: no checkpoint of round 1759000000123 or of a newer one at Sink Relay:1\n"
        "Warning: round 1759000000123 did not close at every node of out within 60s\n"
    )
    monkeypatch.setattr(execution, "_run_debasher_dir_tool_in_own_session", lambda program, tool: (output, 2))

    response = execution.take_snapshot(_relay(tmp_path))

    assert response.exitCode == 2
    assert response.epoch == 1759000000123
    assert response.pendingNodes == ["Sink", "Relay:1"]


# --- inspecting a node ----------------------------------------------------------------


def _inspect(program, process, command, **fields):
    return execution.inspect_node(
        execution.InspectNodeRequest(program=program, processName=process, command=command, **fields)
    )


def _write_external(program, fifo, payload):
    path = Path(program.outputDir) / "__fifos__" / "Relay" / fifo
    subprocess.run(
        ["bash", "-c", 'printf "%s\n" "$1" > "$2"', "_", f'{{"type": "DATA", "payload": {payload}}}', str(path)],
        check=True,
        timeout=30,
    )


@_needs_engine
def test_the_state_of_a_node_is_read_by_the_engine_tool(tmp_path):
    program = _relay(tmp_path)
    relay, sink = program.processes[:2]
    relay.nodeCode.processData = 'self.send_data("outf", packet)'
    sink.nodeCode.processData = "pass"

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        _write_external(program, "relay_ext", '"a1"')
        epoch = execution.take_snapshot(program).epoch
        assert epoch is not None

        summary = _inspect(program, "Relay", "summary")
        checkpoint = _inspect(program, "Relay", "checkpoint", epoch=epoch)
        every_port = _inspect(program, "Relay", "log")
        one_port = _inspect(program, "Relay", "log", port="ext")

        assert summary.error is None
        assert summary.result["task_state"] == "alive"
        assert [c["epoch"] for c in summary.result["checkpoints"]] == [epoch]
        assert checkpoint.result["readable"]
        assert checkpoint.result["epoch"] == epoch
        assert {r["port"] for r in every_port.result["records"]} == {"ext", "trigger"}
        assert [(r["port"], r["payload"]) for r in one_port.result["records"]] == [("ext", "a1")]
    finally:
        _hard_kill(program)


@_needs_engine
def test_an_error_of_the_engine_tool_comes_back_without_the_loading_lines(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        supervisor = _inspect(program, "Sup", "summary")
        no_checkpoint = _inspect(program, "Relay", "checkpoint", epoch=1)

        assert supervisor.result is None
        assert supervisor.error.startswith("Error: Sup is the Supervisor, which keeps no node state")
        assert "Loading module" not in supervisor.error
        assert "retains no checkpoint of epoch 1" in no_checkpoint.error
    finally:
        _hard_kill(program)


def test_a_checkpoint_is_asked_for_by_its_epoch(tmp_path):
    with pytest.raises(execution.HTTPException) as raised:
        _inspect(_relay(tmp_path), "Relay", "checkpoint")

    assert raised.value.status_code == 422


_WEBUI_PROGRAMS_DIR = Path(__file__).resolve().parents[2] / "data" / "webui_programs"


def _batch_launcher(tmp_path):
    """webui_batch_launcher, with webui_batch_greet, the general program that
    its launcher node runs, saved side by side, as it names it."""
    for name in ("webui_batch_launcher", "webui_batch_greet"):
        shutil.copytree(_WEBUI_PROGRAMS_DIR / name, tmp_path / name)
    program = persistence.load_program(str(tmp_path / "webui_batch_launcher"))
    program.outputDir = str(tmp_path / "out")
    return program


def _request(program, text, run):
    path = Path(program.outputDir) / "__fifos__" / "Launch" / "requests"
    line = json.dumps({"type": "DATA", "payload": {"opts": {"-text": text, "-secs": "0"}, "run": run}})
    subprocess.run(["bash", "-c", 'printf "%s\n" "$1" > "$2"', "_", line, str(path)], check=True, timeout=30)


@_needs_engine
def test_the_batch_runs_of_a_launcher_node_and_the_status_of_one(tmp_path):
    program = _batch_launcher(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        _request(program, "world", "r1")
        _request(program, "fail", "r2")

        def ended():
            runs = _inspect(program, "Launch", "runs").result["runs"]
            return [r["state"] for r in runs] == ["finished", "failed"]

        deadline = time.monotonic() + 60
        while not ended() and time.monotonic() < deadline:
            time.sleep(0.5)

        runs = _inspect(program, "Launch", "runs").result
        finished, failed = runs["runs"]
        status = execution.get_batch_run_status(
            execution.BatchRunStatusRequest(program=program, runDir=finished["run_dir"])
        )
        not_a_launcher = _inspect(program, "Report", "runs")

        assert [(r["run"], r["state"]) for r in runs["runs"]] == [("r1", "finished"), ("r2", "failed")]
        assert failed["exit_code"] != 0
        assert "PROCESS: greet ; STATUS: FINISHED" in status.output
        assert "not a launcher node" in not_a_launcher.error
    finally:
        _hard_kill(program)


# --- relaunching a node without a Supervisor ---------------------------------------


def _wait_for_new_pid(program, process, old_pid, timeout_secs=60):
    deadline = time.monotonic() + timeout_secs
    while _node_pid(program, process) in (old_pid, None) and time.monotonic() < deadline:
        time.sleep(0.5)
    return _node_pid(program, process)


def _node_request(program, process):
    return execution.StopProcessRequest(program=program, processName=process)


@_needs_engine
def test_relaunch_node_brings_a_downed_node_back(tmp_path):
    program = _relay(tmp_path, with_supervisor=False)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        relay_pid = _node_pid(program, "Relay")
        sink_pid = _node_pid(program, "Sink")

        nothing_down = execution.relaunch_node(_node_request(program, "Sink"))
        assert nothing_down.exitCode == 0
        assert nothing_down.relaunched == []
        assert _node_pid(program, "Sink") == sink_pid

        subprocess.run(
            [str(paths.find_bin_tool("debasher_stop")), "-d", program.outputDir, "-p", "Sink"],
            capture_output=True,
            timeout=60,
        )
        assert node_relaunch.wait_until_down(program.outputDir, "Sink")

        response = execution.relaunch_node(_node_request(program, "Sink"))

        assert response.exitCode == 0, response.output
        assert response.relaunched == ["Sink"]
        assert _wait_for_new_pid(program, "Sink", sink_pid) not in (sink_pid, None)
        assert _node_pid(program, "Relay") == relay_pid
        assert _wait_for_statuses(program, "IN-PROGRESS") == {"Relay": "IN-PROGRESS", "Sink": "IN-PROGRESS"}
    finally:
        _hard_kill(program)


@_needs_engine
def test_without_a_supervisor_a_restarted_node_is_relaunched_by_the_backend(tmp_path):
    program = _relay(tmp_path, with_supervisor=False)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        sink_pid = _node_pid(program, "Sink")

        response = execution.restart_node(_node_request(program, "Sink"))

        assert response.exitCode == 0, response.output
        assert response.relaunched == ["Sink"]
        assert _wait_for_new_pid(program, "Sink", sink_pid) not in (sink_pid, None)
        assert _wait_for_statuses(program, "IN-PROGRESS") == {"Relay": "IN-PROGRESS", "Sink": "IN-PROGRESS"}
    finally:
        _hard_kill(program)


def test_a_node_is_not_relaunched_by_hand_where_a_supervisor_relaunches_it(tmp_path):
    with pytest.raises(execution.HTTPException) as refused:
        execution.relaunch_node(_node_request(_relay(tmp_path), "Sink"))

    assert refused.value.status_code == 400


def _dead_pid():
    finished = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    return finished.stdout.strip()


def test_only_the_tasks_that_did_not_end_cleanly_and_whose_pid_is_gone_are_down(tmp_path):
    exec_dir = tmp_path / "__exec__" / "Work"
    exec_dir.mkdir(parents=True)
    (exec_dir / "Work_0.id").write_text(f"{os.getpid()}\n")
    (exec_dir / "Work_1.id").write_text(f"{_dead_pid()}\n")
    (exec_dir / "Work_2.id").write_text("not a pid\n")
    (exec_dir / "Work_3.id").write_text(f"{_dead_pid()}\n")
    (exec_dir / "Work_3.finished").write_text("")
    (exec_dir / "Work_10.opts").write_text("")

    tasks = node_relaunch._tasks(str(tmp_path), "Work")

    assert [(task.stem, task.index) for task in tasks] == [
        ("Work_0", 0), ("Work_1", 1), ("Work_2", 2), ("Work_3", 3)
    ]
    # Work_3 ended cleanly, as a node does in an orderly stop.
    assert [node_relaunch._is_down(task) for task in tasks] == [False, True, False, False]


_TRY_LOCK = (
    "import fcntl, sys\n"
    "f = open(sys.argv[1], 'a')\n"
    "try:\n"
    "    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "    print('locked')\n"
    "except BlockingIOError:\n"
    "    print('busy')\n"
)


def test_the_relaunch_lock_keeps_out_a_second_relaunch(tmp_path):
    lock_path = tmp_path / node_relaunch.RELAUNCH_LOCK_NAME

    def try_lock():
        return subprocess.run(
            [sys.executable, "-c", _TRY_LOCK, str(lock_path)], capture_output=True, text=True
        ).stdout.strip()

    with node_relaunch.relaunch_lock(str(tmp_path)):
        assert try_lock() == "busy"
    assert try_lock() == "locked"


# --- resetting the program state ------------------------------------------------


@_needs_engine
@pytest.mark.parametrize("delete", [False, True])
def test_a_reset_takes_the_program_state_away(tmp_path, delete):
    program = _relay(tmp_path)
    out = tmp_path / "out"

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        assert execution.take_snapshot(program).exitCode == 0

        with pytest.raises(execution.HTTPException) as refused:
            execution.reset_program_state(execution.ResetProgramStateRequest(program=program))
        assert refused.value.status_code == 409

        assert execution.stop_program(program).exitCode == 0
        assert execution.get_process_statuses(program).hasProgramState

        response = execution.reset_program_state(
            execution.ResetProgramStateRequest(program=program, delete=delete)
        )

        assert response.exitCode == 0, response.output
        assert not execution.get_process_statuses(program).hasProgramState
        set_aside = list((out / "__reset__").glob("*/__exec__/*/checkpoints")) if (out / "__reset__").exists() else []
        assert bool(set_aside) is not delete
    finally:
        _hard_kill(program)


def test_a_general_program_has_no_program_state_to_reset(tmp_path):
    with pytest.raises(execution.HTTPException) as refused:
        execution.reset_program_state(execution.ResetProgramStateRequest(program=_general(tmp_path)))

    assert refused.value.status_code == 400


@_needs_engine
def test_a_program_killed_before_it_kept_anything_starts_afresh(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")

        assert execution.kill_program(program).exitCode == 0

        assert not execution.get_process_statuses(program).hasProgramState
    finally:
        _hard_kill(program)


# --- the launch record ------------------------------------------------------------


def _with_program_state(tmp_path):
    _exec_dir(tmp_path / "out", "Relay", "checkpoints")


def _with_code(program, process_data):
    changed = program.model_copy(deep=True)
    changed.processes[1].nodeCode.processData = process_data
    return changed


def test_the_comparison_leaves_out_every_description(tmp_path):
    program = _relay(tmp_path)
    described = program.model_copy(deep=True)
    described.description = "a relay"
    described.processes[0].description = "relays what comes from outside"
    described.processes[0].options[0].description = "what comes from outside"

    assert launch_record.compared_script(described) == launch_record.compared_script(program)
    assert launch_record.compared_script(_with_code(program, "pass")) != launch_record.compared_script(program)


def test_a_launch_that_ends_well_leaves_its_record(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)

    assert execution.run_program(program).exitCode == 0

    record = launch_record.read(program.outputDir)
    assert record is not None
    assert not launch_record.differs(record, program, [])


def test_a_launch_that_fails_leaves_the_previous_record(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "exit 1")
    program = _relay(tmp_path)
    (tmp_path / "out").mkdir()
    launch_record.write(program.outputDir, program, [])
    _with_program_state(tmp_path)
    changed = _with_code(program, "pass")

    assert execution.run_program(changed, resumeChangedProgram=True).exitCode == 1

    assert launch_record.differs(launch_record.read(program.outputDir), changed, [])


def test_the_same_program_resumes_its_state_without_asking(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)
    assert execution.run_program(program).exitCode == 0
    _with_program_state(tmp_path)

    described = program.model_copy(deep=True)
    described.processes[1].description = "a new description"

    assert not execution.launch_check(described).needsConfirmation
    assert execution.run_program(described).exitCode == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda program: _with_code(program, "pass"),
        lambda program: program.model_copy(update={"programOptions": {"-no-hold-fifos": "true"}}),
    ],
    ids=["code", "program-options"],
)
def test_a_changed_program_asks_before_resuming_its_state(tmp_path, monkeypatch, change):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)
    assert execution.run_program(program).exitCode == 0
    _with_program_state(tmp_path)
    changed = change(program)

    check = execution.launch_check(changed)
    assert check.needsConfirmation and check.hasLaunchRecord

    with pytest.raises(execution.HTTPException) as refused:
        execution.run_program(changed)
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "launch-record", "hasLaunchRecord": True}

    assert execution.run_program(changed, resumeChangedProgram=True).exitCode == 0
    assert not execution.launch_check(changed).needsConfirmation


def test_program_state_with_no_record_asks_too(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)
    _with_program_state(tmp_path)

    check = execution.launch_check(program)
    assert check.needsConfirmation and not check.hasLaunchRecord

    with pytest.raises(execution.HTTPException) as refused:
        execution.run_program(program)
    assert refused.value.detail == {"code": "launch-record", "hasLaunchRecord": False}


def test_a_program_with_no_state_never_asks(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, "echo launched")
    program = _relay(tmp_path)
    assert execution.run_program(program).exitCode == 0

    changed = _with_code(program, "pass")

    assert not execution.launch_check(changed).needsConfirmation
    assert execution.run_program(changed).exitCode == 0


@_needs_engine
def test_a_resumed_program_is_compared_with_its_launch_record(tmp_path):
    program = _relay(tmp_path)

    try:
        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        assert execution.take_snapshot(program).exitCode == 0
        assert execution.stop_program(program).exitCode == 0

        assert execution.run_program(program).exitCode == 0
        _wait_for_statuses(program, "IN-PROGRESS")
        assert execution.stop_program(program).exitCode == 0

        with pytest.raises(execution.HTTPException) as refused:
            execution.run_program(_with_code(program, "pass"))
        assert refused.value.status_code == 409
    finally:
        _hard_kill(program)


# --- a general run that outlives the tab ------------------------------------------

# A stand-in for debasher_exec that validates at once, and otherwise says in
# which session it runs and with which arguments, and then lives a while, as
# the built-in scheduler does.
_REPORT_AND_LIVE = (
    'case "$*" in *--validate*) echo "$*" > "$(dirname "$0")/validated"; exit 0;; esac\n'
    'python3 -c "import os; print(os.getsid(0))" > "$(dirname "$0")/session"\n'
    'echo "$*" > "$(dirname "$0")/args"\n'
    "sleep 30\n"
)


def test_a_general_run_of_the_built_in_scheduler_is_started_detached_in_its_own_session(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, _REPORT_AND_LIVE)
    program = _general(tmp_path)

    started_at = time.monotonic()
    response = execution.run_program(program)

    try:
        assert time.monotonic() - started_at < 10
        assert response.started is True and response.exitCode is None
        assert "--validate" in (tmp_path / "validated").read_text()
        assert _wait_for_text(tmp_path / "args", "--sched BUILTIN")
        assert "--wait" not in (tmp_path / "args").read_text()
        assert "--validate" not in (tmp_path / "args").read_text()
        assert _wait_for_text(tmp_path / "session", "")
        assert int((tmp_path / "session").read_text()) != os.getsid(0)
    finally:
        subprocess.run(["pkill", "-f", str(tmp_path / "debasher_exec")])


def test_a_general_run_by_slurm_is_waited_for_and_its_failure_reported(tmp_path, monkeypatch):
    _fake_debasher_exec(tmp_path, monkeypatch, 'echo "sbatch refused: $*"\nexit 1')
    program = _general(tmp_path, executionOptions=ExecutionOptions(scheduler="SLURM"))

    response = execution.run_program(program)

    assert response.started is False
    assert response.exitCode == 1
    assert response.output.startswith("sbatch refused: --pfile")
    assert "--wait" not in response.output


def test_stopping_a_general_run_reports_the_exit_code_of_the_tool(tmp_path, monkeypatch):
    tool = tmp_path / "debasher_stop"
    tool.write_text('#!/bin/sh\necho "stopped $*"\n')
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(paths, "find_bin_tool", lambda name: tool if name == "debasher_stop" else None)

    response = execution.stop_program(_general(tmp_path))

    assert response.exitCode == 0
    assert response.output == f"stopped -d {tmp_path / 'out'}\n"


def test_a_general_program_that_the_engine_refuses_is_reported_before_anything_is_launched(tmp_path, monkeypatch):
    _fake_debasher_exec(
        tmp_path,
        monkeypatch,
        'case "$*" in *--validate*) echo "Error: option not found for process Step"; exit 1;; esac\n'
        f"touch {tmp_path / 'launched'}",
    )
    program = _general(tmp_path)

    response = execution.run_program(program)

    assert response.started is False
    assert response.exitCode == 1
    assert "option not found for process Step" in response.output
    assert not (tmp_path / "launched").exists()
