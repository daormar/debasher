import array
import fcntl
import os
import termios
import threading
import time

import pytest

import debasher_runtime_lib as lib
import debasher_runtime_transport as transport


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


class _RecordingWorker(lib.FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]

    def __init__(self, *args, **kwargs):
        self.received = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))


class _ReaderOnly(lib.FBPProcess):
    INPUT_PORTS = ["inf"]

    def __init__(self, *args, **kwargs):
        self.received = []
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))


class _WriterOnly(transport._PortWorker):
    """
    The writer half of the transport with nothing on top of it: one output
    port and no business logic. A business node may send only from inside
    process_data, so the tests of the writer thread drive it through the
    transport's own send_data instead.
    """

    def _input_ports(self):
        return {}

    def _output_ports(self):
        return {"outf": "outf"}

    def _brain_loop(self):
        while self._inbound_queue.get() is not transport._STOP:
            pass


@pytest.fixture
def fifo_path(tmp_path):
    path = tmp_path / "test.fifo"
    os.mkfifo(path)
    return str(path)


def _unread_bytes(fifo_path):
    """How many bytes are waiting in the pipe, whoever holds it open."""
    fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        count = array.array("i", [0])
        fcntl.ioctl(fd, termios.FIONREAD, count, True)
        return count[0]
    finally:
        os.close(fd)


def _read_envelopes(fifo, count):
    """
    Reads and decodes `count` envelopes from a text stream, skipping the
    blank line every writer thread sends ahead of its HELLO.
    """
    envelopes = []
    while len(envelopes) < count:
        line = fifo.readline()
        assert line != "", "the fifo hit EOF before enough envelopes arrived"
        line = line.rstrip("\n")
        if line:
            envelopes.append(lib.decode_envelope(line))
    return envelopes


class _BrainRecorder(_ReaderOnly):
    """Keeps every item the reader threads queue, instead of processing them."""

    def __init__(self, *args, **kwargs):
        self.items = []
        super().__init__(*args, **kwargs)

    def _brain_loop(self):
        while True:
            item = self._inbound_queue.get()
            if item is lib._STOP:
                break
            self.items.append(item)


# --- reader thread -------------------------------------------------------


def test_reader_thread_dispatches_data_to_process_data(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data({"x": 1}) + "\n")
            w.flush()

        assert _wait_until(lambda: proc.received == [("inf", {"x": 1})])
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_survives_its_writer_closing_and_hears_the_next_one(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:  # a first incarnation of the writer
            w.write(lib.encode_data(1) + "\n")
        # The write end is closed now, but the reader holds one of its own,
        # so it sees no EOF and keeps listening.
        assert _wait_until(lambda: proc.received == [("inf", 1)])
        assert proc._reader_threads["inf"].is_alive()

        with open(fifo_path, "w") as w:  # the relaunched writer
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_data(2) + "\n")
        assert _wait_until(lambda: proc.received == [("inf", 1), ("inf", 2)])
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_hands_close_to_the_brain_and_stays_alive(fifo_path):
    proc = _BrainRecorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data(1) + "\n")
            w.write(lib.encode_close() + "\n")

        assert _wait_until(lambda: len(proc.items) == 2)
        # Every queued item carries its position, from 1, ahead of the port.
        assert proc.items == [(1, "inf", "DATA", 1, None), (2, "inf", "CLOSE", {}, None)]
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_what_a_writer_sends_after_its_close_never_reaches_the_node(fifo_path):
    proc = _BrainRecorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data(1) + "\n")
            w.write(lib.encode_close() + "\n")
        assert _wait_until(lambda: len(proc.items) == 2)

        # What a relaunched incarnation of the writer would say, and a corrupt line.
        with open(fifo_path, "w") as w:
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_data(2) + "\n")
            w.write(lib.encode_barrier(0) + "\n")
            w.write("this is not an envelope\n")
            w.write(lib.encode_data(3) + "\n")
        assert _wait_until(lambda: _unread_bytes(fifo_path) == 0)
        time.sleep(0.2)  # the reader may still be going through what it read

        assert proc.items == [(1, "inf", "DATA", 1, None), (2, "inf", "CLOSE", {}, None)]
        assert [r.envelope.type for r in proc._input_log.replay(0)] == ["DATA", "CLOSE"]
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


class _SlowReader(_ReaderOnly):
    def process_data(self, port_name, packet):
        time.sleep(0.05)
        super().process_data(port_name, packet)


def test_a_consumer_whose_producer_finished_keeps_saying_it_is_healthy(fifo_path):
    proc = _SlowReader(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            for n in range(10):
                w.write(lib.encode_data(n) + "\n")
            w.write(lib.encode_close() + "\n")

        # The CLOSE is in the log already, and the brain still has most of the messages to go.
        assert _wait_until(lambda: proc._input_log.next_pos == 12)
        assert len(proc.received) < 10
        assert proc._all_threads_alive()

        assert _wait_until(lambda: len(proc.received) == 10, timeout=5)
        assert proc._all_threads_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_a_new_incarnation_of_a_finished_writer_never_blocks_on_a_full_pipe(
    fifo_path, tmp_path, monkeypatch
):
    receiver = _ReaderOnly(opts={"inf": fifo_path})
    receiver.start_threads()
    try:
        monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "first"))
        first = _WriterOnly(opts={"outf": fifo_path})
        first.start_threads()
        first.send_data("outf", 1)
        first.stop_threads(timeout=2)  # says CLOSE: this incarnation has finished for good
        assert _wait_until(lambda: receiver.received == [("inf", 1)])

        # The node is relaunched after its CLOSE and sends far more than a pipe holds.
        monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "again"))
        again = _WriterOnly(opts={"outf": fifo_path})
        again.start_threads()
        try:
            for _ in range(400):
                again.send_data("outf", "x" * 1000)
            assert _wait_until(lambda: again._outbound_queues["outf"].empty(), timeout=5)
        finally:
            again.stop_threads(timeout=2)

        assert receiver.received == [("inf", 1)]
    finally:
        receiver.stop_threads(timeout=2)


def test_a_control_port_keeps_delivering_after_its_writer_says_close(fifo_path):
    class _Commanded(_BrainRecorder):
        CONTROL_PORTS = ["inf"]

    proc = _Commanded(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:  # a Supervisor that stopped
            w.write(lib.encode_close() + "\n")
        with open(fifo_path, "w") as w:  # and the one that was relaunched by hand
            w.write("\n" + lib.encode_hello() + "\n" + lib.encode_interact("start_snapshot") + "\n")

        assert _wait_until(lambda: len(proc.items) == 2)
        assert [item[2] for item in proc.items] == ["CLOSE", "INTERACT"]
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_delivers_what_follows_a_close_when_its_class_says_so(fifo_path):
    class _KeepsListening(_BrainRecorder):
        def _drops_after_close(self, tag):
            return False

    proc = _KeepsListening(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_close() + "\n")
            w.write(lib.encode_data(2) + "\n")

        assert _wait_until(lambda: len(proc.items) == 2)
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_consumes_blank_lines_and_hello_itself(fifo_path):
    proc = _BrainRecorder(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_data(1) + "\n")

        assert _wait_until(lambda: len(proc.items) == 1)
        assert proc.items == [(1, "inf", "DATA", 1, None)]
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_drops_a_fragment_left_by_a_writer_that_died_mid_message(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        big = lib.encode_data("x" * 10000)
        with open(fifo_path, "w") as w:  # dies half way through a message
            w.write(lib.encode_data("before") + "\n")
            w.write(big[: len(big) // 2])
        with open(fifo_path, "w") as w:  # its relaunched incarnation
            w.write("\n" + lib.encode_hello() + "\n")
            w.write(lib.encode_data("after") + "\n")

        assert _wait_until(lambda: proc.received == [("inf", "before"), ("inf", "after")])
        assert proc._reader_threads["inf"].is_alive()
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_dying_on_bad_input_is_caught_by_all_threads_alive(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        # The reader thread is expected to die here (uncaught
        # json.JSONDecodeError from decode_envelope) -- that's the point
        # of this test, per the base class's passive health-reporting
        # design. Pytest reports that as a
        # PytestUnhandledThreadExceptionWarning at its own next check,
        # not synchronously with the thread dying, so this doesn't try
        # to assert on the warning itself (too timing-sensitive), only
        # on the resulting, directly-observable state.
        # One unparsable line is only tolerated when a HELLO follows it
        # (the fragment of a writer that died), so this one is fatal as
        # soon as something else comes after it.
        with open(fifo_path, "w") as w:
            w.write("not a json line\n")
            w.write(lib.encode_data(1) + "\n")
            w.flush()

        reader = proc._reader_threads["inf"]
        assert _wait_until(lambda: not reader.is_alive())
        assert proc._all_threads_alive() is False
    finally:
        proc.stop_threads(timeout=2)


def test_reader_thread_dies_on_two_unparsable_lines_in_a_row(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write("garbage one\n")
            w.write("garbage two\n")
            w.flush()

        assert _wait_until(lambda: not proc._reader_threads["inf"].is_alive())
    finally:
        proc.stop_threads(timeout=2)


def test_stop_threads_wakes_a_reader_that_no_writer_ever_connected_to(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()

    started = time.monotonic()
    proc.stop_threads(timeout=2)

    assert not proc._reader_threads["inf"].is_alive()
    assert time.monotonic() - started < 1


def test_start_threads_does_not_wait_for_any_peer(fifo_path):
    proc = _RecordingWorker(opts={"inf": fifo_path, "outf": fifo_path + ".out"})
    os.mkfifo(proc.opts["outf"])

    started = time.monotonic()
    proc.start_threads()
    try:
        assert time.monotonic() - started < 1
    finally:
        proc.stop_threads(timeout=2)


# --- writer thread -------------------------------------------------------


def test_writer_thread_sends_hello_first_in_one_write_after_a_newline(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "r") as r:
            assert r.readline() == "\n"
            assert lib.decode_envelope(r.readline().rstrip("\n")) == lib.Envelope(
                type="HELLO", payload={}
            )
    finally:
        proc.stop_threads(timeout=2)


def test_writer_thread_sends_encoded_data(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "r") as r:
            proc.send_data("outf", {"y": 2})
            hello, data = _read_envelopes(r, 2)
            assert hello.type == "HELLO"
            assert data == lib.Envelope(type="DATA", payload={"y": 2})
    finally:
        proc.stop_threads(timeout=2)


def test_writer_thread_sends_close_last_when_it_is_stopped(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    with open(fifo_path, "r") as r:
        proc.send_data("outf", 1)
        proc.send_data("outf", 2)
        proc.stop_threads(timeout=2)
        # the writer closed its end when it stopped, so this read ends
        envelopes = [lib.decode_envelope(line) for line in r.read().splitlines() if line]

    assert [e.type for e in envelopes] == ["HELLO", "DATA", "DATA", "CLOSE"]


def test_a_stop_that_is_not_a_finish_sends_what_is_queued_and_no_close(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    with open(fifo_path, "r") as r:
        proc.send_data("outf", 1)
        proc.send_data("outf", 2)
        proc.stop_threads(timeout=2, close=False)
        envelopes = [lib.decode_envelope(line) for line in r.read().splitlines() if line]

    assert [e.type for e in envelopes] == ["HELLO", "DATA", "DATA"]


def test_writer_thread_survives_its_reader_going_away_and_a_new_reader_gets_the_backlog(fifo_path):
    sender = _WriterOnly(opts={"outf": fifo_path})
    receiver = _ReaderOnly(opts={"inf": fifo_path})
    receiver.start_threads()
    sender.start_threads()
    try:
        sender.send_data("outf", "m1")
        assert _wait_until(lambda: receiver.received == [("inf", "m1")])

        receiver.stop_threads(timeout=2)  # the reader is gone
        sender.send_data("outf", "m2")
        sender.send_data("outf", "m3")
        assert _wait_until(lambda: sender._outbound_queues["outf"].empty())
        # no EPIPE: the writer is still there, and what it sent waits in the pipe
        assert sender._writer_threads["outf"].is_alive()

        relaunched = _ReaderOnly(opts={"inf": fifo_path})
        relaunched.start_threads()
        try:
            assert _wait_until(lambda: relaunched.received == [("inf", "m2"), ("inf", "m3")])
        finally:
            relaunched.stop_threads(timeout=2)
    finally:
        sender.stop_threads(timeout=2)


def test_stop_threads_abandons_a_writer_stuck_on_a_full_pipe(fifo_path):
    class _Impatient(_WriterOnly):
        WRITER_STOP_TIMEOUT_SECS = 0.3

    proc = _Impatient(opts={"outf": fifo_path})
    proc.start_threads()
    for _ in range(200):
        proc.send_data("outf", "x" * 1000)  # far more than a pipe holds, with nobody reading
    writer = proc._writer_threads["outf"]
    time.sleep(0.2)  # long enough for it to fill the pipe and block

    started = time.monotonic()
    proc.stop_threads()

    assert time.monotonic() - started < 2
    assert writer.is_alive()  # abandoned, not joined
    assert writer.daemon  # so it can never keep the process alive

    # Clean up: drain the fifo so the abandoned thread can finish.
    fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        deadline = time.monotonic() + 5
        while writer.is_alive() and time.monotonic() < deadline:
            try:
                os.read(fd, 65536)
            except BlockingIOError:
                time.sleep(0.01)
    finally:
        os.close(fd)
    writer.join(timeout=2)
    proc._close_finished_fifos()


# --- brain thread / stop_threads -----------------------------------------


def test_all_threads_alive_is_true_with_no_declared_ports():
    proc = lib.FBPProcess(opts={})
    assert proc._all_threads_alive() is True


# --- heartbeat thread sends to SUPERVISOR_PORT, if set -------------------


class _Supervised(lib.FBPProcess):
    OUTPUT_PORTS = ["out"]
    SUPERVISOR_PORT = "out"
    HEARTBEAT_INTERVAL_SECONDS = 0.05


def test_heartbeat_thread_sends_to_supervisor_port_when_healthy(fifo_path):
    proc = _Supervised(opts={"out": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "r") as r:
            hello, heartbeat = _read_envelopes(r, 2)
            assert hello.type == "HELLO"
            assert heartbeat == lib.Envelope(
                type="INTERACT", payload={"command": "heartbeat", "args": {}}
            )
    finally:
        proc.stop_threads(timeout=2)


def test_heartbeat_thread_sends_nothing_without_a_supervisor_port(fifo_path):
    class _Unsupervised(lib.FBPProcess):
        OUTPUT_PORTS = ["out"]
        HEARTBEAT_INTERVAL_SECONDS = 0.05

    proc = _Unsupervised(opts={"out": fifo_path})
    proc.start_threads()

    fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        time.sleep(0.3)  # several heartbeat intervals
        # nothing but the writer's own HELLO ever went through the fifo
        assert os.read(fd, 65536) == ("\n" + lib.encode_hello() + "\n").encode()
    finally:
        os.close(fd)
        proc.stop_threads(timeout=2)


def test_heartbeat_thread_stops_sending_once_a_thread_has_died():
    # Pure Python-level check of the health gate itself, with no real
    # FIFOs involved (real FIFO/writer-thread timing is exercised
    # separately, by the two tests above): run only the heartbeat loop
    # directly, with _all_threads_alive() forced False, and confirm
    # nothing gets enqueued for the writer thread to ever send.
    proc = _Supervised(opts={"out": "/dev/null"})
    proc._all_threads_alive = lambda: False

    thread = threading.Thread(target=proc._heartbeat_loop, name="heartbeat")
    thread.start()
    time.sleep(0.2)
    proc._heartbeat_stop.set()
    thread.join(timeout=2)

    assert proc._outbound_queues["out"].empty()


def test_stop_threads_joins_everything_cleanly(fifo_path):
    proc = _RecordingWorker(opts={"inf": fifo_path, "outf": fifo_path + ".out"})
    os.mkfifo(proc.opts["outf"])

    # Neither fifo has a peer here, and none is needed: every port holds
    # both ends of its own fifo.
    proc.start_threads()
    proc.stop_threads(timeout=2)

    assert not proc._reader_threads["inf"].is_alive()
    assert not proc._writer_threads["outf"].is_alive()
    assert not proc._brain_thread.is_alive()
    assert not proc._heartbeat_thread.is_alive()
    # every descriptor was closed once the thread using it was gone
    assert proc._reader_fds == {}
    assert proc._writer_fds == {}


# --- full round trip: two processes talking over a real FIFO -------------


def test_two_processes_talk_over_a_real_fifo(fifo_path):
    sender = _WriterOnly(opts={"outf": fifo_path})
    receiver = _ReaderOnly(opts={"inf": fifo_path})

    receiver.start_threads()
    sender.start_threads()
    try:
        sender.send_data("outf", "hello")
        assert _wait_until(lambda: receiver.received == [("inf", "hello")])
    finally:
        sender.stop_threads(timeout=2)
        receiver.stop_threads(timeout=2)


# --- _on_barrier / _on_interact are still stubs in this slice ------------


def test_on_barrier_is_not_implemented_yet():
    proc = lib.FBPProcess(opts={})
    with pytest.raises(NotImplementedError):
        proc._on_barrier("some_port", {"epoch": 1, "halt": False})


def test_on_interact_is_not_implemented_yet():
    proc = lib.FBPProcess(opts={})
    with pytest.raises(NotImplementedError):
        proc._on_interact({"command": "start_snapshot", "args": {}})
