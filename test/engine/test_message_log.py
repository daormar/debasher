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
    INPUT_PORTS = ["inf"]

    def __init__(self, *a, **kw):
        self.received = []
        super().__init__(*a, **kw)

    def capture_state(self):
        return {}

    def restore_state(self, state):
        pass

    def process_data(self, port_name, packet):
        self.received.append((port_name, packet))


@pytest.fixture
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    return tmp_path


# --- _log_dir / _log_segment_path ---------------------------------------


def test_log_dir_is_a_log_subdir_per_port(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    assert proc._log_dir("inf") == os.path.join(str(execdir), "log", "inf")


def test_log_segment_path_is_named_after_the_epoch(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    assert proc._log_segment_path("inf", 7) == os.path.join(
        str(execdir), "log", "inf", "7.log"
    )


# --- _log_received_data --------------------------------------------------


def test_log_received_data_writes_one_json_line(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc._log_received_data("inf", {"x": 1})

    path = proc._log_segment_path("inf", 0)
    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"x": 1}


def test_log_received_data_appends_across_calls_in_order(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc._log_received_data("inf", "first")
    proc._log_received_data("inf", "second")

    with open(proc._log_segment_path("inf", 0)) as f:
        payloads = [json.loads(line) for line in f]
    assert payloads == ["first", "second"]


def test_log_received_data_uses_last_epoch_plus_one(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc._last_epoch = 4
    proc._log_received_data("inf", "x")

    assert os.path.exists(proc._log_segment_path("inf", 5))
    assert not os.path.exists(proc._log_segment_path("inf", 4))


def test_log_received_data_enforces_the_size_cap(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc.MESSAGE_LOG_MAX_BYTES = 10
    proc._log_received_data("inf", "x")

    with pytest.raises(RuntimeError):
        proc._log_received_data("inf", "y" * 100)


# --- _prune_message_log_epoch / integration via _save_checkpoint --------


def test_prune_message_log_epoch_removes_the_segment_for_every_input_port(execdir):
    class _TwoPorts(_Node):
        INPUT_PORTS = ["a", "b"]

    proc = _TwoPorts(opts={"a": "/dev/null", "b": "/dev/null"})
    proc._log_received_data("a", "x")
    proc._log_received_data("b", "y")

    proc._prune_message_log_epoch(0)

    assert not os.path.exists(proc._log_segment_path("a", 0))
    assert not os.path.exists(proc._log_segment_path("b", 0))


def test_prune_message_log_epoch_ignores_a_port_with_no_segment(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    # No log ever written for epoch 3: must not raise.
    proc._prune_message_log_epoch(3)


def test_save_checkpoint_prunes_log_segments_for_dropped_epochs(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc.CHECKPOINT_RETENTION = 2

    for epoch in range(4):
        proc._last_epoch = epoch - 1
        proc._log_received_data("inf", f"epoch-{epoch}")
        proc._save_checkpoint(epoch, {}, {}, 0)

    remaining = sorted(os.listdir(proc._log_dir("inf")))
    assert remaining == ["2.log", "3.log"]


# --- _drain_message_log ---------------------------------------------------


def test_drain_message_log_replays_only_epochs_after_the_checkpoint(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc._last_epoch = -1
    proc._log_received_data("inf", "epoch-0-msg")
    proc._last_epoch = 0
    proc._log_received_data("inf", "epoch-1-msg")

    proc._drain_message_log(checkpoint_epoch=0)

    assert proc.received == [("inf", "epoch-1-msg")]


def test_drain_message_log_replays_in_order_across_multiple_epochs(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    for epoch in range(3):
        proc._last_epoch = epoch - 1
        proc._log_received_data("inf", f"m{epoch}")

    proc._drain_message_log(checkpoint_epoch=-1)

    assert proc.received == [("inf", "m0"), ("inf", "m1"), ("inf", "m2")]


def test_drain_message_log_does_nothing_when_the_port_has_no_log_dir(execdir):
    proc = _Node(opts={"inf": "/dev/null"})
    proc._drain_message_log(checkpoint_epoch=-1)
    assert proc.received == []


# --- integration: real reader+brain threads log at the right epoch -----


def test_reader_and_brain_threads_log_the_payload_actually_delivered(execdir, tmp_path):
    fifo_path = str(tmp_path / "in.fifo")
    os.mkfifo(fifo_path)
    proc = _Node(opts={"inf": fifo_path})
    proc.start_threads()

    with open(fifo_path, "w") as f:
        f.write(lib.encode_data({"v": 42}) + "\n")
        f.flush()

    assert _wait_until(lambda: proc.received == [("inf", {"v": 42})])

    with open(proc._log_segment_path("inf", 0)) as f:
        assert json.loads(f.readline()) == {"v": 42}

    proc.stop_threads()
    os.remove(fifo_path)


def test_message_arriving_after_a_checkpoint_is_logged_under_the_next_epoch(execdir, tmp_path):
    # Regression test for a real bug found only by a real end-to-end
    # debasher_exec smoke test, not by reasoning or by the unit tests
    # above: logging from the *reader* thread using self._last_epoch
    # raced against the *brain* thread actually advancing it when a
    # checkpoint closed, so a message that arrived (and was processed)
    # right after a checkpoint could still be mislabeled with the old
    # epoch -- silently dropping it from replay after a real crash,
    # since drain only replays epochs after the checkpoint's own. The
    # fix moved logging onto the brain thread itself, right before
    # process_data() runs, using the same self._last_epoch the brain
    # thread alone ever advances -- race-free by construction.
    class _Checkpointing(_Node):
        def initialize_runtime(self):
            pass

        def process_data(self, port_name, packet):
            super().process_data(port_name, packet)
            if packet == "checkpoint":
                epoch = self._last_epoch + 1
                self._save_checkpoint(epoch, {}, {}, 0)
                self._last_epoch = epoch

    fifo_path = str(tmp_path / "in.fifo")
    os.mkfifo(fifo_path)
    proc = _Checkpointing(opts={"inf": fifo_path})
    proc.start_threads()

    with open(fifo_path, "w") as f:
        for payload in ["m1", "checkpoint", "m2"]:
            f.write(lib.encode_data(payload) + "\n")
            f.flush()

    assert _wait_until(
        lambda: proc.received == [("inf", "m1"), ("inf", "checkpoint"), ("inf", "m2")]
    )

    with open(proc._log_segment_path("inf", 0)) as f:
        assert [json.loads(line) for line in f] == ["m1", "checkpoint"]
    with open(proc._log_segment_path("inf", 1)) as f:
        assert [json.loads(line) for line in f] == ["m2"]

    proc.stop_threads()
    os.remove(fifo_path)


# --- integration: run() drains the log before starting live threads -----


def test_run_drains_the_message_log_before_starting_threads(execdir):
    class _Recover(_Node):
        def initialize_runtime(self):
            pass

    proc = _Recover(opts={"inf": "/dev/null"})
    proc._last_epoch = -1
    proc._save_checkpoint(0, {}, {}, 0)
    # Received (and logged) after the checkpoint but before the crash --
    # exactly what a real restart needs to replay.
    proc._last_epoch = 0
    proc._log_received_data("inf", "missed-while-down")

    restarted = _Recover(opts={"inf": "/dev/null"})
    threading.Thread(target=restarted.run, daemon=True).start()

    assert _wait_until(lambda: restarted.received == [("inf", "missed-while-down")])

    restarted._halted.set()
    assert _wait_until(lambda: not restarted._brain_thread.is_alive())
