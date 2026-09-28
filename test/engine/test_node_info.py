"""
The node info file of a node (see "`debasher_inspect_resident`: what a node
keeps" in the design doc): written when the threads start, with the limits
in force, and again at every tick of the heartbeat thread, with the size of
the outbound backlog of each output port, which send_data and the writer
threads keep up to date together with the backlog.
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
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    monkeypatch.delenv("DEBASHER_PROCESS_TASK_IDX", raising=False)
    monkeypatch.delenv("DEBASHER_PROCESS_COMP_SPECS", raising=False)
    return tmp_path


class _Fork(lib.FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outa", "outb"]

    def process_data(self, port_name, packet):
        self.send_data(packet["to"], packet["text"])

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


_OPTS = {"inf": "/dev/null", "outa": "/dev/null", "outb": "/dev/null"}


@pytest.fixture
def fifo_opts(tmp_path):
    """Options whose ports are fifos, which the node holds at both ends, so
    that its reader thread waits on its fifo instead of ending at the end of
    /dev/null."""
    opts = {}
    for port in _OPTS:
        path = tmp_path / "fifos" / port
        path.parent.mkdir(exist_ok=True)
        os.mkfifo(path)
        opts[port] = str(path)
    return opts


def _read_node_info(execdir, name="node_info"):
    with open(execdir / name) as f:
        return json.load(f)


def _started(proc):
    proc.start_threads()
    return proc


def test_the_node_info_file_is_written_when_the_threads_start(execdir, fifo_opts, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; input_log_max_mb=2; out_backlog_fail_mb=3")
    before = time.time()
    proc = _started(_Fork(opts=fifo_opts))
    try:
        info = _read_node_info(execdir)
    finally:
        proc.stop_threads(timeout=2)

    assert info["runtime_class"] == "FBPProcess"
    assert before <= info["started_at"] <= info["updated_at"]
    assert info["heartbeat_interval_secs"] == lib.FBPProcess.HEARTBEAT_INTERVAL_SECONDS
    assert info["limits"] == {
        "input_log_max_bytes": 2 * 1024 * 1024,
        "out_backlog_max_bytes": lib.FBPProcess.OUT_BACKLOG_MAX_BYTES,
        "out_backlog_fail_bytes": 3 * 1024 * 1024,
        "gil_switch_interval_secs": lib.FBPProcess.GIL_SWITCH_INTERVAL_SECS,
    }
    assert info["healthy"] is True
    assert info["out_backlog_bytes"] == {}
    assert info["checkpoints_skipped_since"] is None
    assert "launcher" not in info


def test_a_task_of_an_array_writes_a_file_of_its_own(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_TASK_IDX", "2")
    proc = _started(_Fork(opts=_OPTS))
    proc.stop_threads(timeout=2)

    assert (execdir / "node_info_2").exists()
    assert not (execdir / "node_info").exists()


def test_every_heartbeat_tick_writes_it_again(execdir):
    class Quick(_Fork):
        HEARTBEAT_INTERVAL_SECONDS = 0.05

    proc = _started(Quick(opts=_OPTS))
    try:
        first = _read_node_info(execdir)
        assert _wait_until(lambda: _read_node_info(execdir)["updated_at"] > first["updated_at"])
        later = _read_node_info(execdir)
    finally:
        proc.stop_threads(timeout=2)

    assert later["started_at"] == first["started_at"]
    assert later["heartbeat_interval_secs"] == 0.05


def test_a_tick_reports_a_dead_thread(execdir, fifo_opts):
    class Quick(_Fork):
        HEARTBEAT_INTERVAL_SECONDS = 0.05

    proc = _started(Quick(opts=fifo_opts))
    try:
        assert _read_node_info(execdir)["healthy"] is True
        # The brain thread ends, as it does on an exception of process_data;
        # the process goes on.
        proc._inbound_queue.put(transport._STOP)
        assert _wait_until(lambda: _read_node_info(execdir)["healthy"] is False)
    finally:
        proc.stop_threads(timeout=2)


def _run_brain(proc, items):
    """Runs the brain loop over `items`, (port, payload) fed as if a reader
    thread had queued them, with no writer thread to take anything out of
    the outbound backlog."""
    for pos, (port, payload) in enumerate(items, start=1):
        proc._inbound_queue.put((pos, port, "DATA", payload, None))
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


def test_the_backlog_of_each_port_is_kept_with_the_backlog(execdir):
    proc = _Fork(opts=_OPTS)
    _run_brain(
        proc,
        [
            ("inf", {"to": "outa", "text": "x"}),
            ("inf", {"to": "outa", "text": "yy"}),
            ("inf", {"to": "outb", "text": "zzz"}),
        ],
    )

    lines = {tag: [line for _, line in entries] for tag, entries in proc._unwritten.items()}
    assert proc._unwritten_port_bytes == {tag: sum(map(len, ls)) for tag, ls in lines.items()}

    proc._on_written("outa", lines["outa"][0])

    assert proc._unwritten_port_bytes["outa"] == len(lines["outa"][1])
    assert proc._unwritten_bytes == len(lines["outa"][1]) + len(lines["outb"][0])

    proc._started_at = time.time()
    proc._write_node_info(True)
    assert _read_node_info(execdir)["out_backlog_bytes"] == proc._unwritten_port_bytes


def test_the_backlog_restored_from_a_checkpoint_is_counted(execdir):
    proc = _Fork(opts=_OPTS)
    proc._restore_out_backlog({"outb": [{"seq": 1, "payload": "a"}, {"seq": 2, "payload": "b"}]})

    assert proc._unwritten_port_bytes == {
        "outb": len(lib.encode_data("a", seq=1)) + len(lib.encode_data("b", seq=2))
    }


def test_a_file_that_cannot_be_written_does_not_stop_the_heartbeats(execdir, caplog):
    class Quick(_Fork):
        HEARTBEAT_INTERVAL_SECONDS = 0.05

    proc = _started(Quick(opts=_OPTS))
    proc.log.addHandler(caplog.handler)
    try:
        # The temporary file cannot be created where a directory stands.
        os.mkdir(execdir / "node_info.tmp")
        assert _wait_until(lambda: "cannot write the node info file" in caplog.text)
        assert proc._heartbeat_thread.is_alive()
    finally:
        proc.log.removeHandler(caplog.handler)
        proc.stop_threads(timeout=2)
