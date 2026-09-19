import os
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
    proc._on_manual_trigger({"command": "start_snapshot", "args": {"foo": 1}})

    for port in ("init_a", "init_b"):
        line = proc._outbound_queues[port].get_nowait()
        assert lib.decode_envelope(line) == lib.Envelope(
            type="INTERACT", payload={"command": "start_snapshot", "args": {"foo": 1}}
        )


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
    proc._last_heartbeat["a"] = time.time() - 10
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


# --- on_node_permanently_failed: two-phase escalation --------------------


def test_escalation_sends_shutdown_to_every_trigger_port_and_resolves_without_force_stop(
    execdir, monkeypatch
):
    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a", "b": "hb_b"}
        TRIGGER_PORT = ["init_a"]
        FORCE_STOP_TIMEOUT_SECS = 5

    proc = Sup(opts={**_FAKE_OPTS, "init_a": "/tmp/init_a"})
    force_stop_calls = []
    monkeypatch.setattr(subprocess, "run", lambda args: force_stop_calls.append(args))

    proc._given_up.add("a")
    proc._done.add("b")  # everyone else already resolved

    proc.on_node_permanently_failed("a")

    assert _wait_until(lambda: proc._active_escalations == 0)
    line = proc._outbound_queues["init_a"].get_nowait()
    assert lib.decode_envelope(line).payload["command"] == "shutdown"
    assert force_stop_calls == []
    assert proc._all_resolved.is_set()


def test_escalation_forces_debasher_stop_when_the_timeout_elapses_unresolved(
    execdir, monkeypatch
):
    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a", "b": "hb_b"}
        TRIGGER_PORT = []
        FORCE_STOP_TIMEOUT_SECS = 0

    proc = Sup(opts=_FAKE_OPTS)
    force_stop_calls = []
    monkeypatch.setattr(subprocess, "run", lambda args: force_stop_calls.append(args))

    proc._given_up.add("a")
    # "b" never resolves -- simulates the unreachable remainder of a
    # graph broken by "a"'s permanent death.

    proc.on_node_permanently_failed("a")

    assert _wait_until(lambda: proc._active_escalations == 0)
    assert force_stop_calls == [["debasher_stop", "-d", str(execdir)]]
    assert not proc._all_resolved.is_set()


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


# --- _should_reopen_after_eof / reader threads reopening on EOF --------


class _FastGraceSup(lib.Supervisor):
    NODE_PORTS = {"a": "hb_a"}
    EOF_FINISHED_GRACE_SECS = 0.3
    _EOF_POLL_INTERVAL_SECS = 0.02


def test_reader_threads_are_daemon():
    proc = _FastGraceSup(opts=_FAKE_OPTS)
    assert proc._READER_THREADS_ARE_DAEMON is True


def test_should_reopen_after_eof_true_for_the_manual_trigger_tag():
    class Sup(lib.Supervisor):
        NODE_PORTS = {}
        MANUAL_TRIGGER_PORT = "manual"

    proc = Sup(opts={"manual": "/tmp/manual"})
    assert proc._should_reopen_after_eof(lib._MANUAL_TRIGGER_TAG) is True


def test_should_reopen_after_eof_false_once_given_up():
    proc = _FastGraceSup(opts=_FAKE_OPTS)
    proc._given_up.add("a")
    assert proc._should_reopen_after_eof("a") is False


def test_should_reopen_after_eof_false_and_marks_done_when_finished_appears(execdir):
    _node_dir(execdir, "a").joinpath("a.finished").write_text("ok")
    proc = _FastGraceSup(opts=_FAKE_OPTS)
    proc._down.add("a")

    assert proc._should_reopen_after_eof("a") is False
    assert "a" in proc._done
    assert "a" not in proc._down


def test_should_reopen_after_eof_true_after_the_grace_period_with_no_finished_file(execdir):
    proc = _FastGraceSup(opts=_FAKE_OPTS)
    started = time.monotonic()
    assert proc._should_reopen_after_eof("a") is True
    # Actually waited out the grace period, not an instant False-negative.
    assert time.monotonic() - started >= _FastGraceSup.EOF_FINISHED_GRACE_SECS


def test_should_reopen_after_eof_detects_finished_appearing_mid_grace_period(execdir):
    proc = _FastGraceSup(opts=_FAKE_OPTS)
    proc.EOF_FINISHED_GRACE_SECS = 5

    def _write_finished_soon():
        time.sleep(0.15)
        _node_dir(execdir, "a").joinpath("a.finished").write_text("ok")

    threading.Thread(target=_write_finished_soon).start()
    started = time.monotonic()

    assert proc._should_reopen_after_eof("a") is False
    # Caught well before the (deliberately long) grace deadline.
    assert time.monotonic() - started < 2


def test_real_reader_reopens_after_eof_and_receives_a_relaunched_writer(tmp_path):
    """
    End-to-end reproduction of the actual crash+relaunch scenario at the
    Python level: a first writer opens the fifo, sends one heartbeat and
    closes (simulating a node dying); Supervisor's reader must not die
    on that EOF, and a second, independent writer (simulating the
    relaunched node reopening the very same fifo path) must still be
    able to connect and be heard.
    """
    fifo_path = tmp_path / "hb.fifo"
    os.mkfifo(fifo_path)

    class Sup(lib.Supervisor):
        NODE_PORTS = {"a": "hb_a"}
        EOF_FINISHED_GRACE_SECS = 0.2
        _EOF_POLL_INTERVAL_SECS = 0.02

    proc = Sup(opts={"hb_a": str(fifo_path)})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_interact("heartbeat") + "\n")
        assert _wait_until(lambda: proc._reader_threads["a"].is_alive())

        # First writer closed above; nothing has written .finished, so
        # the reader is expected to reopen rather than give up for good.
        second_write_done = threading.Event()

        def _second_writer():
            with open(fifo_path, "w") as w:
                w.write(lib.encode_interact("heartbeat") + "\n")
            second_write_done.set()

        writer_thread = threading.Thread(target=_second_writer)
        writer_thread.start()

        assert second_write_done.wait(timeout=5)
        writer_thread.join(timeout=2)
        assert not writer_thread.is_alive()
    finally:
        # The reader may well be back to waiting on a third writer that
        # never comes at this point -- exactly why its thread is a
        # daemon (_READER_THREADS_ARE_DAEMON), so a bounded-timeout
        # stop_threads() here is safe even if it can't actually join it.
        proc.stop_threads(timeout=1)
