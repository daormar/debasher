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


class _WriterOnly(transport._PortWorker):
    def _input_ports(self):
        return {}

    def _output_ports(self):
        return {"outf": "outf"}

    def _brain_loop(self):
        while self._inbound_queue.get() is not transport._STOP:
            pass


class _Sender(lib.FBPProcess):
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


_OPTS = {"inf": "/dev/null"}


def _arrive(proc, port, envelope_type, value):
    """Delivers one item the way a reader thread does, through the real
    encode/decode round trip and the real _on_arrival. `value` is the
    payload for DATA, or the claimed last_seq (possibly None) for CLOSE."""
    if proc._input_log is None:
        proc._open_input_log(0)
    if envelope_type == "DATA":
        line = lib.encode_data(value)
    elif envelope_type == "CLOSE":
        line = lib.encode_close(value)
    else:
        raise ValueError(envelope_type)
    proc._on_arrival(port, lib.decode_envelope(line), line)


def _arrive_data(proc, port, payload, seq):
    if proc._input_log is None:
        proc._open_input_log(0)
    line = lib.encode_data(payload, seq=seq)
    proc._on_arrival(port, lib.decode_envelope(line), line)


def _log_records(proc):
    return list(proc._input_log.replay(0))


def test_close_carries_the_senders_last_number(fifo_path):
    proc = _Sender(opts={"inf": "/dev/null", "outf": fifo_path})
    proc.start_threads()
    with open(fifo_path, "r") as r:
        proc._inbound_queue.put((1, "inf", "DATA", "a", None))
        proc._inbound_queue.put((2, "inf", "DATA", "b", None))
        proc._inbound_queue.put(transport._STOP)
        assert _wait_until(lambda: not proc._brain_thread.is_alive())
        proc.stop_threads(timeout=2)

        lines = [line for line in r.read().splitlines() if line]

    envelopes = [lib.decode_envelope(line) for line in lines]
    assert [e.type for e in envelopes] == ["HELLO", "DATA", "DATA", "CLOSE"]
    assert envelopes[-1].payload == {"last_seq": 2}


def test_a_plain_port_worker_close_carries_no_last_seq(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    with open(fifo_path, "r") as r:
        proc.send_data("outf", 1)
        proc.stop_threads(timeout=2)
        lines = [line for line in r.read().splitlines() if line]

    envelopes = [lib.decode_envelope(line) for line in lines]
    assert envelopes[-1].type == "CLOSE"
    assert envelopes[-1].payload == {}


def test_a_close_that_matches_what_was_accepted_is_not_an_error():
    proc = _Recorder(opts=_OPTS)
    _arrive_data(proc, "inf", "a", seq=1)
    _arrive_data(proc, "inf", "b", seq=2)

    _arrive(proc, "inf", "CLOSE", 2)  # claims 2: matches what was accepted

    assert [r.envelope.type for r in _log_records(proc)] == ["DATA", "DATA", "CLOSE"]


def test_a_close_claiming_more_than_was_accepted_is_a_g8_error():
    proc = _Recorder(opts=_OPTS)
    _arrive_data(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError, match=r"'inf'.*missing 2 to 4") as excinfo:
        _arrive(proc, "inf", "CLOSE", 4)  # claims 4, only 1 was ever accepted
    assert "inf" in str(excinfo.value)


def test_a_single_missing_message_before_close_is_named_without_a_range():
    proc = _Recorder(opts=_OPTS)
    _arrive_data(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError, match=r"missing 2$"):
        _arrive(proc, "inf", "CLOSE", 2)  # only 2 is lost, not "2 to 2"


def test_close_is_logged_and_queued_even_though_it_raises():
    # Unlike a DATA gap, nothing ever sends CLOSE a second time: losing it to
    # an early raise would leave the port looking unfinished forever, so the
    # error comes only after CLOSE is itself durably recorded.
    proc = _Recorder(opts=_OPTS)
    _arrive_data(proc, "inf", "a", seq=1)

    with pytest.raises(ValueError):
        _arrive(proc, "inf", "CLOSE", 4)

    assert [r.envelope.type for r in _log_records(proc)] == ["DATA", "CLOSE"]
    assert proc._inbound_queue.qsize() == 2


def test_a_close_with_no_claim_is_never_an_error():
    proc = _Recorder(opts=_OPTS)
    _arrive_data(proc, "inf", "a", seq=1)

    _arrive(proc, "inf", "CLOSE", None)  # a plain _PortWorker's writer, or none ever sent

    assert [r.envelope.type for r in _log_records(proc)] == ["DATA", "CLOSE"]


def test_a_real_lost_message_before_close_is_caught_end_to_end(fifo_path):
    # The sender genuinely sent 1, 2 and 3, but the fifo (or the receiver's
    # own log) never got 3 before it finished for good: the receiver's
    # reader thread dies from the mismatch, the process staying alive.
    proc = _Recorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data("a", seq=1) + "\n")
            w.write(lib.encode_data("b", seq=2) + "\n")
            w.write(lib.encode_close(3) + "\n")  # claims 3, but 3 itself never arrived
            w.flush()

        reader = proc._reader_threads["inf"]
        assert _wait_until(lambda: not reader.is_alive())
        assert not proc._all_threads_alive()
        assert proc.received == ["a", "b"]
        assert [r.envelope.type for r in _log_records(proc)] == ["DATA", "DATA", "CLOSE"]
    finally:
        proc.stop_threads(timeout=2)


def test_a_halted_node_sends_no_close_so_nothing_to_check(fifo_path):
    proc = _Sender(opts={"inf": "/dev/null", "outf": fifo_path})
    proc.start_threads()
    with open(fifo_path, "r") as r:
        proc._inbound_queue.put((1, "inf", "DATA", "a", None))
        proc._inbound_queue.put(transport._STOP)
        assert _wait_until(lambda: not proc._brain_thread.is_alive())
        proc.stop_threads(timeout=2, close=False)  # a halt: no CLOSE

        lines = [line for line in r.read().splitlines() if line]

    assert [lib.decode_envelope(line).type for line in lines] == ["HELLO", "DATA"]
