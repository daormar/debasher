import errno
import json
import os
import shutil
import threading
import time

import pytest

import debasher_runtime_inputlog as inputlog
import debasher_runtime_lib as lib


def _wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture(autouse=True)
def execdir(tmp_path, monkeypatch):
    # The node's own directory. A relaunched node gets the same one.
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "node"))
    return tmp_path / "node"


class _Fanin(lib.FBPProcess):
    """
    A node whose state is the whole history of what it processed, in order,
    so that any difference in what it received, or in the order it processed
    it, shows up in the state.
    """

    INPUT_PORTS = ["a", "b"]

    def __init__(self, *args, **kwargs):
        self.seen = []
        self.positions = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.seen.append((port_name, packet))
        self.positions.append(self._current_pos)

    def capture_node_state(self):
        return {"seen": [list(item) for item in self.seen]}

    def restore_node_state(self, node_state):
        self.seen = [tuple(item) for item in node_state["seen"]]

    def initialize_runtime(self):
        pass


def _opts(tmp_path, ports=("a", "b")):
    opts = {}
    for port in ports:
        path = str(tmp_path / f"{port}.fifo")
        if not os.path.exists(path):
            os.mkfifo(path)
        opts[port] = path
    return opts


def _arrive(proc, port, envelope_type, payload):
    """Delivers one item the way a reader thread does, once the node has its log open."""
    if proc._input_log is None:
        proc._open_input_log(0)
    line = json.dumps({"type": envelope_type, "payload": payload})
    proc._on_arrival(port, lib.Envelope(envelope_type, payload), line)


_ROUND = {"epoch": 0, "halt": False}


def _round(epoch, halt=False):
    return {"epoch": epoch, "halt": halt}


def _process(proc, items):
    """Delivers the items and lets the brain thread process everything that is queued."""
    for port, envelope_type, payload in items:
        _arrive(proc, port, envelope_type, payload)
    proc._inbound_queue.put(lib._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(5)
    assert not brain.is_alive()


def _crash(proc):
    """A killed process leaves no open descriptor behind, and does nothing else."""
    proc._input_log.close()


def _relaunch(tmp_path, cls=_Fanin, ports=("a", "b")):
    node = cls(opts=_opts(tmp_path, ports))
    node._halted.set()
    node.run()
    return node


def _data(port, value):
    return (port, lib.TYPE_DATA, value)


# --- a node comes back to the state it would have had ---------------------


def test_a_node_that_crashes_before_its_first_checkpoint_recovers_everything_it_had_received(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _data("b", 2), _data("a", 3)])
    _crash(live)

    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", 1), ("b", 2), ("a", 3)]
    assert relaunched.capture_node_state() == live.capture_node_state()


def test_recovery_reproduces_the_order_across_ports_not_port_by_port(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _data("b", 2), _data("a", 3), _data("b", 4)])
    _crash(live)

    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", 1), ("b", 2), ("a", 3), ("b", 4)]


def test_a_message_that_was_still_waiting_in_the_queue_when_the_node_crashed_is_not_lost(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _data("b", 2)])
    # Three more arrive while the brain thread is busy with something else: they are
    # written to the log the moment they arrive, and the node dies before it gets to them.
    for item in (_data("a", 3), _data("b", 4), _data("a", 5)):
        _arrive(live, *item)
    assert live.seen == [("a", 1), ("b", 2)]
    _crash(live)

    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", 1), ("b", 2), ("a", 3), ("b", 4), ("a", 5)]


def test_a_message_processed_after_the_snapshot_and_before_the_round_closes_is_recovered(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(
        live,
        [
            _data("a", 10),
            ("a", lib.TYPE_BARRIER, _ROUND),  # the state is captured here
            _data("b", 90),  # in transit at the cut, processed while the round is open
            ("b", lib.TYPE_BARRIER, _ROUND),  # the round closes and the checkpoint is written
        ],
    )
    assert live.seen == [("a", 10), ("b", 90)]
    _crash(live)

    relaunched = _relaunch(tmp_path)
    # The checkpoint holds only what came before the capture; the rest comes back from the log.
    assert relaunched.seen == [("a", 10), ("b", 90)]


def test_recovery_after_a_checkpoint_replays_only_what_came_after_it(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(
        live,
        [
            _data("a", 1),
            _data("b", 2),
            ("a", lib.TYPE_BARRIER, _ROUND),  # position 3
            ("b", lib.TYPE_BARRIER, _ROUND),  # position 4, the round closes
            _data("a", 5),  # position 5
            _data("b", 6),  # position 6
        ],
    )
    _crash(live)

    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == live.seen == [("a", 1), ("b", 2), ("a", 5), ("b", 6)]
    # Only the two messages after position 3 were executed again.
    assert relaunched.positions == [5, 6]


def test_after_a_halt_the_node_resumes_in_the_state_it_had_when_it_stopped(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(
        live,
        [
            _data("a", 1),
            ("a", lib.TYPE_BARRIER, _round(0, halt=True)),  # position 2, the state is captured
            _data("b", 2),  # in transit at the cut, processed before the round closes
            ("b", lib.TYPE_BARRIER, _round(0, halt=True)),  # the round closes and the node stops
        ],
    )
    assert live._halted.is_set()
    assert live.seen == [("a", 1), ("b", 2)]
    _crash(live)

    resumed = _relaunch(tmp_path)
    assert resumed.seen == [("a", 1), ("b", 2)]
    # What is executed again is exactly what the node had processed after capturing its state.
    assert resumed.positions == [3]


def test_recovery_restores_the_latest_checkpoint_and_numbering_goes_on_after_the_log(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), ("a", lib.TYPE_BARRIER, _ROUND), ("b", lib.TYPE_BARRIER, _ROUND), _data("b", 2)])
    _crash(live)

    relaunched = _relaunch(tmp_path)
    assert relaunched._last_epoch == 0
    # The log holds four records, so the next item gets position 5.
    assert relaunched._input_log.next_pos == 5


def test_the_log_holds_every_kind_of_item_but_only_data_is_replayed(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(
        live,
        [
            _data("a", 1),
            ("a", lib.TYPE_INTERACT, {"command": "unknown", "args": {}}),
            _data("b", 2),
            ("a", lib.TYPE_CLOSE, {}),
        ],
    )
    _crash(live)

    kinds = [r.envelope.type for r in lib._InputLog(str(tmp_path / "node" / "log"), 10**9, 10**9).replay(0)]
    assert kinds == ["DATA", "INTERACT", "DATA", "CLOSE"]
    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", 1), ("b", 2)]


def test_recovery_reads_the_log_and_writes_nothing_to_it(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _data("b", 2)])
    _crash(live)
    log_dir = tmp_path / "node" / "log"
    before = {n: (log_dir / n).read_bytes() for n in os.listdir(log_dir)}

    _relaunch(tmp_path)
    assert {n: (log_dir / n).read_bytes() for n in os.listdir(log_dir)} == before


def test_a_torn_tail_left_by_the_crash_is_ignored_and_numbering_goes_on(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _data("b", 2)])
    _crash(live)
    segment = tmp_path / "node" / "log" / "1.log"
    with open(segment, "ab") as f:
        f.write(b'{"pos": 3, "port": "a", "env": {"type": "DA')

    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", 1), ("b", 2)]
    assert relaunched._input_log.next_pos == 3


def test_recovery_fails_loudly_when_the_log_has_a_hole(tmp_path):
    class _Small(_Fanin):
        INPUT_LOG_SEGMENT_BYTES = 200

    live = _Small(opts=_opts(tmp_path))
    _process(live, [_data("a", n) for n in range(1, 13)])
    _crash(live)
    names = sorted(os.listdir(tmp_path / "node" / "log"), key=lambda n: int(n[: -len(".log")]))
    assert len(names) >= 3
    os.remove(tmp_path / "node" / "log" / names[1])

    node = _Small(opts=_opts(tmp_path))
    node._halted.set()
    with pytest.raises(ValueError, match="missing"):
        node.run()


# --- the size of the log stays bounded --------------------------------------


def test_the_log_is_pruned_after_checkpoints_and_recovery_still_works(tmp_path):
    class _Pruning(_Fanin):
        INPUT_LOG_SEGMENT_BYTES = 300
        CHECKPOINT_RETENTION = 2

    live = _Pruning(opts=_opts(tmp_path))
    items = []
    for epoch in range(6):
        items += [_data("a", epoch * 10 + 1), _data("b", epoch * 10 + 2)]
        items += [("a", lib.TYPE_BARRIER, _round(epoch)), ("b", lib.TYPE_BARRIER, _round(epoch))]
    items += [_data("a", 100)]
    _process(live, items)
    _crash(live)

    names = sorted(os.listdir(tmp_path / "node" / "log"), key=lambda n: int(n[: -len(".log")]))
    assert int(names[0][: -len(".log")]) > 1, "the oldest segments should have been deleted"
    checkpoints = sorted(os.listdir(tmp_path / "node" / "checkpoints"))
    assert len(checkpoints) == 2

    # Every checkpoint that is kept can still be recovered from: the log holds
    # everything after the position that each one reflects, not only the newest.
    for name in checkpoints:
        with open(tmp_path / "node" / "checkpoints" / name) as f:
            processed_upto = json.load(f)["processed_upto"]
        assert list(lib._InputLog(str(tmp_path / "node" / "log"), 10**9, 10**9).replay(processed_upto))

    relaunched = _relaunch(tmp_path, _Pruning)
    assert relaunched.seen == live.seen


def test_a_retained_checkpoint_that_cannot_be_read_aborts_the_prune_with_an_error(tmp_path):
    class _Keeping(_Fanin):
        CHECKPOINT_RETENTION = 2

    node = _Keeping(opts=_opts(tmp_path))
    node._open_input_log(0)
    node._save_checkpoint(0, {"seen": []}, {}, 0, [])
    node._save_checkpoint(1, {"seen": []}, {}, 0, [])
    # Saving epoch 2 keeps epochs 2 and 1, so epoch 1 is the oldest one kept.
    (tmp_path / "node" / "checkpoints" / "1.json").write_text("not json")

    with pytest.raises(RuntimeError, match="cannot read"):
        node._save_checkpoint(2, {"seen": []}, {}, 0, [])
    # The checkpoint that was being saved is on disk all the same.
    assert (tmp_path / "node" / "checkpoints" / "2.json").exists()


# --- failures while writing the log ------------------------------------------


def _send(path, *envelopes):
    with open(path, "w") as w:
        for line in envelopes:
            w.write(line + "\n")


def test_a_log_that_reaches_its_cap_ends_the_reader_thread_and_keeps_what_it_holds(tmp_path):
    class _Capped(_Fanin):
        INPUT_LOG_MAX_BYTES = 600

    opts = _opts(tmp_path)
    node = _Capped(opts=opts)
    node.start_threads()
    try:
        _send(opts["a"], *[lib.encode_data(n) for n in range(30)])
        assert _wait_until(lambda: not node._reader_threads["a"].is_alive())
        # The heartbeat would not report this node as healthy any more.
        assert not node._all_threads_alive()
        held = [r.envelope.payload for r in node._input_log.replay(0)]
        assert held == list(range(len(held))) and 0 < len(held) < 30
        # Everything that was logged reached the brain thread, in order.
        assert _wait_until(lambda: len(node.seen) == len(held))
        assert [packet for _, packet in node.seen] == held
    finally:
        node.stop_threads(timeout=2)


def test_after_a_failed_write_no_reader_thread_can_append_behind_the_fragment(tmp_path, monkeypatch):
    opts = _opts(tmp_path)
    node = _Fanin(opts=opts)
    node.start_threads()
    try:
        _send(opts["a"], lib.encode_data("first"))
        assert _wait_until(lambda: node.seen == [("a", "first")])

        real_write_all = inputlog._write_all

        def failing_write_all(fd, data):
            os.write(fd, data[: len(data) // 2])
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(inputlog, "_write_all", failing_write_all)
        _send(opts["a"], lib.encode_data("torn"))
        assert _wait_until(lambda: not node._reader_threads["a"].is_alive())

        # The fault is gone, but the other port's reader is refused as well.
        monkeypatch.setattr(inputlog, "_write_all", real_write_all)
        _send(opts["b"], lib.encode_data("behind the fragment"))
        assert _wait_until(lambda: not node._reader_threads["b"].is_alive())
    finally:
        node.stop_threads(timeout=2)

    # What the log holds is the record before the failure, and the fragment is a torn tail.
    assert [r.envelope.payload for r in lib._InputLog(str(tmp_path / "node" / "log"), 10**9, 10**9).replay(0)] == ["first"]
    relaunched = _relaunch(tmp_path)
    assert relaunched.seen == [("a", "first")]


# --- how the log gets opened -------------------------------------------------


def test_an_item_that_arrives_before_the_log_is_open_is_refused(tmp_path):
    node = _Fanin(opts=_opts(tmp_path))
    with pytest.raises(RuntimeError, match="input log"):
        node._on_arrival("a", lib.Envelope(lib.TYPE_DATA, 1), lib.encode_data(1))


def test_a_node_driven_without_run_gets_its_log_opened_by_start_threads(tmp_path):
    opts = _opts(tmp_path)
    node = _Fanin(opts=opts)
    node.start_threads()
    try:
        _send(opts["a"], lib.encode_data("x"))
        assert _wait_until(lambda: node.seen == [("a", "x")])
        assert node._input_log is not None
        assert [r.pos for r in node._input_log.replay(0)] == [1]
    finally:
        node.stop_threads(timeout=2)


# --- the ports whose writer has said CLOSE ------------------------------------
#
# Three input ports. The items below are the ones of a node whose round opens at
# the marker on b (position 4). Port a closed before it (position 3) and port c
# after it (position 6), with a message of c in between (position 5).


class _Three(_Fanin):
    INPUT_PORTS = ["a", "b", "c"]


_THREE = ("a", "b", "c")


def _close(port):
    return (port, lib.TYPE_CLOSE, {})


def _marker(port, epoch=0):
    return (port, lib.TYPE_BARRIER, _round(epoch))


_A_ROUND_OPENING_BETWEEN_TWO_CLOSES = [
    _data("a", 1),
    _data("b", 10),
    _close("a"),
    _marker("b"),
    _data("c", 100),
    _close("c"),
    _data("b", 20),
]


def _read_checkpoint(node, epoch):
    with open(os.path.join(node._checkpoints_dir(), f"{epoch}.json")) as f:
        return json.load(f)


def test_a_checkpoint_holds_the_ports_whose_close_the_node_had_processed_when_the_round_opened(tmp_path):
    live = _Three(opts=_opts(tmp_path, _THREE))
    # Every item is in the log before the brain thread starts, so the reader threads have
    # already seen the CLOSE of c when the round opens; the node has not got to it yet.
    _process(live, _A_ROUND_OPENING_BETWEEN_TWO_CLOSES)
    assert live._closed_ports == {"a", "c"}
    live._close_barrier_round()

    checkpoint = _read_checkpoint(live, 0)
    assert checkpoint["processed_upto"] == 4
    assert checkpoint["closed_ports"] == ["a"]


def test_a_relaunched_node_knows_again_which_ports_had_closed(tmp_path):
    live = _Three(opts=_opts(tmp_path, _THREE))
    _process(live, _A_ROUND_OPENING_BETWEEN_TWO_CLOSES)
    live._close_barrier_round()
    _crash(live)

    relaunched = _relaunch(tmp_path, _Three, _THREE)
    # a comes from the checkpoint, c from the CLOSE that the log holds after it.
    assert relaunched._closed_ports == {"a", "c"}
    assert relaunched.capture_node_state() == live.capture_node_state()


def test_a_port_closed_long_ago_is_still_closed_once_the_log_that_recorded_its_close_is_gone(tmp_path):
    live = _Three(opts=_opts(tmp_path, _THREE))
    _process(live, [_data("a", 1), _close("a"), _marker("b")])
    live._close_barrier_round()
    _crash(live)
    # What pruning does to every segment that ends at or below the checkpoint's position.
    shutil.rmtree(os.path.join(os.environ["DEBASHER_PROCESS_EXECDIR"], "log"))

    relaunched = _relaunch(tmp_path, _Three, _THREE)
    assert relaunched._closed_ports == {"a"}


def test_a_replay_that_finds_a_message_after_the_close_of_its_port_fails_loudly(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _close("a"), _data("a", 2)])
    _crash(live)

    with pytest.raises(ValueError, match="already received CLOSE"):
        _relaunch(tmp_path)


def test_a_message_after_a_close_that_the_checkpoint_recorded_also_fails_loudly(tmp_path):
    live = _Fanin(opts=_opts(tmp_path))
    _process(live, [_data("a", 1), _close("a"), _marker("b")])
    live._close_barrier_round()
    _arrive(live, "a", lib.TYPE_DATA, 2)
    _crash(live)

    with pytest.raises(ValueError, match="already received CLOSE"):
        _relaunch(tmp_path)


def test_after_a_relaunch_the_readers_of_closed_ports_drop_what_their_writers_send(tmp_path):
    opts = _opts(tmp_path)
    live = _Fanin(opts=opts)
    _process(live, [_data("a", 1), _close("a")])
    _crash(live)

    node = _Fanin(opts=opts)
    runner = threading.Thread(target=node.run, daemon=True)
    runner.start()
    try:
        assert _wait_until(lambda: len(node._reader_threads) == 2)
        # The writer of a is relaunched and says more; the writer of b has never said CLOSE.
        with open(opts["a"], "w") as w:
            w.write("\n" + lib.encode_hello() + "\n" + lib.encode_data(2) + "\n")
        with open(opts["b"], "w") as w:
            w.write(lib.encode_data(3) + "\n")
        assert _wait_until(lambda: ("b", 3) in node.seen)
        time.sleep(0.3)  # what the reader of a was sent has been read by now

        assert node.seen == [("a", 1), ("b", 3)]
        assert [(r.port, r.envelope.type) for r in node._input_log.replay(0)] == [
            ("a", "DATA"),
            ("a", "CLOSE"),
            ("b", "DATA"),
        ]
        assert node._reader_threads["a"].is_alive()
    finally:
        node._halted.set()
        runner.join(5)
