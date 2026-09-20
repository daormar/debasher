import json
import os
import threading
import time

import pytest

import debasher_runtime_lib as lib


def _wait_until(predicate, timeout=10.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture(autouse=True)
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


class _Node(lib.FBPProcess):
    """Keeps what it processes, together with the position of each item, and its state is what it kept."""

    INPUT_PORTS = ["a", "b"]

    def __init__(self, *args, **kwargs):
        self.seen = []
        self.processed = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.seen.append(packet)
        self.processed.append((self._current_pos, port_name, packet))

    def capture_state(self):
        return {"seen": list(self.seen)}

    def restore_state(self, state):
        self.seen = list(state["seen"])

    def initialize_runtime(self):
        pass


_OPTS = {"a": "/dev/null", "b": "/dev/null"}


def _arrive(proc, port, envelope_type, payload):
    """Delivers one item the way a reader thread does, once the node has its log open."""
    if proc._input_log is None:
        proc._open_input_log(0)
    line = json.dumps({"type": envelope_type, "payload": payload})
    proc._on_arrival(port, lib.Envelope(envelope_type, payload), line)


def _run_brain(proc, items):
    for port, envelope_type, payload in items:
        _arrive(proc, port, envelope_type, payload)
    proc._inbound_queue.put(lib._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(5)
    assert not brain.is_alive()


def _checkpoint(execdir, epoch):
    with open(execdir / "checkpoints" / f"{epoch}.json") as f:
        return json.load(f)


# --- positions are handed out at arrival --------------------------------


def test_positions_start_at_one_and_run_across_ports_and_item_types():
    proc = _Node(opts=_OPTS)
    _arrive(proc, "a", lib.TYPE_DATA, "x")
    _arrive(proc, "b", lib.TYPE_DATA, "y")
    _arrive(proc, "a", lib.TYPE_BARRIER, {"epoch": 0, "halt": False})
    _arrive(proc, "b", lib.TYPE_INTERACT, {"command": "start_snapshot", "args": {}})
    _arrive(proc, "a", lib.TYPE_CLOSE, {})

    items = [proc._inbound_queue.get_nowait() for _ in range(5)]
    assert [item[0] for item in items] == [1, 2, 3, 4, 5]
    assert [item[1:3] for item in items] == [
        ("a", "DATA"),
        ("b", "DATA"),
        ("a", "BARRIER"),
        ("b", "INTERACT"),
        ("a", "CLOSE"),
    ]
    assert items[0][3] == "x"


def test_a_worker_without_positions_keeps_the_plain_three_part_item():
    class _Plain(lib._PortWorker):
        def _input_ports(self):
            return {}

        def _output_ports(self):
            return {}

    proc = _Plain(opts={})
    proc._on_arrival("some node", lib.Envelope(lib.TYPE_DATA, {"x": 1}), "unused")
    assert proc._inbound_queue.get_nowait() == ("some node", lib.TYPE_DATA, {"x": 1})


def test_the_brain_thread_knows_the_position_of_the_item_it_is_processing(execdir):
    proc = _Node(opts=_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_DATA, "first"),
            ("b", lib.TYPE_INTERACT, {"command": "unknown", "args": {}}),
            ("b", lib.TYPE_DATA, "third"),
        ],
    )
    assert proc.processed == [(1, "a", "first"), (3, "b", "third")]
    assert proc._current_pos == 3


def test_the_order_of_the_positions_is_the_order_in_which_items_are_processed(execdir):
    # Several reader threads, each on its own real fifo, delivering as fast as they can.
    ports = [f"p{i}" for i in range(6)]
    per_port = 250

    class _Fanin(_Node):
        INPUT_PORTS = ports

    opts = {}
    for port in ports:
        opts[port] = str(execdir / f"{port}.fifo")
        os.mkfifo(opts[port])

    proc = _Fanin(opts=opts)
    proc.start_threads()

    def send(port):
        with open(opts[port], "w") as w:
            for n in range(per_port):
                w.write(lib.encode_data(n) + "\n")

    senders = [threading.Thread(target=send, args=(port,)) for port in ports]
    try:
        for sender in senders:
            sender.start()
        assert _wait_until(lambda: len(proc.processed) == len(ports) * per_port)
    finally:
        for sender in senders:
            sender.join(5)
        proc.stop_threads(timeout=2)

    # Every position was processed once, in position order.
    assert [pos for pos, _, _ in proc.processed] == list(range(1, len(ports) * per_port + 1))
    # And each channel kept its own order.
    for port in ports:
        assert [packet for _, p, packet in proc.processed if p == port] == list(range(per_port))


# --- the checkpoint records the position that captured its state --------


def test_a_round_opened_by_a_peers_marker_records_the_position_of_that_marker(execdir):
    proc = _Node(opts=_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_DATA, 1),
            ("b", lib.TYPE_DATA, 2),
            ("a", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # position 3: the state is captured here
            ("b", lib.TYPE_DATA, 5),  # in transit at the cut
            ("b", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # the round closes
        ],
    )

    checkpoint = _checkpoint(execdir, 0)
    assert checkpoint["processed_upto"] == 3
    # The state is exactly what had been processed up to that position, no more,
    # while what arrived in transit is kept as the channel state as well as processed.
    assert checkpoint["state"] == {"seen": [1, 2]}
    assert checkpoint["channel_state"] == {"b": [5]}
    assert proc.seen == [1, 2, 5]


def test_a_round_started_by_interact_records_the_position_of_that_interact(execdir):
    class _One(_Node):
        INPUT_PORTS = ["a"]

    proc = _One(opts={"a": "/dev/null"})
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_DATA, 1),
            ("a", lib.TYPE_INTERACT, {"command": "start_snapshot", "args": {}}),  # position 2
            ("a", lib.TYPE_DATA, 3),
            ("a", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # the marker comes back around
        ],
    )

    checkpoint = _checkpoint(execdir, 0)
    assert checkpoint["processed_upto"] == 2
    assert checkpoint["state"] == {"seen": [1]}


def test_the_position_is_taken_when_the_round_opens_not_when_it_closes(execdir):
    proc = _Node(opts=_OPTS)
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # position 1
            ("b", lib.TYPE_DATA, "later"),
            ("b", lib.TYPE_DATA, "later still"),
            ("b", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # position 4
        ],
    )
    assert _checkpoint(execdir, 0)["processed_upto"] == 1


def test_a_position_belongs_to_one_round_only(execdir):
    proc = _Node(opts={"a": "/dev/null", "b": "/dev/null"})
    _run_brain(
        proc,
        [
            ("a", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),  # position 1
            ("b", lib.TYPE_BARRIER, {"epoch": 0, "halt": False}),
            ("a", lib.TYPE_DATA, "between"),
            ("b", lib.TYPE_BARRIER, {"epoch": 1, "halt": False}),  # position 4
            ("a", lib.TYPE_BARRIER, {"epoch": 1, "halt": False}),
        ],
    )
    assert _checkpoint(execdir, 0)["processed_upto"] == 1
    assert _checkpoint(execdir, 1)["processed_upto"] == 4


def test_a_root_node_that_starts_a_round_before_processing_anything_records_zero(execdir):
    class _Root(_Node):
        INPUT_PORTS = []

    proc = _Root(opts={})
    proc._on_interact({"command": "start_snapshot", "args": {}})
    assert _checkpoint(execdir, 0)["processed_upto"] == 0


# --- the schema and the restart -----------------------------------------


def test_load_latest_checkpoint_returns_the_position(execdir):
    proc = _Node(opts=_OPTS)
    proc._save_checkpoint(2, {"seen": ["s"]}, {}, 12)
    assert proc._load_latest_checkpoint() == (2, {"seen": ["s"]}, 12)


def test_a_checkpoint_written_before_positions_existed_is_refused_by_its_version(execdir):
    proc = _Node(opts=_OPTS)
    os.makedirs(execdir / "checkpoints")
    with open(execdir / "checkpoints" / "0.json", "w") as f:
        json.dump({"schema_version": 1, "epoch": 0, "state": {}, "channel_state": {}}, f)
    with pytest.raises(ValueError, match="schema version"):
        proc._load_latest_checkpoint()


class _NoPorts(_Node):
    INPUT_PORTS = []


def test_a_restored_checkpoint_makes_the_positions_go_on_after_its_own(execdir):
    _NoPorts(opts={})._save_checkpoint(4, {"seen": []}, {}, 40)

    proc = _NoPorts(opts={})
    proc._halted.set()
    proc.run()
    assert proc._input_log.next_pos == 41

    _arrive(proc, "a", lib.TYPE_DATA, "next")
    assert _drain(proc) == [(41, "a", lib.TYPE_DATA, "next")]


def test_a_node_with_no_checkpoint_numbers_from_one(execdir):
    proc = _NoPorts(opts={})
    proc._halted.set()
    proc.run()
    assert proc._input_log.next_pos == 1


def _drain(proc):
    items = []
    while not proc._inbound_queue.empty():
        item = proc._inbound_queue.get_nowait()
        if item is not lib._STOP:
            items.append(item)
    return items
