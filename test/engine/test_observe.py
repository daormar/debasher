"""
Unit tests of the observation of the outside world in FBPProcess: observe(),
run by an observation thread only for a class that defines it; inject(),
which writes what it sees to the input log under the name OBSERVE_PORT and
queues it, so that it reaches process_data like any input and a replay
reproduces it; and the checks that keep it from being misused.
"""

import os
import threading
import time

import pytest

import debasher_runtime_lib as lib


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def ports(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "node"))
    monkeypatch.delenv("DEBASHER_PROCESS_PORTS", raising=False)
    paths = {}
    for name in ("data",):
        path = tmp_path / name
        os.mkfifo(path)
        paths[name] = str(path)
    return paths


class _Base(lib.FBPProcess):
    INPUT_PORTS = ["data"]

    def __init__(self, *args, **kwargs):
        self.received = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


class _Watcher(_Base):
    OBSERVE_PORT = "events"
    OBSERVE_INTERVAL_SECS = 60

    def __init__(self, *args, **kwargs):
        self.observations = 0
        super().__init__(*args, **kwargs)

    def observe(self):
        self.observations += 1
        self.inject({"seen": self.observations})


def test_a_node_without_observe_has_no_observation_thread(ports):
    node = _Base(opts=ports)
    node.start_threads()
    try:
        assert node._observe_thread is None
        assert node._all_threads_alive()
    finally:
        node.stop_threads(timeout=2)


def test_what_observe_injects_reaches_process_data_through_the_observe_port(ports):
    node = _Watcher(opts=ports)
    node.start_threads()
    try:
        assert _wait_until(lambda: node.received == [("events", {"seen": 1})])
        # And it is in the input log, like any input.
        records = list(node._input_log.replay(0))
        assert [(r.port, r.envelope.payload) for r in records] == [("events", {"seen": 1})]
    finally:
        node.stop_threads(timeout=2)


def test_observe_now_runs_observe_before_its_interval(ports):
    node = _Watcher(opts=ports)
    node.start_threads()
    try:
        assert _wait_until(lambda: node.observations == 1)
        node.observe_now()
        assert _wait_until(lambda: node.observations == 2)
        assert _wait_until(lambda: len(node.received) == 2)
    finally:
        node.stop_threads(timeout=2)


def test_a_dead_observation_thread_makes_the_node_unhealthy(ports):
    class Broken(_Base):
        OBSERVE_INTERVAL_SECS = 60

        def observe(self):
            raise RuntimeError("the observed world went away")

    node = Broken(opts=ports)
    node.start_threads()
    try:
        assert _wait_until(lambda: not node._observe_thread.is_alive())
        assert not node._all_threads_alive()
    finally:
        node.stop_threads(timeout=2)


def test_an_observe_port_that_is_an_input_port_is_refused(ports):
    class Clashing(_Watcher):
        OBSERVE_PORT = "data"

    with pytest.raises(ValueError, match="OBSERVE_PORT names 'data', which is one of its input ports"):
        Clashing(opts=ports)


def test_inject_without_an_observe_port_is_an_error(ports):
    class Portless(_Base):
        def observe(self):
            pass

    node = Portless(opts=ports)
    with pytest.raises(RuntimeError, match="needs OBSERVE_PORT"):
        node.inject({"x": 1})


def test_inject_from_process_data_is_an_error(ports):
    class Echo(_Watcher):
        def process_data(self, port_name, packet):
            self.inject(packet)

    node = Echo(opts=ports)
    with pytest.raises(RuntimeError, match="send_data"):
        node._run_process_data("data", {"x": 1})


def test_inject_returns_once_its_line_is_in_the_input_log(ports):
    logged_when_returned = []

    class Checking(_Base):
        OBSERVE_PORT = "events"
        OBSERVE_INTERVAL_SECS = 60

        def observe(self):
            self.inject({"x": 1})
            logged_when_returned.append([r.envelope.payload for r in self._input_log.replay(0)])

    node = Checking(opts=ports)
    node.start_threads()
    try:
        assert _wait_until(lambda: logged_when_returned)
        assert logged_when_returned == [[{"x": 1}]]
    finally:
        node.stop_threads(timeout=2)


def test_a_relaunched_node_gets_what_was_observed_from_its_log(ports):
    node = _Watcher(opts=ports)
    node.start_threads()
    try:
        assert _wait_until(lambda: node.received == [("events", {"seen": 1})])
    finally:
        node.stop_threads(timeout=2)

    # Its replay hands the observation to process_data again, without
    # observing anything (this class does not even observe).
    class Relaunched(_Base):
        pass

    relaunched = Relaunched(opts=ports)
    relaunched._stop_requested.set()
    relaunched.run()
    assert relaunched.received == [("events", {"seen": 1})]


def test_the_observation_thread_stops_with_the_node(ports):
    node = _Watcher(opts=ports)
    node.start_threads()
    assert _wait_until(lambda: node.observations == 1)
    node.stop_threads(timeout=2)
    assert not node._observe_thread.is_alive()
