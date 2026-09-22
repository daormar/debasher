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


class _Node(lib.FBPProcess):
    def __init__(self, *a, **kw):
        self.restored_with = None
        self.initialize_runtime_calls = 0
        super().__init__(*a, **kw)

    def capture_node_state(self):
        return {"marker": "s"}

    def restore_node_state(self, node_state):
        self.restored_with = node_state

    def initialize_runtime(self):
        self.initialize_runtime_calls += 1


@pytest.fixture
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


# --- _load_latest_checkpoint --------------------------------------------


def test_load_latest_checkpoint_returns_none_when_no_checkpoints_dir_exists(execdir):
    proc = _Node(opts={})
    assert proc._load_latest_checkpoint() is None


def test_load_latest_checkpoint_returns_none_when_the_dir_is_empty(execdir):
    proc = _Node(opts={})
    os.makedirs(proc._checkpoints_dir())
    assert proc._load_latest_checkpoint() is None


def test_load_latest_checkpoint_returns_the_highest_epoch(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(0, {"marker": "old"}, {}, 0, [], {}, {})
    proc._save_checkpoint(1, {"marker": "new"}, {}, 0, [], {}, {})

    epoch, node_state, capture_pos, closed_ports, out_seq, last_seq = proc._load_latest_checkpoint()
    assert epoch == 1
    assert node_state == {"marker": "new"}


def test_load_latest_checkpoint_rejects_a_schema_version_mismatch(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(0, {}, {}, 0, [], {}, {})
    checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
    with open(checkpoint_path) as f:
        data = json.load(f)
    data["schema_version"] = 999
    with open(checkpoint_path, "w") as f:
        json.dump(data, f)

    with pytest.raises(ValueError):
        proc._load_latest_checkpoint()


def test_load_latest_checkpoint_refuses_a_checkpoint_without_its_closed_ports(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(0, {}, {}, 0, [], {}, {})
    checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
    with open(checkpoint_path) as f:
        data = json.load(f)
    del data["closed_ports"]
    with open(checkpoint_path, "w") as f:
        json.dump(data, f)

    with pytest.raises(KeyError, match="closed_ports"):
        proc._load_latest_checkpoint()


def test_load_latest_checkpoint_refuses_a_checkpoint_without_its_out_seq(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(0, {}, {}, 0, [], {}, {})
    checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
    with open(checkpoint_path) as f:
        data = json.load(f)
    del data["out_seq"]
    with open(checkpoint_path, "w") as f:
        json.dump(data, f)

    with pytest.raises(KeyError, match="out_seq"):
        proc._load_latest_checkpoint()


def test_load_latest_checkpoint_refuses_a_checkpoint_without_its_last_seq(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(0, {}, {}, 0, [], {}, {})
    checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
    with open(checkpoint_path) as f:
        data = json.load(f)
    del data["last_seq"]
    with open(checkpoint_path, "w") as f:
        json.dump(data, f)

    with pytest.raises(KeyError, match="last_seq"):
        proc._load_latest_checkpoint()


# --- run(): the full startup sequence ------------------------------------


def test_run_skips_restore_state_and_starts_with_defaults_when_no_checkpoint(execdir):
    proc = _Node(opts={})
    threading.Thread(target=proc.run, daemon=True).start()

    assert _wait_until(lambda: proc.initialize_runtime_calls == 1)
    assert proc.restored_with is None
    assert proc._last_epoch == -1

    proc._halted.set()
    assert _wait_until(lambda: not proc._brain_thread.is_alive())


def test_run_restores_state_and_seeds_last_epoch_when_a_checkpoint_exists(execdir):
    proc = _Node(opts={})
    proc._save_checkpoint(4, {"marker": "restored"}, {}, 0, [], {"outf": 3}, {"inf": 2})

    # A second instance is what actually "restarts": the first one
    # above only exists here to seed the checkpoint file on disk.
    restarted = _Node(opts={})
    threading.Thread(target=restarted.run, daemon=True).start()

    assert _wait_until(lambda: restarted.initialize_runtime_calls == 1)
    assert restarted.restored_with == {"marker": "restored"}
    assert restarted._last_epoch == 4
    # Restored before initialize_runtime() is even called, so that a replay
    # numbers what it sends exactly as the crashed incarnation had (G5).
    assert restarted._out_seq == {"outf": 3}
    # Both the brain's own view (G5) and the reader threads' live dedup
    # counter start from the same restored value; with nothing left to
    # replay here, they stay equal.
    assert restarted._last_seq == {"inf": 2}
    assert restarted._accepted_seq == {"inf": 2}

    restarted._halted.set()
    assert _wait_until(lambda: not restarted._brain_thread.is_alive())


def test_run_stops_every_thread_once_halted_is_set(execdir):
    proc = _Node(opts={})
    run_thread = threading.Thread(target=proc.run, daemon=True)
    run_thread.start()

    assert _wait_until(lambda: proc._brain_thread is not None and proc._brain_thread.is_alive())

    # Simulate an epoch closing with halt=True, as _on_epoch_closed would
    # do for real -- this runs on the *test* thread, not run()'s own
    # thread, deliberately, exactly like an external INTERACT shutdown
    # would arrive from outside whatever thread is blocked in run().
    proc._on_interact({"command": "shutdown", "args": {}})

    assert run_thread.join(timeout=2) is None
    assert not run_thread.is_alive()
    assert not proc._brain_thread.is_alive()
    assert not proc._heartbeat_thread.is_alive()


class _Relay(_Node):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]

    def process_data(self, port_name, packet):
        self.send_data("outf", packet)


def test_an_ordered_halt_says_nothing_after_the_marker(execdir):
    # A halt is not the end of a node, which is resumed later: what it leaves
    # on its channels ends with the round's marker, so that a node downstream
    # never takes it for one that finished for good.
    in_fifo = execdir / "in.fifo"
    out_fifo = execdir / "out.fifo"
    os.mkfifo(in_fifo)
    os.mkfifo(out_fifo)
    # A read end held here keeps what the node wrote in the pipe once it is gone.
    rfd = os.open(out_fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        proc = _Relay(opts={"inf": str(in_fifo), "outf": str(out_fifo)})
        run_thread = threading.Thread(target=proc.run, daemon=True)
        run_thread.start()
        assert _wait_until(lambda: proc._brain_thread is not None and proc._brain_thread.is_alive())

        # A writer outside the node sends a message and then the marker of a halt.
        wfd = os.open(in_fifo, os.O_WRONLY)
        try:
            os.write(wfd, (lib.encode_data(1) + "\n").encode())
            os.write(wfd, (lib.encode_barrier(0, halt=True) + "\n").encode())
        finally:
            os.close(wfd)
        run_thread.join(timeout=5)
        assert not run_thread.is_alive()

        sent = os.read(rfd, 1 << 16).decode().split("\n")
    finally:
        os.close(rfd)

    assert [lib.decode_envelope(line).type for line in sent if line] == ["HELLO", "DATA", "BARRIER"]
