import json
import os

import pytest

import debasher_runtime_lib as lib


class _Node(lib.FBPProcess):
    OUTPUT_PORTS = ["x"]

    def __init__(self, *a, **kw):
        self.state_to_capture = {"marker": "s"}
        super().__init__(*a, **kw)

    def capture_node_state(self):
        return dict(self.state_to_capture)


@pytest.fixture
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


# --- _checkpoints_dir ------------------------------------------------


def test_checkpoints_dir_requires_the_env_var(monkeypatch):
    monkeypatch.delenv("DEBASHER_PROCESS_EXECDIR", raising=False)
    proc = _Node(opts={"x": "/dev/null"})

    with pytest.raises(RuntimeError):
        proc._checkpoints_dir()


def test_checkpoints_dir_is_a_checkpoints_subdir_of_the_execdir(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    assert proc._checkpoints_dir() == os.path.join(str(execdir), "checkpoints")


# --- _save_checkpoint --------------------------------------------------


def test_save_checkpoint_writes_the_expected_json_structure(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    path = proc._save_checkpoint(3, {"marker": "s"}, {"a": [1, 2]}, 17)

    with open(path) as f:
        data = json.load(f)

    assert data == {
        "schema_version": lib.FBPProcess.CHECKPOINT_SCHEMA_VERSION,
        "epoch": 3,
        "processed_upto": 17,
        "node_state": {"marker": "s"},
        "channel_state": {"a": [1, 2]},
    }


def test_save_checkpoint_leaves_no_temp_file_behind(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    proc._save_checkpoint(0, {}, {}, 0)

    names = os.listdir(proc._checkpoints_dir())
    assert names == ["0.json"]


def test_save_checkpoint_is_named_after_the_epoch(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    path = proc._save_checkpoint(7, {}, {}, 0)
    assert os.path.basename(path) == "7.json"


def test_save_checkpoint_prunes_older_epochs_beyond_retention(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    proc.CHECKPOINT_RETENTION = 2

    for epoch in range(5):
        proc._save_checkpoint(epoch, {}, {}, 0)

    names = sorted(os.listdir(proc._checkpoints_dir()))
    assert names == ["3.json", "4.json"]


# --- _on_epoch_closed: full integration via _on_barrier/_on_interact ---


def test_on_epoch_closed_writes_a_checkpoint(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})

    checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
    assert os.path.exists(checkpoint_path)
    with open(checkpoint_path) as f:
        data = json.load(f)
    assert data["node_state"] == {"marker": "s"}


def test_on_epoch_closed_notifies_the_supervisor_port_if_set(execdir):
    class _Supervised(_Node):
        OUTPUT_PORTS = ["x", "supervisor"]
        SUPERVISOR_PORT = "supervisor"

    proc = _Supervised(opts={"x": "/dev/null", "supervisor": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})

    line = proc._outbound_queues["supervisor"].get_nowait()
    envelope = lib.decode_envelope(line)
    assert envelope.type == "INTERACT"
    assert envelope.payload["command"] == "checkpoint_saved"
    assert envelope.payload["args"]["epoch"] == 0
    assert envelope.payload["args"]["path"].endswith("0.json")


def test_on_epoch_closed_sends_nothing_extra_without_a_supervisor_port(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})

    # Only the BARRIER forwarded on "x" itself, nothing else queued.
    assert proc._outbound_queues["x"].qsize() == 1


def test_on_epoch_closed_sets_halted_event_only_when_halt_is_true(execdir):
    proc = _Node(opts={"x": "/dev/null"})
    proc._on_interact({"command": "start_snapshot", "args": {}})
    assert not proc._halted.is_set()

    proc2 = _Node(opts={"x": "/dev/null"})
    proc2._on_interact({"command": "shutdown", "args": {}})
    assert proc2._halted.is_set()
