"""
Unit tests of the non-durable mode of a node (see "The non-durable mode" in
doc/design_doc_resident.md): a node of a program declared
`program_type "resident" "non-durable"` keeps no input log and no
checkpoint, takes part in no round, compares no sequence number, and bounds
what it has read and not yet processed by waiting instead of by the cap of
a log. The node learns the mode from DEBASHER_PROGRAM_DURABILITY, which the
engine exports.
"""

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
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "node"))
    return tmp_path / "node"


@pytest.fixture
def non_durable(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROGRAM_DURABILITY", transport.DURABILITY_NON_DURABLE)


@pytest.fixture(autouse=True)
def _node_log(caplog):
    """The node logger does not propagate: this hands what the nodes of
    these tests log to caplog."""
    import logging

    loggers = [logging.getLogger(name) for name in ("_Fanin", "Small")]
    for logger in loggers:
        logger.addHandler(caplog.handler)
    yield
    for logger in loggers:
        logger.removeHandler(caplog.handler)


class _Fanin(lib.FBPProcess):
    """Keeps what it processes with the position of each item; its two hooks
    of the state are not written, as a node of a non-durable program need
    not write them."""

    INPUT_PORTS = ["a", "b"]
    OUTPUT_PORTS = ["outf"]

    def __init__(self, *args, **kwargs):
        self.seen = []
        self.positions = []
        self.initialized = 0
        super().__init__(*args, **kwargs)

    def process_data(self, port_name, packet):
        self.seen.append((port_name, packet))
        self.positions.append(self._current_pos)

    def initialize_runtime(self):
        self.initialized += 1


def _opts(tmp_path, ports=("a", "b", "outf")):
    opts = {}
    for port in ports:
        path = str(tmp_path / f"{port}.fifo")
        if not os.path.exists(path):
            os.mkfifo(path)
        opts[port] = path
    return opts


def _arrive(proc, port, envelope_type, payload, seq=None):
    """Delivers one envelope the way a reader thread does."""
    if envelope_type == lib.TYPE_DATA:
        line = lib.encode_data(payload, seq=seq)
    else:
        line = json.dumps({"type": envelope_type, "payload": payload})
    proc._on_arrival(port, lib.decode_envelope(line), line)


def _drain(proc):
    """Lets the brain thread process everything queued so far, then ends it."""
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


# --- the mode comes from the engine ------------------------------------------


def test_a_node_is_durable_unless_the_engine_says_otherwise(monkeypatch):
    monkeypatch.delenv("DEBASHER_PROGRAM_DURABILITY", raising=False)
    assert _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})._durable is True
    monkeypatch.setenv("DEBASHER_PROGRAM_DURABILITY", "")
    assert _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})._durable is True
    monkeypatch.setenv("DEBASHER_PROGRAM_DURABILITY", transport.DURABILITY_NON_DURABLE)
    assert _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})._durable is False


def test_a_durability_that_is_neither_mode_is_refused(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROGRAM_DURABILITY", "light")
    with pytest.raises(ValueError, match="light"):
        _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})


def test_the_inbound_queue_bound_is_a_computational_specification(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; inbound_queue_max_mb=2")
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    assert proc.INBOUND_QUEUE_MAX_BYTES == 2 * 1024 * 1024


# --- no input log, no checkpoint, no replay ------------------------------------


def test_what_arrives_is_numbered_and_processed_in_order_with_no_log_on_disk(non_durable, execdir):
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    _arrive(proc, "a", lib.TYPE_DATA, 1)
    _arrive(proc, "b", lib.TYPE_DATA, 2)
    _arrive(proc, "a", lib.TYPE_DATA, 3)
    _drain(proc)

    assert proc.seen == [("a", 1), ("b", 2), ("a", 3)]
    assert proc.positions == [1, 2, 3]
    assert proc._input_log is None
    assert not (execdir / "log").exists()


def test_a_relaunched_node_starts_afresh_over_the_checkpoint_and_log_it_finds(non_durable, execdir, tmp_path):
    # What a durable run would have left: a checkpoint and a log with a
    # record after its capture. A non-durable node reads neither
    (execdir / "checkpoints").mkdir(parents=True)
    (execdir / "checkpoints" / "3.json").write_text(
        json.dumps(
            {
                "schema_version": lib.FBPProcess.CHECKPOINT_SCHEMA_VERSION,
                "epoch": 3,
                "capture_pos": 1,
                "closed_ports": [],
                "out_seq": {"outf": 9},
                "last_seq": {},
                "out_backlog": {},
                "node_state": {"seen": [["a", 1]]},
                "channel_state": {},
            }
        )
    )
    (execdir / "log").mkdir()
    (execdir / "log" / "1.log").write_text(
        '{"pos": 1, "port": "a", "env": ' + lib.encode_data(1) + "}\n"
        '{"pos": 2, "port": "b", "env": ' + lib.encode_data(2) + "}\n"
    )

    proc = _Fanin(opts=_opts(tmp_path))
    proc._stop_requested.set()
    proc.run()

    assert proc.seen == []
    assert proc.initialized == 1
    assert proc._out_seq == {}
    assert proc._last_epoch == -1
    assert proc._input_log is None
    assert list((execdir / "checkpoints").iterdir()) == [execdir / "checkpoints" / "3.json"]


def test_the_threads_start_without_opening_a_log(non_durable, execdir, tmp_path):
    proc = _Fanin(opts=_opts(tmp_path))
    proc.start_threads()
    try:
        assert proc._input_log is None
        assert not (execdir / "log").exists()
        assert (execdir / "control_ports").exists()
    finally:
        proc.stop_threads(timeout=5)


# --- no rounds ------------------------------------------------------------------


def test_a_trigger_opens_no_round_and_writes_nothing(non_durable, execdir, caplog):
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    for command in ("start_snapshot", "shutdown"):
        proc._on_interact({"command": command, "args": {"epoch": 7}})

    assert proc._round is None
    assert not proc._halted.is_set()
    assert proc._outbound_queues["outf"].empty()
    assert not (execdir / "checkpoints").exists()
    assert not (execdir / "halted").exists()
    assert "no rounds" in caplog.text


def test_a_marker_that_arrives_is_ignored_and_not_forwarded(non_durable, execdir, caplog):
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    _arrive(proc, "a", lib.TYPE_BARRIER, {"epoch": 7, "halt": True, "last_seq": 50})
    _arrive(proc, "a", lib.TYPE_DATA, "after")
    _drain(proc)

    assert proc._round is None
    assert proc._outbound_queues["outf"].empty()
    assert proc.seen == [("a", "after")]
    assert not (execdir / "checkpoints").exists()
    assert "no rounds" in caplog.text


# --- no sequence numbers ----------------------------------------------------------


def test_the_sequence_numbers_are_neither_compared_nor_required_to_be_consecutive(non_durable):
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    # The end of the numbering of a writer that died, then the start of the
    # numbering of its new incarnation, as a held fifo hands them over
    _arrive(proc, "a", lib.TYPE_DATA, "x57", seq=57)
    _arrive(proc, "a", lib.TYPE_DATA, "x58", seq=58)
    _arrive(proc, "a", lib.TYPE_DATA, "y1", seq=1)
    _arrive(proc, "a", lib.TYPE_DATA, "y2", seq=2)
    # A jump, which a durable reader reports as a loss
    _arrive(proc, "a", lib.TYPE_DATA, "y9", seq=9)
    # A marker and a CLOSE that claim more than arrived
    _arrive(proc, "a", lib.TYPE_BARRIER, {"epoch": 1, "halt": False, "last_seq": 40})
    _arrive(proc, "b", lib.TYPE_CLOSE, {"last_seq": 40})
    _drain(proc)

    assert [packet for _, packet in proc.seen] == ["x57", "x58", "y1", "y2", "y9"]
    assert proc._closed_ports == {"b"}


def test_the_writer_still_numbers_what_it_sends(non_durable):
    proc = _Fanin(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    proc._handler_thread = threading.get_ident()
    proc.send_data("outf", "one")
    proc.send_data("outf", "two")
    lines = [proc._outbound_queues["outf"].get_nowait() for _ in range(2)]
    assert [lib.decode_envelope(line).seq for line in lines] == [1, 2]


# --- the bound of the inbound queue --------------------------------------------------


def test_a_reader_waits_while_the_inbound_queue_is_over_its_bound(non_durable, caplog):
    class Small(_Fanin):
        INBOUND_QUEUE_MAX_BYTES = 40

    proc = Small(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    _arrive(proc, "a", lib.TYPE_DATA, "x" * 40)
    assert proc._inbound_bytes >= 40

    arrived = threading.Event()
    reader = threading.Thread(target=lambda: (_arrive(proc, "b", lib.TYPE_DATA, "y"), arrived.set()))
    reader.start()
    try:
        # The second block waits for the brain thread
        assert not arrived.wait(0.5)
        assert "waiting for the brain thread" in caplog.text

        _drain(proc)
        assert arrived.wait(5)
    finally:
        # A reader left waiting would keep the test process alive
        proc._stopping.set()
        reader.join(5)
    assert proc.seen == [("a", "x" * 40)]
    _drain(proc)
    assert proc.seen[1] == ("b", "y")
    assert proc._inbound_bytes == 0


def test_a_durable_node_never_waits_on_the_bound(monkeypatch):
    monkeypatch.delenv("DEBASHER_PROGRAM_DURABILITY", raising=False)

    class Small(_Fanin):
        INBOUND_QUEUE_MAX_BYTES = 1

        def capture_node_state(self):
            return {}

        def restore_node_state(self, node_state):
            pass

    proc = Small(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    proc._open_input_log(0)
    _arrive(proc, "a", lib.TYPE_DATA, "x" * 40)
    _arrive(proc, "b", lib.TYPE_DATA, "y" * 40)
    assert proc._inbound_bytes == 0
    _drain(proc)
    assert len(proc.seen) == 2


def test_a_stop_ends_the_wait_of_a_reader(non_durable):
    class Small(_Fanin):
        INBOUND_QUEUE_MAX_BYTES = 10

    proc = Small(opts={"a": "/dev/null", "b": "/dev/null", "outf": "/dev/null"})
    _arrive(proc, "a", lib.TYPE_DATA, "x" * 20)
    reader = threading.Thread(target=lambda: _arrive(proc, "b", lib.TYPE_DATA, "y"))
    reader.start()
    try:
        assert not _wait_until(lambda: not reader.is_alive(), timeout=0.5)
    finally:
        proc._stopping.set()
        reader.join(5)
    assert not reader.is_alive()


# --- what the node reports ------------------------------------------------------------


def test_the_node_info_file_says_the_mode(non_durable, execdir, tmp_path):
    proc = _Fanin(opts=_opts(tmp_path))
    proc.start_threads()
    try:
        with open(execdir / "node_info") as f:
            info = json.load(f)
    finally:
        proc.stop_threads(timeout=5)
    assert info["durability"] == "non-durable"
    assert info["limits"]["inbound_queue_max_bytes"] == lib.FBPProcess.INBOUND_QUEUE_MAX_BYTES
