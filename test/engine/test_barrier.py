import json
import os
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


@pytest.fixture(autouse=True)
def execdir(tmp_path, monkeypatch):
    # A real reader thread now logs every DATA payload it receives (the
    # message log, see test_message_log.py), which needs this env var
    # the same way checkpointing already does.
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


class _BarrierWorker(lib.FBPProcess):
    INPUT_PORTS = ["a", "b"]
    OUTPUT_PORTS = ["x", "y"]

    def __init__(self, *args, **kwargs):
        self.closed_epochs = []
        self.received = []
        self.state_to_capture = {"marker": "initial"}
        super().__init__(*args, **kwargs)

    def capture_node_state(self):
        return dict(self.state_to_capture)

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, processed_upto):
        self.closed_epochs.append((epoch, halt, node_state, channel_buffers))


_FAKE_OPTS = {"a": "/dev/null", "b": "/dev/null", "x": "/dev/null", "y": "/dev/null"}


def _out(proc, port):
    return proc._outbound_queues[port].get_nowait()


class _OnePort(lib.FBPProcess):
    INPUT_PORTS = ["a"]
    OUTPUT_PORTS = ["x"]

    def __init__(self, *a, **kw):
        self.closed_epochs = []
        super().__init__(*a, **kw)

    def capture_node_state(self):
        return {"marker": "initial"}

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, processed_upto):
        self.closed_epochs.append((epoch, halt, node_state, channel_buffers))


class _Root(lib.FBPProcess):
    OUTPUT_PORTS = ["x"]

    def __init__(self, *a, **kw):
        self.closed_epochs = []
        super().__init__(*a, **kw)

    def capture_node_state(self):
        return {}

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, processed_upto):
        self.closed_epochs.append((epoch, halt, node_state, channel_buffers))


# --- peer-triggered rounds (a BARRIER arriving on an input port) --------


def test_single_pending_port_closes_as_soon_as_its_marker_arrives():
    proc = _OnePort(opts={"a": "/dev/null", "x": "/dev/null"})
    proc._on_barrier("a", {"epoch": 0, "halt": False})

    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {})]
    assert lib.decode_envelope(_out(proc, "x")) == lib.Envelope(
        type="BARRIER", payload={"epoch": 0, "halt": False}
    )


def test_two_pending_ports_waits_for_the_second_marker():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    proc._on_barrier("a", {"epoch": 0, "halt": False})

    assert proc._barrier_pending == {"b"}
    assert proc.closed_epochs == []

    proc._on_barrier("b", {"epoch": 0, "halt": False})

    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {"b": []})]


def test_barrier_is_forwarded_on_every_output_port_when_a_round_opens():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    proc._on_barrier("a", {"epoch": 3, "halt": False})

    assert lib.decode_envelope(_out(proc, "x")).payload == {"epoch": 3, "halt": False}
    assert lib.decode_envelope(_out(proc, "y")).payload == {"epoch": 3, "halt": False}


def test_mismatched_epoch_while_a_round_is_open_raises():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    proc._on_barrier("a", {"epoch": 0, "halt": False})

    with pytest.raises(ValueError):
        proc._on_barrier("b", {"epoch": 99, "halt": False})


# --- self-triggered rounds (INTERACT start_snapshot/shutdown) -----------


def test_start_snapshot_leaves_every_input_port_pending():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    proc._on_interact({"command": "start_snapshot", "args": {}})

    assert proc._barrier_pending == {"a", "b"}
    assert proc.closed_epochs == []
    assert lib.decode_envelope(_out(proc, "x")).payload == {"epoch": 0, "halt": False}


def test_a_root_node_with_no_input_ports_closes_instantly():
    proc = _Root(opts={"x": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})

    assert proc.closed_epochs == [(0, False, {}, {})]


def test_shutdown_command_closes_with_halt_true():
    proc = _Root(opts={"x": "/dev/null"})
    proc._on_interact({"command": "shutdown", "args": {}})

    assert proc.closed_epochs == [(0, True, {}, {})]


def test_epoch_number_increments_across_successive_self_initiated_rounds():
    proc = _Root(opts={"x": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})
    proc._on_interact({"command": "start_snapshot", "args": {}})

    assert [epoch for epoch, *_ in proc.closed_epochs] == [0, 1]


def test_starting_a_round_while_one_is_already_open_raises():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    proc._on_interact({"command": "start_snapshot", "args": {}})

    with pytest.raises(ValueError):
        proc._on_interact({"command": "start_snapshot", "args": {}})


def test_unrecognized_interact_command_is_logged_and_ignored(caplog):
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    # caplog.at_level(level, logger=name) only adjusts that logger's level;
    # its capturing handler lives on the root logger, so it only ever sees
    # records that propagate there. proc.log has propagate=False (by
    # design, to avoid duplicate output through some future ancestor
    # handler), so the handler must be attached directly here instead of
    # relying on propagation.
    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("WARNING", logger=proc.log.name):
            proc._on_interact({"command": "not_a_real_command", "args": {}})
    finally:
        proc.log.removeHandler(caplog.handler)

    assert proc.closed_epochs == []
    assert proc._barrier_epoch is None
    assert "not_a_real_command" in caplog.text


# --- DATA on a still pending port: processed, and also recorded ---------
# --- (the brain loop driven directly, no FIFOs or reader threads)   ------


def _run_brain(proc, items):
    # Feeds the items through the arrival hook, as a reader thread would, and
    # runs the brain loop to completion on its own thread: the order in which
    # the brain sees them is then exactly the order given here.
    if proc._input_log is None:
        proc._open_input_log(0)
    for port, envelope_type, payload in items:
        line = json.dumps({"type": envelope_type, "payload": payload})
        proc._on_arrival(port, lib.Envelope(envelope_type, payload), line)
    proc._inbound_queue.put(lib._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(5)
    assert not brain.is_alive()


_ROUND = {"epoch": 0, "halt": False}


def test_data_on_a_still_pending_port_reaches_process_data_while_a_round_is_open():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),  # the round opens, "b" is pending
            ("b", lib.TYPE_DATA, 5),  # in transit at the cut
            ("b", lib.TYPE_BARRIER, _ROUND),  # the round closes
            ("b", lib.TYPE_DATA, 7),
        ],
    )

    assert proc.received == [("b", 5), ("b", 7)]


def test_data_on_a_still_pending_port_is_also_recorded_as_channel_state():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),
            ("b", lib.TYPE_DATA, 5),
            ("b", lib.TYPE_BARRIER, _ROUND),
            ("b", lib.TYPE_DATA, 7),  # after the round: not part of it
        ],
    )

    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {"b": [5]})]


def test_messages_are_processed_in_arrival_order_across_pending_and_settled_ports():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),  # "a" settles, "b" stays pending
            ("b", lib.TYPE_DATA, "b1"),
            ("a", lib.TYPE_DATA, "a1"),
            ("b", lib.TYPE_DATA, "b2"),
            ("b", lib.TYPE_BARRIER, _ROUND),
        ],
    )

    assert proc.received == [("b", "b1"), ("a", "a1"), ("b", "b2")]
    # Only what arrived on the pending port is channel state: "a1" came
    # after "a"'s own marker, so it belongs to the next round.
    assert proc.closed_epochs[0][3] == {"b": ["b1", "b2"]}


def test_process_data_cannot_alter_the_recorded_channel_state():
    class _Mutating(_BarrierWorker):
        def process_data(self, port_name, packet):
            super().process_data(port_name, packet)
            packet["touched"] = True

    proc = _Mutating(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),
            ("b", lib.TYPE_DATA, {"n": 1}),
            ("b", lib.TYPE_BARRIER, _ROUND),
        ],
    )

    assert proc.received == [("b", {"n": 1, "touched": True})]
    assert proc.closed_epochs[0][3] == {"b": [{"n": 1}]}


def test_data_on_a_still_pending_port_is_logged_like_any_other():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),
            ("b", lib.TYPE_DATA, 5),
            ("b", lib.TYPE_BARRIER, _ROUND),
            ("b", lib.TYPE_DATA, 7),
        ],
    )

    # Every item is in the input log, with its position, and the DATA ones are the two that were sent.
    records = list(proc._input_log.replay(0))
    assert [(r.pos, r.port, r.envelope.type) for r in records] == [
        (1, "a", "BARRIER"),
        (2, "b", "DATA"),
        (3, "b", "BARRIER"),
        (4, "b", "DATA"),
    ]
    assert [r.envelope.payload for r in records if r.envelope.type == "DATA"] == [5, 7]


# --- integration: a real cyclic self-return and a real pending port, ----
# --- through real threads and FIFOs                                   ---


@pytest.fixture
def fifo_pair(tmp_path):
    a_to_b = tmp_path / "a_to_b.fifo"
    b_to_a = tmp_path / "b_to_a.fifo"
    os.mkfifo(a_to_b)
    os.mkfifo(b_to_a)
    return str(a_to_b), str(b_to_a)


def test_data_on_a_still_pending_port_is_delivered_and_recorded_through_real_fifos(tmp_path):
    path_a = str(tmp_path / "a.fifo")
    path_b = str(tmp_path / "b.fifo")
    os.mkfifo(path_a)
    os.mkfifo(path_b)

    proc = _BarrierWorker(opts={"a": path_a, "b": path_b, "x": str(tmp_path / "x.fifo"), "y": str(tmp_path / "y.fifo")})
    os.mkfifo(proc.opts["x"])
    os.mkfifo(proc.opts["y"])

    proc.start_threads()
    try:
        with open(path_a, "w") as wa, open(path_b, "w") as wb:
            wa.write(lib.encode_barrier(0) + "\n")
            wa.flush()
            assert _wait_until(lambda: proc._barrier_pending == {"b"})

            wb.write(lib.encode_data("in transit") + "\n")
            wb.flush()
            # delivered right away, while "b"'s own marker has still not arrived
            assert _wait_until(lambda: proc.received == [("b", "in transit")])
            assert proc._barrier_pending == {"b"}

            wb.write(lib.encode_barrier(0) + "\n")
            wb.flush()
            assert _wait_until(lambda: proc.closed_epochs != [])

        assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {"b": ["in transit"]})]
        assert proc.received == [("b", "in transit")]
    finally:
        proc.stop_threads(timeout=2)


def test_initiator_in_a_cycle_waits_for_its_own_marker_to_return(fifo_pair, tmp_path):
    a_to_b, b_to_a = fifo_pair

    class _Node(lib.FBPProcess):
        INPUT_PORTS = ["inf"]
        OUTPUT_PORTS = ["outf"]

        def __init__(self, *a, **kw):
            self.closed_epochs = []
            super().__init__(*a, **kw)

        def capture_node_state(self):
            return {"name": self.opts.get("name")}

        def _execdir(self):
            # Two nodes in one test process would otherwise share a directory,
            # and so a log, which real nodes never do.
            return self.opts["execdir"]

        def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, processed_upto):
            self.closed_epochs.append((epoch, halt, node_state, channel_buffers))

    # A cycle of two nodes: node_a -> node_b -> node_a.
    node_a = _Node(opts={"inf": b_to_a, "outf": a_to_b, "name": "a", "execdir": str(tmp_path / "a")})
    node_b = _Node(opts={"inf": a_to_b, "outf": b_to_a, "name": "b", "execdir": str(tmp_path / "b")})

    node_b.start_threads()
    node_a.start_threads()
    try:
        node_a._on_interact({"command": "start_snapshot", "args": {}})
        # node_a is the initiator: its own input port is pending until
        # the marker it just sent has gone all the way around through
        # node_b and back to it.
        assert node_a._barrier_pending == {"inf"}
        assert node_a.closed_epochs == []

        assert _wait_until(lambda: node_a.closed_epochs != [])
        # node_a self-initiated, so "inf" was tracked as pending for the
        # whole round (even though nothing arrived on it before its own
        # marker did) -- an empty list is still a real, correct channel
        # state entry, not the same as never having tracked that port.
        assert node_a.closed_epochs == [(0, False, {"name": "a"}, {"inf": []})]
        assert _wait_until(lambda: node_b.closed_epochs != [])
        # node_b instead first saw this round via the BARRIER arriving on
        # its own (only) input port, so that port was never "pending" at
        # all -- nothing to track.
        assert node_b.closed_epochs == [(0, False, {"name": "b"}, {})]
    finally:
        node_a.stop_threads(timeout=2)
        node_b.stop_threads(timeout=2)
