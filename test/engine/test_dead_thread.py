"""
A thread of a node that dies ends its process: run() stops the other
threads, without CLOSE, within a bounded wait, and raises a RuntimeError
that carries the cause, so that the process exits with an error, the same
as a crash. Every thread of a node is a daemon, so that one blocked for
ever never keeps the process from ending.
"""

import os
import threading
import time

import pytest

import debasher_runtime_lib as lib


def _wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def opts(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "node"))
    monkeypatch.delenv("DEBASHER_PROCESS_PORTS", raising=False)
    monkeypatch.delenv("DEBASHER_PROCESS_TASK_IDX", raising=False)
    monkeypatch.delenv("DEBASHER_PROCESS_COMP_SPECS", raising=False)
    paths = {name: str(tmp_path / name) for name in ("inf", "outf")}
    for path in paths.values():
        os.mkfifo(path)
    return paths


class _Relay(lib.FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]
    HEARTBEAT_INTERVAL_SECS = 0.05
    DEAD_THREAD_STOP_TIMEOUT_SECS = 0.5

    def __init__(self, *args, **kwargs):
        self.received = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.received.append(packet)
        self.send_data("outf", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


def _start_run(node):
    """Runs node.run() on a thread of its own, as a process would on its
    main thread; returns the thread and a dict that gets the exception
    run() raised, under "error"."""
    outcome = {}

    def target():
        try:
            node.run()
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, outcome


def _write(path, *lines):
    with open(path, "w") as w:
        for line in lines:
            w.write(line + "\n")


# --- every kind of thread that dies ends run() ---------------------------


class _BrainFails(_Relay):
    def process_data(self, port_name, packet):
        raise KeyError("a fault of the module")


class _WriterFails(_Relay):
    def _on_written(self, tag, line):
        raise OSError(5, "Input/output error")


class _HeartbeatFails(_Relay):
    def _report_node_info(self):
        # Only the heartbeat thread fails: the first file, written by the
        # main thread when the threads start, goes through
        if threading.current_thread().name == "heartbeat":
            raise RuntimeError("a fault of the heartbeat")
        super()._report_node_info()


class _ObserverFails(_Relay):
    OBSERVE_PORT = "events"

    def observe(self):
        raise RuntimeError("the observed world went away")


@pytest.mark.parametrize(
    "cls, lines, thread_name, cause",
    [
        (_BrainFails, [lib.encode_data(1)], "brain", "a fault of the module"),
        (_Relay, ["not json", lib.encode_data(1)], "reader:inf", "not followed by HELLO"),
        (_WriterFails, [lib.encode_data(1)], "writer:outf", "Input/output error"),
        (_HeartbeatFails, [], "heartbeat", "a fault of the heartbeat"),
        (_ObserverFails, [], "observer", "the observed world went away"),
    ],
)
def test_a_thread_that_dies_ends_run_with_an_error_that_names_it(opts, cls, lines, thread_name, cause):
    node = cls(opts=opts)
    thread, outcome = _start_run(node)
    try:
        assert _wait_until(lambda: node._brain_thread is not None)
        if lines:
            _write(opts["inf"], *lines)
        thread.join(timeout=5)
    finally:
        node._stop_requested.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    error = outcome.get("error")
    assert isinstance(error, RuntimeError)
    assert "a thread of its own died" in str(error) and repr(thread_name) in str(error)
    assert cause in str(error.__cause__)


def test_a_thread_that_ends_on_its_own_ends_run_too(opts):
    # A reader of /dev/null ends at its end, which a fifo held at both ends
    # never has: no loop of a thread ends while the process runs.
    node = _Relay(opts={**opts, "inf": os.devnull})
    thread, outcome = _start_run(node)
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert "ended on its own" in str(outcome["error"].__cause__)


def test_a_dead_thread_sends_no_close(opts):
    # The process is relaunched, and its peers must not take it for one
    # that has finished for good
    fd = os.open(opts["outf"], os.O_RDONLY | os.O_NONBLOCK)
    try:
        node = _BrainFails(opts=opts)
        thread, outcome = _start_run(node)
        assert _wait_until(lambda: node._brain_thread is not None)
        _write(opts["inf"], lib.encode_data(1))
        thread.join(timeout=5)
        sent = os.read(fd, 1 << 16).decode()
    finally:
        os.close(fd)

    assert "error" in outcome
    assert sent == "\n" + lib.encode_hello() + "\n"


# --- the bounded stop ----------------------------------------------------


class _StuckBrain(_Relay):
    """A brain thread that never comes back from process_data, and an
    observation thread that never comes back from observe(): neither can
    be joined."""

    OBSERVE_PORT = "events"

    def __init__(self, *args, **kwargs):
        self.never = threading.Event()
        self.stuck = threading.Event()
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.stuck.set()
        self.never.wait()

    def observe(self):
        self.never.wait()


def test_a_death_ends_run_within_its_bound_with_threads_that_never_stop(opts):
    node = _StuckBrain(opts=opts)
    thread, outcome = _start_run(node)
    try:
        assert _wait_until(lambda: node._brain_thread is not None)
        # The brain thread gets stuck, then the reader dies
        _write(opts["inf"], lib.encode_data(1))
        assert node.stuck.wait(5)
        died_at = time.monotonic()
        _write(opts["inf"], "not json", lib.encode_data(2))
        thread.join(timeout=10)
        took = time.monotonic() - died_at
    finally:
        node.never.set()
        thread.join(timeout=5)

    assert "reader:inf" in str(outcome["error"])
    # One bound for every thread together, not one for each of the two
    # that never stop
    assert took < 2 * _StuckBrain.DEAD_THREAD_STOP_TIMEOUT_SECS


def test_every_thread_of_a_node_is_a_daemon(opts):
    # A thread that is not a daemon, blocked for ever, would keep the
    # interpreter from exiting once run() has raised
    node = _ObserverFails(opts=opts)
    node.OBSERVE_INTERVAL_SECS = 60
    node.observe = lambda: None
    node.start_threads()
    try:
        threads = [
            *node._reader_threads.values(),
            *node._writer_threads.values(),
            node._brain_thread,
            node._heartbeat_thread,
            node._observe_thread,
        ]
        assert all(t is not None and t.daemon for t in threads)
    finally:
        node.stop_threads(timeout=2)


# --- a death during the replay -------------------------------------------


class _WriterFailsInReplay(_WriterFails):
    def process_data(self, port_name, packet):
        self.received.append(packet)
        self.send_data("outf", packet)
        # The writer dies on this first message; the replay waits for it, so
        # that what follows depends on no race
        _wait_until(lambda: self._thread_error is not None)


def test_a_writer_that_dies_during_the_replay_stops_it_and_ends_run(opts):
    logged = _Relay(opts=opts)
    logged._open_input_log(0)
    for payload in range(5):
        line = lib.encode_data(payload)
        logged._on_arrival("inf", lib.decode_envelope(line), line)
    logged._input_log.close()

    node = _WriterFailsInReplay(opts=opts)
    thread, outcome = _start_run(node)
    thread.join(timeout=5)

    assert "writer:outf" in str(outcome["error"])
    assert node.received == [0]
    # The other threads were never started
    assert node._brain_thread is None
