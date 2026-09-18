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


class _WriterOnly(lib.FBPProcess):
    OUTPUT_PORTS = ["outf"]


@pytest.fixture
def fifo_path(tmp_path):
    path = tmp_path / "test.fifo"
    os.mkfifo(path)
    return str(path)


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


def test_reader_thread_exits_on_fifo_eof(fifo_path):
    proc = _ReaderOnly(opts={"inf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "w") as w:
            w.write(lib.encode_data(1) + "\n")
        # the "with" block above closes the write end -> EOF for the reader
        reader = proc._reader_threads["inf"]
        assert _wait_until(lambda: not reader.is_alive())
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
        with open(fifo_path, "w") as w:
            w.write("not a json line\n")
            w.flush()

        reader = proc._reader_threads["inf"]
        assert _wait_until(lambda: not reader.is_alive())
        assert proc._all_threads_alive() is False
    finally:
        proc.stop_threads(timeout=2)


# --- writer thread -------------------------------------------------------


def test_writer_thread_sends_encoded_data(fifo_path):
    proc = _WriterOnly(opts={"outf": fifo_path})
    proc.start_threads()
    try:
        with open(fifo_path, "r") as r:
            proc.send_data("outf", {"y": 2})
            line = r.readline().rstrip("\n")
            assert lib.decode_envelope(line) == lib.Envelope(type="DATA", payload={"y": 2})
    finally:
        proc.stop_threads(timeout=2)


# --- brain thread / stop_threads -----------------------------------------


def test_all_threads_alive_is_true_with_no_declared_ports():
    proc = lib.FBPProcess(opts={})
    assert proc._all_threads_alive() is True


def test_stop_threads_joins_everything_cleanly(fifo_path):
    proc = _RecordingWorker(opts={"inf": fifo_path, "outf": fifo_path + ".out"})
    os.mkfifo(proc.opts["outf"])

    # start_threads() first: its reader/writer threads each block inside
    # open() until something opens the other end of their FIFO. Only
    # then do we open the other ends below -- opening "inf" for writing
    # before the process's own reader thread exists to pair with it
    # would deadlock the main thread right here.
    proc.start_threads()

    def _drain_writer_fifo():
        with open(proc.opts["outf"], "r"):
            pass

    reader_holder = threading.Thread(target=_drain_writer_fifo)
    reader_holder.start()

    writer_holder = open(proc.opts["inf"], "w")

    reader_holder.join(timeout=2)
    writer_holder.close()

    proc.stop_threads(timeout=2)

    assert not proc._reader_threads["inf"].is_alive()
    assert not proc._writer_threads["outf"].is_alive()
    assert not proc._brain_thread.is_alive()
    assert not proc._heartbeat_thread.is_alive()


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
