import json
import os
import threading

import pytest

import debasher_runtime_lib as lib
import debasher_runtime_transport as transport


@pytest.fixture(autouse=True)
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


class _Relay(lib.FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]

    def process_data(self, port_name, packet):
        self.send_data("outf", packet)

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


class _Spawner(_Relay):
    """Also tries to send from a thread of its own, while process_data runs."""

    def __init__(self, *args, **kwargs):
        self.foreign_error = None
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        def other():
            try:
                self.send_data("outf", "from another thread")
            except RuntimeError as exc:
                self.foreign_error = exc

        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
        self.send_data("outf", packet)


class _Failing(_Relay):
    def process_data(self, port_name, packet):
        self.send_data("outf", packet)
        raise ValueError("process_data failed")


class _TwoOutputs(lib.FBPProcess):
    """Routes each packet to the output port it names, so that each port's own
    numbering can be told apart from the other's."""

    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["x", "y"]

    def process_data(self, port_name, packet):
        self.send_data(packet["port"], packet["val"])

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


_OPTS = {"inf": "/dev/null", "outf": "/dev/null"}


def _queued(proc, tag="outf"):
    """The DATA payloads waiting for the writer thread of `tag`, in order."""
    return [envelope.payload for envelope in _queued_envelopes(proc, tag)]


def _queued_envelopes(proc, tag="outf"):
    """The full DATA envelopes (payload and seq) waiting for the writer thread of `tag`."""
    return [lib.decode_envelope(line) for line in list(proc._outbound_queues[tag].queue)]


def _arrive(proc, port, payload):
    """Delivers one DATA item the way a reader thread does, opening the input log if needed."""
    if proc._input_log is None:
        proc._open_input_log(0)
    line = lib.encode_data(payload)
    proc._on_arrival(port, lib.decode_envelope(line), line)


def _run_brain(proc, items):
    """items: a list of (port, payload). Delivers them for real, through the input
    log, and runs the brain loop, on a thread of its own, until it is done."""
    for port, payload in items:
        _arrive(proc, port, payload)
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


def _process_on_the_brain_thread(proc, *packets):
    """Runs the brain loop, on a thread of its own, over the given packets, and waits for it to end."""
    for pos, packet in enumerate(packets, start=1):
        proc._inbound_queue.put((pos, "inf", "DATA", packet, None))
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


def test_a_node_cannot_send_outside_process_data():
    proc = _Relay(opts=_OPTS)

    with pytest.raises(RuntimeError, match="send_data"):
        proc.send_data("outf", 1)

    assert _queued(proc) == []


def test_what_a_node_sends_inside_process_data_on_the_brain_thread_reaches_its_writer():
    proc = _Relay(opts=_OPTS)

    _process_on_the_brain_thread(proc, 7, 8)

    assert _queued(proc) == [7, 8]


def test_a_thread_of_the_module_cannot_send_while_process_data_runs():
    proc = _Spawner(opts=_OPTS)

    _process_on_the_brain_thread(proc, 7)

    assert isinstance(proc.foreign_error, RuntimeError)
    assert _queued(proc) == [7]


def test_a_node_cannot_send_once_process_data_has_returned():
    proc = _Relay(opts=_OPTS)
    proc._run_process_data("inf", 1)

    with pytest.raises(RuntimeError):
        proc.send_data("outf", 2)

    assert _queued(proc) == [1]


def test_a_node_cannot_send_once_process_data_has_failed():
    proc = _Failing(opts=_OPTS)
    with pytest.raises(ValueError):
        proc._run_process_data("inf", 1)

    with pytest.raises(RuntimeError):
        proc.send_data("outf", 2)

    assert _queued(proc) == [1]


def test_a_node_can_send_while_it_replays_its_input_log():
    proc = _Relay(opts=_OPTS)
    proc._open_input_log(0)
    for packet in (5, 6):
        line = lib.encode_data(packet)
        proc._on_arrival("inf", lib.decode_envelope(line), line)

    proc._replay_input_log(0)

    assert _queued(proc) == [5, 6]


# --- G5: the sender numbers its DATA (5.2) --------------------------------


def test_send_data_numbers_each_message_starting_at_1(execdir):
    proc = _Relay(opts=_OPTS)
    _run_brain(proc, [("inf", "a"), ("inf", "b"), ("inf", "c")])

    assert [(e.payload, e.seq) for e in _queued_envelopes(proc)] == [
        ("a", 1),
        ("b", 2),
        ("c", 3),
    ]
    assert proc._out_seq == {"outf": 3}


def test_each_output_port_is_numbered_on_its_own(execdir):
    proc = _TwoOutputs(opts={"inf": "/dev/null", "x": "/dev/null", "y": "/dev/null"})
    _run_brain(
        proc,
        [
            ("inf", {"port": "x", "val": "a"}),
            ("inf", {"port": "y", "val": "p"}),
            ("inf", {"port": "x", "val": "b"}),
            ("inf", {"port": "x", "val": "c"}),
            ("inf", {"port": "y", "val": "q"}),
        ],
    )

    assert [(e.payload, e.seq) for e in _queued_envelopes(proc, "x")] == [
        ("a", 1),
        ("b", 2),
        ("c", 3),
    ]
    assert [(e.payload, e.seq) for e in _queued_envelopes(proc, "y")] == [("p", 1), ("q", 2)]


def test_a_capture_takes_the_sender_counters_at_that_instant_and_the_checkpoint_stores_them(
    execdir,
):
    proc = _Relay(opts=_OPTS)
    _run_brain(proc, [("inf", 1), ("inf", 2), ("inf", 3)])
    assert proc._out_seq == {"outf": 3}

    # A round opens as soon as the trigger is handled, before it closes (its
    # input port, "inf", is left pending): capture_node_state() and the
    # sender counters are taken right there, at the same instant.
    proc._on_interact({"command": "start_snapshot", "args": {}})
    assert proc._barrier_out_seq == {"outf": 3}

    proc._close_barrier_round()
    with open(os.path.join(proc._checkpoints_dir(), "0.json")) as f:
        checkpoint = json.load(f)
    assert checkpoint["out_seq"] == {"outf": 3}


def test_the_checkpoint_reflects_the_counters_at_capture_not_what_is_sent_while_the_round_stays_open(
    execdir,
):
    proc = _Relay(opts=_OPTS)
    _run_brain(proc, [("inf", 1), ("inf", 2)])
    assert proc._out_seq == {"outf": 2}

    # The round opens at once but its own input port, "inf", is left
    # pending, so it does not close here.
    proc._on_interact({"command": "start_snapshot", "args": {}})
    assert proc._barrier_out_seq == {"outf": 2}

    # More arrives while the round is still open: G2 says it is processed
    # and sent at once, seq 3, but that belongs to the next epoch, not to
    # the one already captured.
    _run_brain(proc, [("inf", 3)])
    assert proc._out_seq == {"outf": 3}
    assert proc._barrier_out_seq == {"outf": 2}

    proc._close_barrier_round()
    with open(os.path.join(proc._checkpoints_dir(), "0.json")) as f:
        checkpoint = json.load(f)
    assert checkpoint["out_seq"] == {"outf": 2}


def test_a_restored_checkpoint_makes_the_numbering_go_on_after_it(execdir):
    live = _Relay(opts=_OPTS)
    live._save_checkpoint(0, {}, {}, 0, set(), {"outf": 3}, {})

    relaunched = _Relay(opts=_OPTS)
    _, node_state, capture_pos, closed_ports, out_seq, last_seq = relaunched._load_latest_checkpoint()
    relaunched.restore_node_state(node_state)
    relaunched._closed_ports = set(closed_ports)
    relaunched._out_seq = dict(out_seq)
    relaunched._last_seq = dict(last_seq)
    relaunched._accepted_seq = dict(last_seq)

    _run_brain(relaunched, [("inf", "d"), ("inf", "e")])

    assert [(e.payload, e.seq) for e in _queued_envelopes(relaunched)] == [
        ("d", 4),
        ("e", 5),
    ]


def test_replay_regenerates_the_same_numbers_a_crashed_incarnation_had_used(execdir):
    # The guarantee (G5): a relaunched node's replay renumbers what it sends
    # again exactly as the crashed incarnation had, so a neighbor that
    # received those messages the first time recognizes them as duplicates.
    live = _Relay(opts=_OPTS)
    _run_brain(live, [("inf", 1), ("inf", 2), ("inf", 3)])
    live._save_checkpoint(
        0, live.capture_node_state(), {}, live._current_pos, set(), dict(live._out_seq), {}
    )
    while not live._outbound_queues["outf"].empty():  # drain what the checkpoint already covers
        live._outbound_queues["outf"].get_nowait()

    # More arrives after that checkpoint and is sent with seq 4 and 5.
    # Nothing here survives a crash except the input log: not a newer
    # checkpoint (none is taken) and not the outbound queue (memory, like a
    # real kill -9 destroys it).
    _run_brain(live, [("inf", 4), ("inf", 5)])
    assert [e.seq for e in _queued_envelopes(live)] == [4, 5]

    relaunched = _Relay(opts=_OPTS)
    _, node_state, capture_pos, closed_ports, out_seq, last_seq = relaunched._load_latest_checkpoint()
    relaunched.restore_node_state(node_state)
    relaunched._closed_ports = set(closed_ports)
    relaunched._out_seq = dict(out_seq)
    relaunched._last_seq = dict(last_seq)
    relaunched._accepted_seq = dict(last_seq)
    relaunched._open_input_log(capture_pos)
    relaunched._replay_input_log(capture_pos)

    assert [e.seq for e in _queued_envelopes(relaunched)] == [4, 5]
