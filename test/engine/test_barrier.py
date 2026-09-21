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

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, capture_pos, closed_ports):
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

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, capture_pos, closed_ports):
        self.closed_epochs.append((epoch, halt, node_state, channel_buffers))


class _Root(lib.FBPProcess):
    OUTPUT_PORTS = ["x"]

    def __init__(self, *a, **kw):
        self.closed_epochs = []
        super().__init__(*a, **kw)

    def capture_node_state(self):
        return {}

    def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, capture_pos, closed_ports):
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

        def _on_epoch_closed(self, epoch, halt, node_state, channel_buffers, capture_pos, closed_ports):
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


# --- ports whose writer has finished (CLOSE) ------------------------------------------------


class _ThreePorts(_BarrierWorker):
    INPUT_PORTS = ["a", "b", "c"]


_THREE_OPTS = {**_FAKE_OPTS, "c": "/dev/null"}


def _close(port):
    return (port, lib.TYPE_CLOSE, {})


def test_a_round_does_not_wait_for_a_port_whose_writer_finishes_while_it_is_open():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, _ROUND),  # the round opens, b is pending
            ("b", lib.TYPE_DATA, 5),  # in transit at the cut
            _close("b"),  # no marker will ever come from b
        ],
    )

    # The message of b stays in the channel state; the round closes with the CLOSE.
    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {"b": [5]})]


def test_a_close_after_the_marker_of_its_port_changes_nothing():
    proc = _ThreePorts(opts=_THREE_OPTS)
    _run_brain(proc, [("a", lib.TYPE_BARRIER, _ROUND), _close("a")])

    assert proc.closed_epochs == []
    assert proc._barrier_pending == {"b", "c"}


def test_a_round_that_opens_after_a_port_closed_does_not_wait_for_it():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_close("a"), ("b", lib.TYPE_BARRIER, _ROUND)])

    # It closes as its own marker arrives, and keeps no channel state for the closed port.
    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {})]


def test_the_marker_is_still_forwarded_when_a_round_opens_with_closed_ports():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_close("a"), ("b", lib.TYPE_BARRIER, _ROUND)])

    for port in ("x", "y"):
        assert lib.decode_envelope(_out(proc, port)) == lib.Envelope(
            type="BARRIER", payload={"epoch": 0, "halt": False}
        )


def test_a_node_whose_inputs_have_all_closed_starts_and_closes_a_round_like_a_source():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            _close("a"),
            _close("b"),
            ("trigger", lib.TYPE_INTERACT, {"command": "start_snapshot", "args": {}}),
        ],
    )

    assert [epoch for epoch, *_ in proc.closed_epochs] == [0]
    for port in ("x", "y"):
        assert lib.decode_envelope(_out(proc, port)).payload == {"epoch": 0, "halt": False}


def test_a_later_round_after_two_ports_closed_opens_and_closes_without_ending_the_brain_thread():
    proc = _ThreePorts(opts=_THREE_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_DATA, 1),
            ("b", lib.TYPE_DATA, 10),
            _close("a"),
            ("b", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # the round opens
            ("c", lib.TYPE_DATA, 100),  # in transit at the cut
            _close("c"),  # while the round is open
            ("b", lib.TYPE_DATA, 20),
            ("b", lib.TYPE_BARRIER, {"epoch": 1, "halt": False}),  # nothing left to wait for
        ],
    )

    # The CLOSE of c was in the log when the first round opened, but the brain thread had not
    # reached it: c was still pending, and its message is kept in the channel state.
    assert proc.closed_epochs == [
        (0, False, {"marker": "initial"}, {"c": [100]}),
        (1, False, {"marker": "initial"}, {}),
    ]


# --- control ports: input ports that carry only commands -------------------------------------


class _WithCommands(_BarrierWorker):
    INPUT_PORTS = ["inf", "commands"]
    CONTROL_PORTS = ["commands"]


class _OnlyCommands(_BarrierWorker):
    INPUT_PORTS = ["commands"]
    CONTROL_PORTS = ["commands"]


_COMMANDS_OPTS = {"inf": "/dev/null", "commands": "/dev/null", "x": "/dev/null", "y": "/dev/null"}
_START = {"command": "start_snapshot", "args": {}}


def test_an_initiator_whose_only_input_is_a_control_port_closes_its_round_when_it_is_triggered():
    proc = _OnlyCommands(opts=_COMMANDS_OPTS)
    _run_brain(proc, [("commands", lib.TYPE_INTERACT, _START)])

    assert [epoch for epoch, *_ in proc.closed_epochs] == [0]
    for port in ("x", "y"):
        assert lib.decode_envelope(_out(proc, port)).payload == {"epoch": 0, "halt": False}


def test_a_control_port_takes_no_part_in_a_round_that_a_peer_starts():
    proc = _WithCommands(opts=_COMMANDS_OPTS)
    # No command has been sent: the round starts elsewhere and reaches this node as a marker.
    _run_brain(proc, [("inf", lib.TYPE_BARRIER, _ROUND)])

    # It closes with that marker, and keeps no channel state for the control port.
    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {})]


def test_an_initiator_with_a_data_port_and_a_control_port_waits_only_for_the_data_port():
    proc = _WithCommands(opts=_COMMANDS_OPTS)
    _run_brain(proc, [("commands", lib.TYPE_INTERACT, _START)])
    assert proc._barrier_pending == {"inf"}
    assert proc.closed_epochs == []

    _run_brain(proc, [("inf", lib.TYPE_BARRIER, _ROUND)])
    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {"inf": []})]


def test_a_close_on_a_control_port_changes_nothing():
    proc = _WithCommands(opts=_COMMANDS_OPTS)
    _run_brain(proc, [_close("commands"), ("inf", lib.TYPE_BARRIER, _ROUND)])

    assert proc._closed_ports == set()
    assert proc.closed_epochs == [(0, False, {"marker": "initial"}, {})]


def test_control_ports_have_to_be_input_ports():
    class _Bad(_BarrierWorker):
        CONTROL_PORTS = ["z"]

    with pytest.raises(ValueError, match="CONTROL_PORTS"):
        _Bad(opts=_FAKE_OPTS)


# --- rounds that overlap: the newer one replaces the older -------------------------------------


class _Counting(_BarrierWorker):
    """Its node state is how many messages it had processed when it was captured."""

    def capture_node_state(self):
        return {"n": len(self.received)}


def _marker(port, epoch, halt=False):
    return (port, lib.TYPE_BARRIER, {"epoch": epoch, "halt": halt})


def _trigger(command):
    return ("trigger", lib.TYPE_INTERACT, {"command": command, "args": {}})


def test_a_marker_of_a_newer_round_replaces_the_open_one_and_captures_when_it_arrives():
    proc = _Counting(opts=_FAKE_OPTS)
    _run_brain(
        proc,
        [
            ("b", lib.TYPE_DATA, 1),
            _marker("a", 0),  # round 0 opens (one message processed), b is pending
            ("b", lib.TYPE_DATA, 2),
            _marker("a", 1),  # round 1 reaches the node: it replaces round 0
            ("b", lib.TYPE_DATA, 3),
            _marker("b", 1),
        ],
    )

    # Round 0 left nothing behind: the state is the one at the marker of round 1 (two messages),
    # and only what arrived after that marker is channel state.
    assert proc.closed_epochs == [(1, False, {"n": 2}, {"b": [3]})]
    # The marker of round 0 had already gone out, and the one of round 1 follows it.
    assert [lib.decode_envelope(_out(proc, "x")).payload["epoch"] for _ in range(2)] == [0, 1]


def test_a_marker_of_a_newer_snapshot_does_not_replace_an_open_halt():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_marker("a", 0, halt=True), _marker("a", 1)])
    assert (proc._barrier_epoch, proc._barrier_halt) == (0, True)

    _run_brain(proc, [_marker("b", 0, halt=True)])
    assert proc.closed_epochs == [(0, True, {"marker": "initial"}, {"b": []})]


def test_a_marker_of_a_newer_halt_replaces_an_open_snapshot():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_marker("a", 0), _marker("a", 1, halt=True), _marker("b", 1, halt=True)])

    assert proc.closed_epochs == [(1, True, {"marker": "initial"}, {"b": []})]


def test_a_marker_of_a_round_that_was_replaced_or_is_over_is_ignored():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    # b is slow: its marker for round 0 arrives after round 1 has replaced it, and settles nothing.
    _run_brain(proc, [_marker("a", 0), _marker("a", 1), _marker("b", 0)])
    assert proc._barrier_epoch == 1
    assert proc._barrier_pending == {"b"}

    # Round 1 closes with the marker of b. Later markers of rounds 1 and 0 open nothing.
    _run_brain(proc, [_marker("b", 1), _marker("a", 1), _marker("b", 0)])
    assert [epoch for epoch, *_ in proc.closed_epochs] == [1]
    assert proc._barrier_epoch is None


def test_a_snapshot_trigger_that_finds_a_round_open_changes_nothing_and_does_not_end_the_node():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_marker("a", 0), _trigger("start_snapshot"), ("b", lib.TYPE_DATA, 5)])

    assert (proc._barrier_epoch, proc._barrier_pending) == (0, {"b"})
    assert proc.received == [("b", 5)]  # the node went on processing
    assert lib.decode_envelope(_out(proc, "x")).payload["epoch"] == 0
    assert proc._outbound_queues["x"].empty()  # and no marker of a second round went out


def test_a_shutdown_trigger_that_finds_a_snapshot_open_replaces_it_with_the_halt():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_marker("a", 0), _trigger("shutdown")])

    assert (proc._barrier_epoch, proc._barrier_halt, proc._barrier_pending) == (1, True, {"a", "b"})
    assert [lib.decode_envelope(_out(proc, "x")).payload for _ in range(2)] == [
        {"epoch": 0, "halt": False},
        {"epoch": 1, "halt": True},
    ]
    _run_brain(proc, [_marker("a", 1, halt=True), _marker("b", 1, halt=True)])
    assert [(epoch, halt) for epoch, halt, *_ in proc.closed_epochs] == [(1, True)]


def test_a_shutdown_trigger_that_finds_a_halt_open_changes_nothing():
    proc = _BarrierWorker(opts=_FAKE_OPTS)
    _run_brain(proc, [_marker("a", 0, halt=True), _trigger("shutdown")])

    assert (proc._barrier_epoch, proc._barrier_pending) == (0, {"b"})
    assert proc._outbound_queues["x"].qsize() == 1
