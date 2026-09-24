import os
import re
import signal
import subprocess
import threading
import time

import pytest

import debasher_runtime_lib as lib


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def execdir(tmp_path):
    # Mirrors the engine's own layout: __exec__/<name>/ per process, all
    # siblings under the same __exec__ parent.
    supervisor_dir = tmp_path / "__exec__" / "supervisor"
    supervisor_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def process_execdir(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(execdir / "__exec__" / "supervisor"))
    return execdir


def _node_dir(execdir, node_name):
    d = execdir / "__exec__" / node_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dead_pid():
    """A PID guaranteed to no longer exist: a child process, waited on
    (reaped) before returning its former pid."""
    child = subprocess.Popen(["true"])
    child.wait()
    return child.pid


class _Sup(lib.Supervisor):
    NODE_PORTS = {"a": "hb_a", "b": "hb_b"}


_FAKE_OPTS = {"hb_a": "/tmp/hb_a", "hb_b": "/tmp/hb_b"}


# --- port declaration --------------------------------------------------


def test_input_ports_covers_every_node_port():
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._input_ports() == {"a": "hb_a", "b": "hb_b"}


def test_input_ports_adds_the_manual_trigger_tag_when_configured():
    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a"}
        MANUAL_TRIGGER_PORT = "manual"

    proc = Sup(opts={"hb_a": "/tmp/hb_a", "manual": "/tmp/manual"})
    assert proc._input_ports() == {"a": "hb_a", lib._MANUAL_TRIGGER_TAG: "manual"}


def test_output_ports_covers_every_trigger_port():
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a", "init_b"]

    proc = Sup(opts={"init_a": "/tmp/a", "init_b": "/tmp/b"})
    assert proc._output_ports() == {"init_a": "init_a", "init_b": "init_b"}


def test_trigger_port_is_empty_by_default():
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._output_ports() == {}


def test_rejects_a_missing_declared_port():
    with pytest.raises(ValueError, match="hb_b"):
        _Sup(opts={"hb_a": "/tmp/hb_a"})


# --- ports from the engine ----------------------------------------------

_ENGINE_PORTS = "nodes=start=hb_start,worker:0=hb_w0,worker:1=hb_w1;trigger=trig;manual_trigger=manual"
_ENGINE_OPTS = {port: "/dev/null" for port in ("hb_start", "hb_w0", "hb_w1", "trig", "manual")}


class _UndeclaredSup(lib.Supervisor):
    HEARTBEAT_TIMEOUT_SECS = 3


def test_a_supervisor_run_by_the_engine_takes_its_ports_from_it(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_PORTS", _ENGINE_PORTS)
    proc = _UndeclaredSup(opts=_ENGINE_OPTS)
    assert proc.NODE_PORTS == {"start": "hb_start", ("worker", 0): "hb_w0", ("worker", 1): "hb_w1"}
    assert proc.TRIGGER_PORT == ["trig"]
    assert proc.MANUAL_TRIGGER_PORT == "manual"
    assert set(proc._last_heartbeat) == {"start", ("worker", 0), ("worker", 1)}
    # The class itself is left as it was.
    assert _UndeclaredSup.NODE_PORTS == {} and _UndeclaredSup.MANUAL_TRIGGER_PORT is None


def test_empty_fields_from_the_engine_give_a_supervisor_no_trigger(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_PORTS", "nodes=a=hb_a;trigger=;manual_trigger=")
    proc = _UndeclaredSup(opts={"hb_a": "/dev/null"})
    assert proc.NODE_PORTS == {"a": "hb_a"}
    assert proc.TRIGGER_PORT == []
    assert proc.MANUAL_TRIGGER_PORT is None


def test_a_supervisor_that_declares_ports_is_refused_when_the_engine_gives_them(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_PORTS", _ENGINE_PORTS)
    with pytest.raises(ValueError, match="must not declare them: remove NODE_PORTS"):
        _Sup(opts=_ENGINE_OPTS)


def test_a_node_field_in_the_ports_of_a_supervisor_is_refused(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_PORTS", "input=inf;output=outf")
    with pytest.raises(ValueError, match="unknown field 'input'"):
        _UndeclaredSup(opts={"inf": "/dev/null"})


# --- heartbeat / checkpoint_saved / unrecognized command dispatch ------


def test_heartbeat_updates_last_seen_and_clears_down_and_resets_attempts():
    proc = _Sup(opts=_FAKE_OPTS)
    proc._down.add("a")
    proc._relaunch_attempts["a"] = 2

    before = proc._last_heartbeat["a"]
    time.sleep(0.01)
    proc._on_node_interact("a", {"command": "heartbeat", "args": {}})

    assert proc._last_heartbeat["a"] > before
    assert "a" not in proc._down
    assert proc._relaunch_attempts["a"] == 0


def test_checkpoint_saved_is_just_logged(caplog):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("INFO", logger=proc.log.name):
            proc._on_node_interact(
                "a", {"command": "checkpoint_saved", "args": {"epoch": 3, "path": "/x"}}
            )
    finally:
        proc.log.removeHandler(caplog.handler)

    assert "a" in caplog.text
    assert "3" in caplog.text


def test_unrecognized_node_command_is_logged_and_ignored(caplog):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("WARNING", logger=proc.log.name):
            proc._on_node_interact("a", {"command": "not_a_real_command", "args": {}})
    finally:
        proc.log.removeHandler(caplog.handler)

    assert "not_a_real_command" in caplog.text


def test_brain_loop_ignores_unexpected_envelope_types(caplog):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.log.addHandler(caplog.handler)
    before = proc._last_heartbeat["a"]
    proc._inbound_queue.put(("a", lib.TYPE_DATA, {"x": 1}))
    proc._inbound_queue.put(lib._STOP)
    try:
        with caplog.at_level("WARNING", logger=proc.log.name):
            proc._brain_loop()
    finally:
        proc.log.removeHandler(caplog.handler)

    assert "DATA" in caplog.text
    # A DATA envelope is a protocol violation on a Supervisor channel,
    # not something that should be mistaken for a heartbeat.
    assert proc._last_heartbeat["a"] == before


# --- manual trigger relay ------------------------------------------------


def test_manual_trigger_relays_the_command_to_every_trigger_port():
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a", "init_b"]

    proc = Sup(opts={"init_a": "/tmp/a", "init_b": "/tmp/b"})
    proc._on_manual_trigger({"command": "start_snapshot", "args": {"foo": 1, "epoch": 42}})

    for port in ("init_a", "init_b"):
        line = proc._outbound_queues[port].get_nowait()
        assert lib.decode_envelope(line) == lib.Envelope(
            type="INTERACT", payload={"command": "start_snapshot", "args": {"foo": 1, "epoch": 42}}
        )


def test_manual_trigger_gives_every_initiator_the_same_epoch_in_milliseconds(monkeypatch):
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a", "init_b"]

    monkeypatch.setattr(time, "time_ns", lambda: 1_790_000_000_123_456_789)
    proc = Sup(opts={"init_a": "/tmp/a", "init_b": "/tmp/b"})
    proc._on_manual_trigger({"command": "shutdown", "args": {"foo": 1}})

    for port in ("init_a", "init_b"):
        payload = lib.decode_envelope(proc._outbound_queues[port].get_nowait()).payload
        assert payload == {"command": "shutdown", "args": {"foo": 1, "epoch": 1_790_000_000_123}}


def test_manual_trigger_epochs_keep_growing_within_the_same_millisecond(monkeypatch):
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a"]

    monkeypatch.setattr(time, "time_ns", lambda: 5_000_000)
    proc = Sup(opts={"init_a": "/tmp/a"})
    proc._on_manual_trigger({"command": "start_snapshot"})
    proc._on_manual_trigger({"command": "start_snapshot", "args": None})

    epochs = [
        lib.decode_envelope(proc._outbound_queues["init_a"].get_nowait()).payload["args"]["epoch"]
        for _ in range(2)
    ]
    assert epochs == [5, 6]


def test_manual_trigger_leaves_args_that_are_not_an_object_alone():
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a"]

    proc = Sup(opts={"init_a": "/tmp/a"})
    proc._on_manual_trigger({"command": "whatever_the_gui_sent", "args": [1, 2]})

    line = proc._outbound_queues["init_a"].get_nowait()
    assert lib.decode_envelope(line).payload["args"] == [1, 2]


def test_manual_trigger_does_not_validate_the_command():
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a"]

    proc = Sup(opts={"init_a": "/tmp/a"})
    proc._on_manual_trigger({"command": "whatever_the_gui_sent", "args": None})

    line = proc._outbound_queues["init_a"].get_nowait()
    assert lib.decode_envelope(line).payload["command"] == "whatever_the_gui_sent"


# --- _node_pid_alive -----------------------------------------------------


def test_node_pid_alive_true_when_no_id_file_yet(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._node_pid_alive("a") is True


def test_node_pid_alive_true_for_a_real_running_pid(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._node_pid_alive("a") is True


def test_node_pid_alive_false_for_a_pid_that_no_longer_exists(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._node_pid_alive("a") is False


def test_node_pid_alive_true_for_malformed_id_file(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text("not-a-pid")
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._node_pid_alive("a") is True


# --- _check_node: .finished / PID-dead fast path / heartbeat timeout ----


def test_check_node_marks_done_on_finished_file_and_clears_down(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    proc._down.add("a")
    _node_dir(execdir, "a").joinpath("a.finished").write_text("ok")

    proc._check_node("a")

    assert "a" in proc._done
    assert "a" not in proc._down


def test_check_node_skips_nodes_already_done_or_given_up(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    proc._done.add("a")
    proc._given_up.add("b")
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")
    proc._check_node("b")

    assert calls == []


def test_check_node_declares_down_immediately_on_dead_pid_without_waiting_for_timeout(
    execdir,
):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))

    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 999999  # would never fire on its own
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == ["a"]
    assert "a" in proc._down


def test_check_node_leaves_a_live_but_recently_heard_from_node_alone(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == []
    assert "a" not in proc._down


def test_check_node_declares_down_on_heartbeat_timeout_with_a_live_pid(execdir):
    # A live PID never proves health by itself -- only heartbeat timeout
    # judges "alive but not really working".
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 0
    proc._last_heartbeat["a"] = time.monotonic() - 10
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == ["a"]


def test_check_node_does_not_repeat_on_node_down_while_still_down(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")
    proc._check_node("a")
    proc._check_node("a")

    assert calls == ["a"]


def test_check_node_declares_down_again_once_a_relaunch_never_heartbeats(execdir):
    # The relaunched incarnation itself dies before ever sending a
    # heartbeat: with no grace period this node would stay "down"
    # forever, since only a real heartbeat used to clear it.
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 0
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")
    proc._check_node("a")

    assert calls == ["a", "a"]
    assert proc._relaunch_attempts["a"] == 2


def test_repeated_relaunches_that_never_heartbeat_eventually_escalate(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 0
    proc.MAX_RELAUNCH_ATTEMPTS = 2
    down_calls = []
    failed_calls = []
    proc.on_node_down = lambda node: down_calls.append(node)
    proc.on_node_permanently_failed = lambda node: failed_calls.append(node)

    proc._check_node("a")
    proc._check_node("a")
    proc._check_node("a")

    assert down_calls == ["a", "a"]
    assert failed_calls == ["a"]
    assert "a" in proc._given_up


def test_check_node_suspends_failure_detection_while_an_escalation_is_in_flight(execdir):
    # An escalation already asks every reachable node to stop; declaring
    # one "down" here over the heartbeat gap that stopping naturally
    # produces would relaunch a node the escalation just told to leave.
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc._active_escalations = 1
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == []
    assert "a" not in proc._down


def test_check_node_still_detects_finished_while_an_escalation_is_in_flight(execdir):
    # The one thing that must keep working during an escalation: a node
    # reaching "done" is what lets _maybe_resolve ever fire once it ends.
    proc = _Sup(opts=_FAKE_OPTS)
    proc._active_escalations = 1
    _node_dir(execdir, "a").joinpath("a.finished").write_text("ok")

    proc._check_node("a")

    assert "a" in proc._done


# --- _declare_down / relaunch budget -------------------------------------


def test_declare_down_calls_on_node_down_within_budget():
    proc = _Sup(opts=_FAKE_OPTS)
    proc.MAX_RELAUNCH_ATTEMPTS = 3
    down_calls = []
    failed_calls = []
    proc.on_node_down = lambda node: down_calls.append(node)
    proc.on_node_permanently_failed = lambda node: failed_calls.append(node)

    proc._declare_down("a")

    assert down_calls == ["a"]
    assert failed_calls == []
    assert proc._relaunch_attempts["a"] == 1


def test_declare_down_gives_up_after_exceeding_the_budget():
    proc = _Sup(opts=_FAKE_OPTS)
    proc.MAX_RELAUNCH_ATTEMPTS = 2
    down_calls = []
    failed_calls = []
    proc.on_node_down = lambda node: down_calls.append(node)
    proc.on_node_permanently_failed = lambda node: failed_calls.append(node)

    for _ in range(2):
        proc._declare_down("a")
        proc._down.discard("a")  # simulate a fresh outage each time

    proc._declare_down("a")

    assert down_calls == ["a", "a"]
    assert failed_calls == ["a"]
    assert "a" in proc._given_up


def test_declare_down_resets_last_heartbeat_to_start_a_fresh_grace_period():
    proc = _Sup(opts=_FAKE_OPTS)
    proc._last_heartbeat["a"] = 0
    proc.on_node_down = lambda node: None

    proc._declare_down("a")

    assert proc._last_heartbeat["a"] > 0


def test_recovering_between_outages_resets_the_budget():
    proc = _Sup(opts=_FAKE_OPTS)
    proc.MAX_RELAUNCH_ATTEMPTS = 1
    failed_calls = []
    proc.on_node_down = lambda node: None
    proc.on_node_permanently_failed = lambda node: failed_calls.append(node)

    proc._declare_down("a")
    proc._on_heartbeat("a")  # real recovery: resets the counter
    proc._declare_down("a")

    assert failed_calls == []
    assert "a" not in proc._given_up


# --- node identity: plain process name or (process, task_idx) ----------


def test_plain_node_file_names_have_no_task_index(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._node_id_file("a") == str(execdir / "__exec__" / "a" / "a.id")
    assert proc._node_finished_file("a") == str(execdir / "__exec__" / "a" / "a.finished")


def test_array_task_node_file_names_carry_the_task_index(execdir):
    class Sup(lib.Supervisor):
        NODE_PORTS = {("w", 3): "hb_w3"}

    proc = Sup(opts={"hb_w3": "/tmp/hb_w3"})
    assert proc._node_id_file(("w", 3)) == str(execdir / "__exec__" / "w" / "w_3.id")
    assert proc._node_finished_file(("w", 3)) == str(
        execdir / "__exec__" / "w" / "w_3.finished"
    )


def test_check_node_marks_an_array_task_done_from_its_own_finished_file(execdir):
    class Sup(lib.Supervisor):
        NODE_PORTS = {("w", 0): "hb_w0", ("w", 1): "hb_w1"}

    proc = Sup(opts={"hb_w0": "/tmp/hb_w0", "hb_w1": "/tmp/hb_w1"})
    _node_dir(execdir, "w").joinpath("w_1.finished").write_text("ok")

    proc._check_node(("w", 1))

    assert ("w", 1) in proc._done
    assert ("w", 0) not in proc._done


@pytest.mark.parametrize(
    "bad_key",
    [("w",), ("w", "1"), (1, 2), ("w", -1), ("w", 1, 2), ("w", True), 5],
)
def test_rejects_a_malformed_node_key(bad_key):
    class Sup(lib.Supervisor):
        NODE_PORTS = {bad_key: "hb"}

    with pytest.raises(ValueError, match="NODE_PORTS key"):
        Sup(opts={"hb": "/tmp/hb"})


# --- on_node_down default: relaunch through debasher_launch_process -----


class _FakeLauncher:
    def __init__(self, returncode=0):
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_launch_process_command_for_a_plain_process(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", "/opt/libexec")
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._launch_process_command("a") == [
        "/opt/libexec/debasher_launch_process",
        "-d",
        str(execdir),
        "-p",
        "a",
    ]


def test_launch_process_command_for_an_array_task_adds_the_task_index(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", "/opt/libexec")

    class Sup(lib.Supervisor):
        NODE_PORTS = {("w", 3): "hb_w3"}

    proc = Sup(opts={"hb_w3": "/tmp/hb_w3"})
    assert proc._launch_process_command(("w", 3)) == [
        "/opt/libexec/debasher_launch_process",
        "-d",
        str(execdir),
        "-p",
        "w",
        "-t",
        "3",
    ]


def test_launch_process_command_requires_the_libexec_env_var(monkeypatch):
    monkeypatch.delenv("DEBASHER_LIBEXECDIR", raising=False)
    proc = _Sup(opts=_FAKE_OPTS)
    with pytest.raises(RuntimeError, match="DEBASHER_LIBEXECDIR"):
        proc._launch_process_command("a")


def test_debasher_stop_resident_command_uses_the_bindir_env_var(monkeypatch):
    monkeypatch.setenv("DEBASHER_BINDIR", "/opt/bin")
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc._debasher_stop_resident_command() == "/opt/bin/debasher_stop_resident"


def test_debasher_stop_resident_command_requires_the_bindir_env_var(monkeypatch):
    monkeypatch.delenv("DEBASHER_BINDIR", raising=False)
    proc = _Sup(opts=_FAKE_OPTS)
    with pytest.raises(RuntimeError, match="DEBASHER_BINDIR"):
        proc._debasher_stop_resident_command()


def test_on_node_down_default_runs_the_launcher_tool(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", "/opt/libexec")
    proc = _Sup(opts=_FAKE_OPTS)
    calls = []

    def fake_popen(command, **kwargs):
        calls.append(command)
        return _FakeLauncher()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    proc.on_node_down("a")

    assert calls == [proc._launch_process_command("a")]


def test_on_node_down_default_logs_a_failing_launcher(execdir, monkeypatch, caplog):
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", "/opt/libexec")
    proc = _Sup(opts=_FAKE_OPTS)
    monkeypatch.setattr(subprocess, "Popen", lambda command, **kw: _FakeLauncher(returncode=3))

    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("ERROR", logger=proc.log.name):
            proc.on_node_down("a")
            assert _wait_until(lambda: "exit code 3" in caplog.text)
    finally:
        proc.log.removeHandler(caplog.handler)

    assert "'a'" in caplog.text


# --- on_node_permanently_failed: escalation via debasher_stop_resident ---


def test_escalation_calls_debasher_stop_resident_excluding_the_given_up_node(
    execdir, monkeypatch
):
    monkeypatch.setenv("DEBASHER_BINDIR", "/opt/bin")
    proc = _Sup(opts=_FAKE_OPTS)
    proc.FORCE_STOP_TIMEOUT_SECS = 5
    proc._given_up.add("a")
    proc._done.add("b")  # everyone else already resolved

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    proc.on_node_permanently_failed("a")

    assert _wait_until(lambda: proc._active_escalations == 0)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == [
        "/opt/bin/debasher_stop_resident",
        "-d",
        str(execdir),
        "-x",
        "a",
        "--keep-supervisor",
        "--timeout",
        "5",
    ]
    # Matches the DEVNULL redirection Supervisor already applies to its
    # own relaunch Popen calls (see on_node_down): left inherited, the
    # generated wrapper script's own stdout/stderr tee pipe would stay
    # open for as long as this subprocess runs, the same leak pieza 2
    # found and fixed for a relaunch.
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert proc._all_resolved.is_set()


def test_escalation_excludes_only_the_failed_task_of_an_array(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_BINDIR", "/opt/bin")

    class Sup(lib.Supervisor):
        NODE_PORTS = {("w", 0): "hb_w0", ("w", 1): "hb_w1"}

    proc = Sup(opts={"hb_w0": "/tmp/hb_w0", "hb_w1": "/tmp/hb_w1"})
    proc._given_up.add(("w", 1))
    proc._done.add(("w", 0))

    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: (calls.append(args), subprocess.CompletedProcess(args, 0))[1],
    )

    proc.on_node_permanently_failed(("w", 1))

    assert _wait_until(lambda: proc._active_escalations == 0)
    assert calls[0][calls[0].index("-x") + 1] == "w:1"


def test_escalation_logs_but_still_resolves_bookkeeping_when_the_tool_fails(
    execdir, monkeypatch
):
    monkeypatch.setenv("DEBASHER_BINDIR", "/opt/bin")
    proc = _Sup(opts=_FAKE_OPTS)
    proc._given_up.add("a")
    proc._done.add("b")

    monkeypatch.setattr(
        subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 1)
    )

    proc.on_node_permanently_failed("a")

    assert _wait_until(lambda: proc._active_escalations == 0)
    # debasher_stop_resident itself already falls back to debasher_stop
    # internally on its own timeout: a nonzero exit here is logged, not
    # retried or escalated further from this side.
    assert proc._all_resolved.is_set()


def test_forced_exit_constant_matches_the_tool_script():
    # Ties the two sides of a cross-language contract together: a mismatch
    # here (either constant edited without the other) would otherwise pass
    # every other test silently, since they mock subprocess.run and read
    # this same Python constant back for the "forced" case rather than a
    # literal value.
    sh_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(lib.__file__))),
        "engine",
        "debasher_stop_resident.sh",
    )
    with open(sh_path) as f:
        text = f.read()
    match = re.search(r"^DEBASHER_STOP_RESIDENT_FORCED_EXIT=(\d+)$", text, re.MULTILINE)
    assert match, "debasher_stop_resident.sh no longer defines DEBASHER_STOP_RESIDENT_FORCED_EXIT"
    assert lib.Supervisor._DEBASHER_STOP_RESIDENT_FORCED_EXIT == int(match.group(1))


def test_escalation_logs_a_specific_message_when_the_tool_reports_a_forced_stop(
    execdir, monkeypatch, caplog
):
    monkeypatch.setenv("DEBASHER_BINDIR", "/opt/bin")
    proc = _Sup(opts=_FAKE_OPTS)
    proc._given_up.add("a")
    proc._done.add("b")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, proc._DEBASHER_STOP_RESIDENT_FORCED_EXIT
        ),
    )

    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("ERROR", logger=proc.log.name):
            proc.on_node_permanently_failed("a")
            assert _wait_until(lambda: "forced a hard kill" in caplog.text)
    finally:
        proc.log.removeHandler(caplog.handler)

    assert "'a'" in caplog.text
    assert proc._all_resolved.is_set()


# --- _maybe_resolve -------------------------------------------------------


def test_maybe_resolve_sets_all_resolved_once_everything_is_settled():
    proc = _Sup(opts=_FAKE_OPTS)
    proc._done.add("a")
    proc._given_up.add("b")

    proc._maybe_resolve()

    assert proc._all_resolved.is_set()


def test_maybe_resolve_waits_for_pending_escalations():
    proc = _Sup(opts=_FAKE_OPTS)
    proc._done.add("a")
    proc._given_up.add("b")
    proc._active_escalations = 1

    proc._maybe_resolve()

    assert not proc._all_resolved.is_set()


# --- integration: a real heartbeat over a real FIFO ----------------------


def test_real_heartbeat_over_a_real_fifo_updates_last_seen(tmp_path):
    fifo_path = tmp_path / "hb.fifo"
    os.mkfifo(fifo_path)

    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a"}

    proc = Sup(opts={"hb_a": str(fifo_path)})
    before = proc._last_heartbeat["a"]
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_interact("heartbeat") + "\n")
            w.flush()

        assert _wait_until(lambda: proc._last_heartbeat["a"] > before)
    finally:
        proc.stop_threads(timeout=2)


# --- reader threads: no EOF, nothing to reopen ---------------------------


class _OneNodeSup(lib.Supervisor):
    NODE_PORTS = {"a": "hb_a"}


def test_no_supervisor_reader_drops_what_follows_a_close():
    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a"}
        MANUAL_TRIGGER_PORT = "manual"

    proc = Sup(opts={"hb_a": "/tmp/hb_a", "manual": "/tmp/manual"})

    assert proc._drops_after_close("a") is False
    assert proc._drops_after_close(lib._MANUAL_TRIGGER_TAG) is False


def test_stop_threads_passes_the_choice_of_saying_close_to_the_supervisors_writers(tmp_path):
    fifo_path = tmp_path / "init.fifo"
    os.mkfifo(fifo_path)

    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        TRIGGER_PORT = ["init_a"]

    for close, expected in ((True, ["HELLO", "CLOSE"]), (False, ["HELLO"])):
        proc = Sup(opts={"init_a": str(fifo_path)})
        proc.start_threads()
        with open(fifo_path, "r") as r:
            proc.stop_threads(timeout=2, close=close)
            envelopes = [lib.decode_envelope(line) for line in r.read().splitlines() if line]
        assert [e.type for e in envelopes] == expected


def test_real_reader_hears_a_relaunched_writer(tmp_path):
    """
    The crash and relaunch scenario at the Python level: a first writer
    connects, sends one heartbeat and goes away (a node dying); the
    Supervisor's reader never sees EOF, so it neither dies nor has anything
    to reopen, and a second, independent writer (the relaunched node) is
    heard on the very same fifo path.
    """
    fifo_path = tmp_path / "hb.fifo"
    os.mkfifo(fifo_path)

    proc = _OneNodeSup(opts={"hb_a": str(fifo_path)})
    proc.start_threads()
    try:
        proc._last_heartbeat["a"] = 0
        with open(fifo_path, "w") as w:
            w.write(lib.encode_interact("heartbeat") + "\n")
        assert _wait_until(lambda: proc._last_heartbeat["a"] > 0)
        assert proc._reader_threads["a"].is_alive()

        proc._last_heartbeat["a"] = 0
        with open(fifo_path, "w") as w:
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_interact("heartbeat") + "\n")
        assert _wait_until(lambda: proc._last_heartbeat["a"] > 0)
        assert proc._reader_threads["a"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_reader_keeps_listening_after_a_node_sends_close(tmp_path):
    fifo_path = tmp_path / "hb.fifo"
    os.mkfifo(fifo_path)

    proc = _OneNodeSup(opts={"hb_a": str(fifo_path)})
    proc.start_threads()
    try:
        # A node that closes its channel may still crash or be relaunched
        # later, and must be heard again when it comes back.
        with open(fifo_path, "w") as w:
            w.write(lib.encode_close() + "\n")
        time.sleep(0.1)
        assert proc._reader_threads["a"].is_alive()

        proc._last_heartbeat["a"] = 0
        with open(fifo_path, "w") as w:
            w.write(lib.encode_interact("heartbeat") + "\n")
        assert _wait_until(lambda: proc._last_heartbeat["a"] > 0)
    finally:
        proc.stop_threads(timeout=2)


def test_run_returns_once_every_node_is_resolved_even_with_a_manual_trigger_port(execdir, tmp_path):
    # Regression: the manual trigger reader always sits waiting for the next
    # external write, and stop_threads() used to join it forever.
    hb = tmp_path / "hb_a.fifo"
    manual = tmp_path / "manual.fifo"
    os.mkfifo(hb)
    os.mkfifo(manual)

    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a"}
        MANUAL_TRIGGER_PORT = "manual"
        HEARTBEAT_CHECK_INTERVAL_SECS = 0.05

    _node_dir(execdir, "a").joinpath("a.finished").write_text("ok")
    proc = Sup(opts={"hb_a": str(hb), "manual": str(manual)})

    runner = threading.Thread(target=proc.run, daemon=True)
    runner.start()
    runner.join(timeout=5)

    assert not runner.is_alive()


# --- stopping by signal, same mechanism as FBPProcess -----------------


def test_on_stop_signal_sets_all_resolved():
    proc = _Sup(opts=_FAKE_OPTS)
    assert not proc._all_resolved.is_set()

    proc._on_stop_signal(signal.SIGTERM, None)

    assert proc._all_resolved.is_set()


@pytest.fixture
def _sigterm_handler_guard():
    original = signal.getsignal(signal.SIGTERM)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, original)


@pytest.fixture
def _real_opts(tmp_path):
    # run() calls start_threads(), which opens every declared port's fifo
    # for real: _FAKE_OPTS's paths do not exist and only work for tests
    # that never go through run()/start_threads() at all.
    hb_a = tmp_path / "hb_a.fifo"
    hb_b = tmp_path / "hb_b.fifo"
    os.mkfifo(hb_a)
    os.mkfifo(hb_b)
    return {"hb_a": str(hb_a), "hb_b": str(hb_b)}


def test_run_installs_a_sigterm_handler_when_called_on_the_main_thread(_sigterm_handler_guard, _real_opts):
    proc = _Sup(opts=_real_opts)
    proc._all_resolved.set()  # so run() returns at once, on this (the main) thread

    proc.run()

    assert signal.getsignal(signal.SIGTERM) == proc._on_stop_signal


def test_run_does_not_touch_the_signal_handler_off_the_main_thread(_sigterm_handler_guard, _real_opts):
    before = signal.getsignal(signal.SIGTERM)
    proc = _Sup(opts=_real_opts)
    runner = threading.Thread(target=proc.run, daemon=True)
    runner.start()

    assert _wait_until(lambda: proc._checker_thread is not None and proc._checker_thread.is_alive())
    assert signal.getsignal(signal.SIGTERM) == before

    proc._all_resolved.set()
    assert _wait_until(lambda: not runner.is_alive())


def test_a_real_sigterm_stops_run_before_every_node_is_resolved(_sigterm_handler_guard, _real_opts):
    # The actual guarantee this piece is for: a graceful-stop tool that
    # finds a Supervisor can end it by signal even while nodes it watches
    # are still unresolved, so it cannot relaunch one out from under the
    # tool's own subsequent halt-and-signal sequence.
    proc = _Sup(opts=_real_opts)

    def _send_sigterm_once_running():
        assert _wait_until(lambda: proc._checker_thread is not None and proc._checker_thread.is_alive())
        os.kill(os.getpid(), signal.SIGTERM)

    sender = threading.Thread(target=_send_sigterm_once_running, daemon=True)
    sender.start()

    proc.run()  # blocks here, on the main thread, until the signal arrives

    sender.join(timeout=2)
    assert not proc._checker_thread.is_alive()


# --- a Supervisor that did not run for a while --------------------------


def test_a_late_tick_moves_every_last_heartbeat_forward_by_the_stall():
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    proc._last_heartbeat = {"a": 100.0, "b": 200.0}

    # 5.5 s since the previous tick, 0.5 s expected: 5 s during which this
    # Supervisor did not run.
    proc._credit_own_stall(5.5)

    assert proc._last_heartbeat == {"a": pytest.approx(105.0), "b": pytest.approx(205.0)}


def test_a_tick_late_by_no_more_than_one_interval_changes_nothing():
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    proc._last_heartbeat = {"a": 100.0, "b": 200.0}

    proc._credit_own_stall(1.0)

    assert proc._last_heartbeat == {"a": 100.0, "b": 200.0}


def test_after_its_own_stall_the_supervisor_does_not_declare_a_live_node_down(execdir):
    # The node sent its last heartbeat just before this Supervisor stopped
    # running for 10 s; the ones it sent meanwhile are still unread.
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    proc.HEARTBEAT_TIMEOUT_SECS = 3
    proc._last_heartbeat["a"] = time.monotonic() - 10.5
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._credit_own_stall(10.5)
    proc._check_node("a")

    assert calls == []


def test_after_its_own_stall_a_node_whose_process_is_gone_is_still_declared_down(execdir):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_CHECK_INTERVAL_SECS = 0.5
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._credit_own_stall(10.5)
    proc._check_node("a")

    assert calls == ["a"]


def test_a_jump_of_the_wall_clock_does_not_make_a_node_look_silent(execdir, monkeypatch):
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc._on_heartbeat("a")
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 3600)
    proc._check_node("a")

    assert calls == []


# --- the heartbeat timeout from the computational specifications -------


def test_the_computational_specs_set_the_heartbeat_timeout(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; mem=32; time=00:01:00; heartbeat_timeout_s=90")
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc.HEARTBEAT_TIMEOUT_SECS == 90
    assert _Sup.HEARTBEAT_TIMEOUT_SECS == lib.Supervisor.HEARTBEAT_TIMEOUT_SECS


def test_the_limits_of_a_node_mean_nothing_to_a_supervisor(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; out_backlog_fail_mb=1")
    proc = _Sup(opts=_FAKE_OPTS)
    assert not hasattr(proc, "OUT_BACKLOG_FAIL_BYTES")


def test_a_heartbeat_timeout_that_is_not_a_positive_number_is_refused(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; heartbeat_timeout_s=0")
    with pytest.raises(ValueError, match="heartbeat_timeout_s"):
        _Sup(opts=_FAKE_OPTS)


# --- the startup deadline ------------------------------------------------


def _silent_live_node(execdir, proc, node, silent_for):
    _node_dir(execdir, node).joinpath(f"{node}.id").write_text(str(os.getpid()))
    proc._last_heartbeat[node] = time.monotonic() - silent_for


def test_a_node_not_heard_from_since_its_launch_has_its_startup_deadline(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 3
    proc.STARTUP_TIMEOUT_SECS = 60
    _silent_live_node(execdir, proc, "a", 10)
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")
    assert calls == []

    proc._last_heartbeat["a"] = time.monotonic() - 61
    proc._check_node("a")
    assert calls == ["a"]


def test_after_its_first_heartbeat_a_node_has_the_heartbeat_timeout(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 3
    proc.STARTUP_TIMEOUT_SECS = 60
    proc._on_heartbeat("a")
    _silent_live_node(execdir, proc, "a", 10)
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == ["a"]


def test_a_relaunched_node_has_its_startup_deadline_again(execdir):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_TIMEOUT_SECS = 3
    proc.STARTUP_TIMEOUT_SECS = 60
    proc._on_heartbeat("a")
    proc.on_node_down = lambda node: None
    proc._declare_down("a")
    with proc._lock:
        assert proc._silence_limit("a") == 60


def test_a_node_that_dies_during_its_startup_is_declared_down_at_once(execdir):
    # How a node that crashes on the same record at every replay ends: its
    # relaunch attempts run out as before, the deadline does not delay it.
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(_dead_pid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc.STARTUP_TIMEOUT_SECS = 999999
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    proc._check_node("a")

    assert calls == ["a"]


def test_the_startup_deadline_of_a_node_overrides_the_supervisors(execdir):
    class Sup(_Sup):
        STARTUP_TIMEOUT_SECS = 60
        NODE_STARTUP_TIMEOUT_SECS = {"b": 120}

    proc = Sup(opts=_FAKE_OPTS)
    with proc._lock:
        assert proc._silence_limit("a") == 60
        assert proc._silence_limit("b") == 120


def test_the_startup_deadline_is_never_shorter_than_the_heartbeat_timeout():
    class Sup(_Sup):
        HEARTBEAT_TIMEOUT_SECS = 30
        NODE_STARTUP_TIMEOUT_SECS = {"b": 5}

    proc = Sup(opts=_FAKE_OPTS)
    with proc._lock:
        assert proc._silence_limit("a") == 30
        assert proc._silence_limit("b") == 30


def test_the_computational_specs_set_the_startup_deadline_of_every_node(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; mem=32; startup_timeout_s=90")
    proc = _Sup(opts=_FAKE_OPTS)
    assert proc.STARTUP_TIMEOUT_SECS == 90


def test_the_engine_gives_the_startup_deadline_of_each_node(monkeypatch):
    monkeypatch.setenv(
        "DEBASHER_PROCESS_PORTS",
        "nodes=a=hb_a,worker:1=hb_w1;trigger=;manual_trigger=;startup=worker:1=45",
    )
    proc = _UndeclaredSup(opts={"hb_a": "/dev/null", "hb_w1": "/dev/null"})
    assert proc.NODE_STARTUP_TIMEOUT_SECS == {("worker", 1): 45.0}


def test_a_node_silent_for_longer_than_the_timeout_is_declared_down(execdir, monkeypatch):
    # The same clock measures both ends: when the heartbeat arrived, and
    # how long ago that was.
    _node_dir(execdir, "a").joinpath("a.id").write_text(str(os.getpid()))
    proc = _Sup(opts=_FAKE_OPTS)
    proc._on_heartbeat("a")
    calls = []
    proc.on_node_down = lambda node: calls.append(node)

    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + proc.HEARTBEAT_TIMEOUT_SECS + 1)
    proc._check_node("a")

    assert calls == ["a"]


def test_the_checker_loop_hands_the_time_between_its_ticks_to_the_stall_credit(monkeypatch):
    proc = _Sup(opts=_FAKE_OPTS)
    proc.HEARTBEAT_CHECK_INTERVAL_SECS = 0.05
    gaps = []
    proc._credit_own_stall = gaps.append
    proc._check_once = lambda: None

    checker = threading.Thread(target=proc._check_loop, daemon=True)
    checker.start()
    try:
        assert _wait_until(lambda: len(gaps) >= 3)
    finally:
        proc._checker_stop.set()
        checker.join(timeout=2)

    assert all(gap >= 0.05 for gap in gaps)
