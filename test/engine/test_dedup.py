import json
import os
import threading
import time

import pytest

import debasher_runtime_lib as lib
import debasher_runtime_transport as transport


def _wait_until(predicate, timeout=5.0, interval=0.01):
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


@pytest.fixture
def fifo_path(tmp_path):
    path = tmp_path / "test.fifo"
    os.mkfifo(path)
    return str(path)


class _Recorder(lib.FBPProcess):
    INPUT_PORTS = ["inf"]

    def __init__(self, *a, **kw):
        self.received = []
        super().__init__(*a, **kw)

    def process_data(self, port_name, packet):
        self.received.append(packet)

    def capture_node_state(self):
        return {"received": list(self.received)}

    def restore_node_state(self, node_state):
        self.received = list(node_state["received"])

    def initialize_runtime(self):
        pass


class _TwoInputs(_Recorder):
    INPUT_PORTS = ["a", "b"]

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))


_OPTS = {"inf": "/dev/null"}


def _arrive(proc, port, payload, seq=None):
    """Delivers one DATA the way a reader thread does: through the real
    encode/decode round trip and the real _on_arrival, so the dedup check
    (G5) runs for real, exactly as it would from a live FIFO."""
    if proc._input_log is None:
        proc._open_input_log(0)
    line = lib.encode_data(payload, seq=seq)
    proc._on_arrival(port, lib.decode_envelope(line), line)


def _run_brain(proc):
    """Lets the brain thread process everything queued so far, then ends it."""
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


def _log_records(proc):
    return list(proc._input_log.replay(0))


def test_a_duplicate_is_dropped_before_it_is_logged_or_queued():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "first", seq=1)
    _arrive(proc, "inf", "again", seq=1)  # a replay's regenerated duplicate

    assert [r.envelope.payload for r in _log_records(proc)] == ["first"]
    assert proc._inbound_queue.qsize() == 1


def test_a_number_not_above_the_last_accepted_one_is_also_a_duplicate():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)
    _arrive(proc, "inf", "a2", seq=2)
    _arrive(proc, "inf", "b", seq=2)  # not above 2: also a duplicate

    _run_brain(proc)
    assert proc.received == ["a", "a2"]


def test_a_higher_number_is_accepted_and_moves_the_counters():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)
    _arrive(proc, "inf", "b", seq=2)

    assert proc._accepted_seq == {"inf": 2}
    _run_brain(proc)
    assert proc.received == ["a", "b"]
    assert proc._last_seq == {"inf": 2}


def test_a_gap_is_a_g8_error_naming_the_channel_and_the_missing_numbers():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError, match=r"'inf'.*missing 2 to 4") as excinfo:
        _arrive(proc, "inf", "b", seq=5)  # jumps from 1 to 5: 2, 3 and 4 are lost
    assert "inf" in str(excinfo.value)


def test_a_single_missing_number_is_named_without_a_range():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError, match=r"missing 2$"):
        _arrive(proc, "inf", "b", seq=3)  # only 2 is lost, not "2 to 2"


def test_a_gap_is_raised_before_anything_is_logged_or_queued():
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError):
        _arrive(proc, "inf", "b", seq=5)

    assert [r.envelope.payload for r in _log_records(proc)] == ["a"]
    assert proc._inbound_queue.qsize() == 1
    # The counter stays at the last one genuinely accepted, not at what
    # merely arrived: a relaunch must still see the gap as open.
    assert proc._accepted_seq == {"inf": 1}


def test_a_gap_kills_the_reader_thread_which_is_how_the_heartbeat_notices(fifo_path):
    # The reader thread dying from an uncaught exception is expected here
    # (same passive health-reporting design as elsewhere): pytest reports it
    # as a PytestUnhandledThreadExceptionWarning at its own next check, not
    # synchronously, so this only asserts on the resulting, observable state.
    proc = _Recorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data("a", seq=1) + "\n")
            w.write(lib.encode_data("b", seq=5) + "\n")
            w.flush()

        reader = proc._reader_threads["inf"]
        assert _wait_until(lambda: not reader.is_alive())
        assert not proc._all_threads_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_a_data_with_no_number_is_always_accepted_and_never_moves_the_counters():
    # decision 6: unnumbered DATA, from a source or a plain _PortWorker, is
    # not part of the numbering, so it never counts towards a duplicate.
    proc = _Recorder(opts=_OPTS)
    _arrive(proc, "inf", "a", seq=1)
    _arrive(proc, "inf", "from outside")  # no seq
    _arrive(proc, "inf", "b", seq=1)  # still a duplicate of "a", unaffected

    _run_brain(proc)
    assert proc.received == ["a", "from outside"]
    assert proc._accepted_seq == {"inf": 1}
    assert proc._last_seq == {"inf": 1}


def test_each_input_port_is_deduplicated_on_its_own():
    proc = _TwoInputs(opts={"a": "/dev/null", "b": "/dev/null"})
    _arrive(proc, "a", "a1", seq=1)
    _arrive(proc, "b", "b1", seq=1)  # same number, different channel: not a duplicate
    _arrive(proc, "a", "a1 again", seq=1)  # a duplicate on "a"

    _run_brain(proc)
    assert proc.received == [("a", "a1"), ("b", "b1")]
    assert proc._accepted_seq == {"a": 1, "b": 1}


def test_a_capture_reflects_what_the_brain_has_processed_not_what_the_reader_has_accepted():
    # Mirrors the same isolation the sender's out_seq needs (G5): a reader
    # thread can accept, log and queue a DATA on a port still pending in an
    # open round before the brain gets to it, so the checkpoint's last_seq
    # must come from the brain's own view, not the reader's live counter.
    proc = _TwoInputs(opts={"a": "/dev/null", "b": "/dev/null"})
    _arrive(proc, "a", "a1", seq=1)
    _run_brain(proc)
    assert proc._last_seq == {"a": 1}

    proc._on_interact({"command": "start_snapshot", "args": {}})  # "a" and "b" pending
    assert proc._barrier_last_seq == {"a": 1}

    # "b" arrives and is processed while the round stays open (G2): the
    # reader's own counter moves at once, but the brain's own mirror, and
    # the round's already-taken copy, must not.
    _arrive(proc, "b", "b1", seq=1)
    assert proc._accepted_seq == {"a": 1, "b": 1}
    _run_brain(proc)
    assert proc._last_seq == {"a": 1, "b": 1}
    assert proc._barrier_last_seq == {"a": 1}

    proc._close_barrier_round()
    with open(os.path.join(proc._checkpoints_dir(), "0.json")) as f:
        checkpoint = json.load(f)
    assert checkpoint["last_seq"] == {"a": 1}


def test_load_latest_checkpoint_returns_last_seq():
    proc = _Recorder(opts=_OPTS)
    proc._save_checkpoint(0, {}, {}, 0, [], {}, {"inf": 4}, {})

    _, _, _, _, _, last_seq, _ = proc._load_latest_checkpoint()
    assert last_seq == {"inf": 4}


def test_a_restored_node_drops_what_its_own_log_already_covers():
    # The guarantee (G5): a relaunched node does not accept, a second time,
    # what its own input log already holds; new arrivals after the numbers
    # already logged are still accepted normally.
    live = _Recorder(opts=_OPTS)
    _arrive(live, "inf", "a", seq=1)
    _arrive(live, "inf", "b", seq=2)
    # last_seq: {} (nothing processed yet)
    live._save_checkpoint(0, live.capture_node_state(), {}, 0, [], {}, {}, {})

    relaunched = _Recorder(opts=_OPTS)
    _, node_state, capture_pos, closed_ports, out_seq, last_seq, _ = relaunched._load_latest_checkpoint()
    relaunched.restore_node_state(node_state)
    relaunched._closed_ports = set(closed_ports)
    relaunched._out_seq = dict(out_seq)
    relaunched._last_seq = dict(last_seq)
    relaunched._accepted_seq = dict(last_seq)
    relaunched._open_input_log(capture_pos)
    relaunched._replay_input_log(capture_pos)  # reprocesses a (seq 1) and b (seq 2)

    assert relaunched._accepted_seq == {"inf": 2}
    assert relaunched.received == ["a", "b"]

    # The peer's own replay re-sends 1 and 2 (regenerated, same numbers) and
    # then a genuinely new one, 3.
    _arrive(relaunched, "inf", "a again", seq=1)
    _arrive(relaunched, "inf", "b again", seq=2)
    _arrive(relaunched, "inf", "c", seq=3)
    _run_brain(relaunched)

    assert relaunched.received == ["a", "b", "c"]


def test_a_dropped_fragment_never_moves_the_accepted_counter(fifo_path):
    proc = _Recorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        # A writer numbered its next message 7, and died half way through it:
        # what reaches the fifo is an unterminated fragment, its "seq": 7
        # included, that the resync line below must make disappear entirely.
        big = lib.encode_data("x" * 10000, seq=7)
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data("before", seq=1) + "\n")
            w.write(big[: len(big) // 2])
        with open(fifo_path, "w") as w:  # its relaunched incarnation
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_data("after", seq=2) + "\n")

        assert _wait_until(lambda: proc._accepted_seq.get("inf") == 2)
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)

    assert proc.received == ["before", "after"]
