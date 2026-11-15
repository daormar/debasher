import json
import os
import threading
import time

import pytest

import debasher_runtime_lib as lib
import debasher_runtime_transport as transport
from debasher_runtime_inputlog import LogCapReached


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


class _Relay(lib.FBPProcess):
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


_OPTS = {"inf": "/dev/null", "outf": "/dev/null"}


def _run_brain(proc, items):
    """items: a list of (port, payload). Runs the brain loop, on a thread of
    its own, over them (fed as if a reader thread had queued them, bypassing
    the input log since these tests are not about it), until it is done."""
    for pos, (port, payload) in enumerate(items, start=1):
        proc._inbound_queue.put((pos, port, "DATA", payload, None))
    proc._inbound_queue.put(transport._STOP)
    brain = threading.Thread(target=proc._brain_loop)
    brain.start()
    brain.join(timeout=5)
    assert not brain.is_alive()


def test_send_data_adds_to_the_backlog_before_anything_can_write_it():
    proc = _Relay(opts=_OPTS)
    _run_brain(proc, [("inf", "a")])

    assert proc._unwritten == {"outf": [(1, lib.encode_data("a", seq=1))]}


def test_a_written_line_leaves_the_backlog(fifo_path):
    proc = _Relay(opts={"inf": "/dev/null", "outf": fifo_path})
    rfd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        proc.start_threads()
        try:
            proc._inbound_queue.put((1, "inf", "DATA", "a", None))

            assert _wait_until(lambda: proc._unwritten.get("outf") == [])
        finally:
            proc.stop_threads(timeout=2)
    finally:
        os.close(rfd)


def test_the_checkpoint_carries_only_what_is_still_unwritten_at_the_capture(fifo_path):
    # A neighbor slow enough that the pipe fills: some of what send_data
    # numbers is confirmed written, the rest stays in the backlog when the
    # round captures. Only the writer thread runs in the background here;
    # process_data itself is called straight from this thread (as
    # _replay_input_log already does), so only one thread ever touches the
    # round's own state, exactly as the real brain thread would.
    proc = _Relay(opts={"inf": "/dev/null", "outf": fifo_path})
    proc._open_fifos()
    writer = threading.Thread(target=proc._writer_loop, args=("outf", "outf"), daemon=True)
    writer.start()
    try:
        # Nobody drains the fifo, so it fills (64 KiB) and the writer thread
        # blocks: keep sending 8 KB messages until some are confirmed
        # written and some are not, rather than guessing how many it takes.
        big = "x" * 8000
        i = 0

        def some_written_and_some_not():
            unwritten = proc._unwritten.get("outf", [])
            return bool(unwritten) and proc._out_seq.get("outf", 0) > len(unwritten)

        while not some_written_and_some_not():
            i += 1
            assert i < 200, "never saw both a written and an unwritten line"
            proc._run_process_data("inf", {"i": i, "pad": big})
            time.sleep(0.01)

        proc._current_pos = i + 1  # the position a following INTERACT would take
        proc._open_round(0, False, arrived_port=None)
        captured = proc._round.capture.out_backlog
        assert captured["outf"]
        assert len(captured["outf"]) < proc._out_seq["outf"]

        proc._round.pending = set()  # "inf" is /dev/null, no marker will ever arrive
        proc._close_round()

        checkpoint_path = os.path.join(proc._checkpoints_dir(), "0.json")
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        assert checkpoint["out_backlog"] == captured
    finally:
        # Drain the pipe so the writer thread can finish.
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    if not os.read(fd, 1 << 16):
                        break
                except BlockingIOError:
                    time.sleep(0.01)
        finally:
            os.close(fd)
        proc._outbound_queues["outf"].put(transport._STOP)
        writer.join(timeout=2)


def test_a_capture_is_a_copy_not_a_live_view_of_the_backlog():
    proc = _Relay(opts=_OPTS)
    _run_brain(proc, [("inf", "a")])
    assert proc._unwritten["outf"] == [(1, lib.encode_data("a", seq=1))]

    proc._on_interact({"command": "start_snapshot", "args": {}})  # "inf" left pending
    assert proc._round.capture.out_backlog == {"outf": [{"seq": 1, "payload": "a"}]}

    # The line is confirmed written while the round stays open: the live
    # backlog empties, but the round's own copy, taken earlier, must not.
    proc._on_written("outf", lib.encode_data("a", seq=1))
    assert proc._unwritten["outf"] == []
    assert proc._round.capture.out_backlog == {"outf": [{"seq": 1, "payload": "a"}]}


def test_over_the_cap_the_checkpoint_is_not_written(caplog):
    class _SmallCap(_Relay):
        OUT_BACKLOG_MAX_BYTES = 10

    proc = _SmallCap(opts=_OPTS)
    _run_brain(proc, [("inf", "a longer payload than the cap allows")])

    proc.log.addHandler(caplog.handler)
    try:
        with caplog.at_level("WARNING", logger=proc.log.name):
            proc._on_interact({"command": "start_snapshot", "args": {}})
            proc._close_round()
    finally:
        proc.log.removeHandler(caplog.handler)

    assert not os.path.exists(os.path.join(proc._checkpoints_dir(), "0.json"))
    assert "OUT_BACKLOG_MAX_BYTES" in caplog.text


def test_a_halt_over_the_cap_still_marks_the_node_halted():
    # A skipped checkpoint must not also skip marking this node halted: it
    # is still discoverable as such from outside, and resumed later from
    # whatever its last real checkpoint was.
    class _SmallCap(_Relay):
        OUT_BACKLOG_MAX_BYTES = 10

    proc = _SmallCap(opts=_OPTS)
    _run_brain(proc, [("inf", "a longer payload than the cap allows")])

    proc._on_interact({"command": "shutdown", "args": {}})
    proc._close_round()

    assert not os.path.exists(os.path.join(proc._checkpoints_dir(), "0.json"))
    assert proc._halted.is_set()
    with open(proc._halted_marker_path()) as f:
        assert f.read() == "0"


def test_load_latest_checkpoint_returns_out_backlog():
    proc = _Relay(opts=_OPTS)
    proc._save_checkpoint(
        lib._Checkpoint(
            epoch=0,
            node_state={},
            out_backlog={"outf": [{"seq": 1, "payload": "a"}]},
        )
    )

    out_backlog = proc._load_latest_checkpoint().out_backlog
    assert out_backlog == {"outf": [{"seq": 1, "payload": "a"}]}


# --- the limit on the memory the backlog takes -------------------------------


class _SmallFailCap(_Relay):
    # Room for two lines of the payloads below, not three.
    OUT_BACKLOG_FAIL_BYTES = 2 * len(lib.encode_data("p" * 50, seq=1)) + 5


def test_send_data_raises_past_the_fail_cap_with_nothing_sent_or_numbered():
    proc = _SmallFailCap(opts=_OPTS)
    proc._handler_thread = threading.get_ident()
    proc.send_data("outf", "p" * 50)
    proc.send_data("outf", "p" * 50)

    with pytest.raises(RuntimeError, match="OUT_BACKLOG_FAIL_BYTES.*'outf'.*not reading"):
        proc.send_data("outf", "p" * 50)

    assert proc._out_seq["outf"] == 2
    assert [seq for seq, _ in proc._unwritten["outf"]] == [1, 2]
    assert proc._outbound_queues["outf"].qsize() == 2


class _TwoOutputs(_SmallFailCap):
    OUTPUT_PORTS = ["p1", "p2"]


def test_the_error_past_the_fail_cap_names_the_port_that_holds_the_most():
    # The reader of p1 is not reading, so the backlog is full of p1; the
    # message that goes over the limit is one of p2.
    proc = _TwoOutputs(opts={"inf": "/dev/null", "p1": "/dev/null", "p2": "/dev/null"})
    proc._handler_thread = threading.get_ident()
    proc.send_data("p1", "p" * 50)
    proc.send_data("p1", "p" * 50)

    with pytest.raises(RuntimeError) as info:
        proc.send_data("p2", "p" * 50)

    held = proc._unwritten_port_bytes["p1"]
    assert (
        "with this message on 'p2'; the port that holds the most not yet "
        f"written is 'p1', with {held} bytes"
    ) in str(info.value)


def test_a_written_line_makes_room_under_the_fail_cap_again():
    proc = _SmallFailCap(opts=_OPTS)
    proc._handler_thread = threading.get_ident()
    proc.send_data("outf", "p" * 50)
    proc.send_data("outf", "p" * 50)

    proc._on_written("outf", lib.encode_data("p" * 50, seq=1))
    proc.send_data("outf", "p" * 50)

    assert [seq for seq, _ in proc._unwritten["outf"]] == [2, 3]
    assert proc._unwritten_bytes == sum(len(line) for _, line in proc._unwritten["outf"])


def test_a_restored_backlog_counts_against_the_fail_cap():
    proc = _SmallFailCap(opts=_OPTS)
    proc._restore_out_backlog({"outf": [{"seq": 1, "payload": "p" * 50}, {"seq": 2, "payload": "p" * 50}]})
    proc._out_seq["outf"] = 2
    proc._handler_thread = threading.get_ident()

    with pytest.raises(RuntimeError, match="OUT_BACKLOG_FAIL_BYTES"):
        proc.send_data("outf", "p" * 50)


def test_a_skipped_checkpoint_is_remembered_until_one_is_written():
    class _SmallCap(_Relay):
        OUT_BACKLOG_MAX_BYTES = 10

    proc = _SmallCap(opts=_OPTS)
    _run_brain(proc, [("inf", "a longer payload than the cap allows")])
    proc._on_interact({"command": "start_snapshot", "args": {}})
    proc._close_round()
    assert proc._checkpoints_skipped_since == 0

    # A second skipped round keeps the first epoch that was skipped.
    proc._on_interact({"command": "start_snapshot", "args": {}})
    proc._close_round()
    assert proc._checkpoints_skipped_since == 0

    # Once the line is written, the next round writes its checkpoint.
    proc._on_written("outf", lib.encode_data("a longer payload than the cap allows", seq=1))
    proc._on_interact({"command": "start_snapshot", "args": {}})
    proc._close_round()
    assert os.path.exists(os.path.join(proc._checkpoints_dir(), "2.json"))
    assert proc._checkpoints_skipped_since is None


@pytest.mark.parametrize("skipped_since", [None, 7])
def test_a_log_at_its_cap_names_the_backlog_when_checkpoints_are_being_skipped(skipped_since):
    class _SmallLog(_Relay):
        INPUT_LOG_MAX_BYTES = 200

    proc = _SmallLog(opts=_OPTS)
    proc._open_input_log(0)
    proc._checkpoints_skipped_since = skipped_since
    line = lib.encode_data("q" * 60, seq=None)
    items = [(lib.decode_envelope(line), line)] * 5

    with pytest.raises(LogCapReached) as info:
        proc._on_arrivals("inf", items)

    if skipped_since is None:
        assert "outbound backlog" not in str(info.value)
    else:
        assert "since epoch 7" in str(info.value)
        assert "OUT_BACKLOG_MAX_BYTES" in str(info.value)
    # What fitted was queued either way.
    assert proc._inbound_queue.qsize() == len(info.value.positions) > 0


# --- the replay of a relaunched node -------------------------------------


@pytest.fixture
def relay_opts(tmp_path):
    paths = {name: str(tmp_path / name) for name in ("inf", "outf")}
    for path in paths.values():
        os.mkfifo(path)
    return paths


def _log_arrivals(opts, payloads):
    node = _Relay(opts=opts)
    node._open_input_log(0)
    for payload in payloads:
        line = lib.encode_data(payload)
        node._on_arrival("inf", lib.decode_envelope(line), line)
    node._input_log.close()


class _Counting(_Relay):
    replayed = 0

    def process_data(self, port_name, packet):
        super().process_data(port_name, packet)
        self.replayed += 1


def _stays_still(value, interval=0.3):
    """Whether `value()` gives the same result before and after `interval`."""
    before = value()
    time.sleep(interval)
    return value() == before


def _start_run(node):
    outcome = {}

    def target():
        try:
            node.run()
        except Exception as exc:  # what a test looks at, in the main thread
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    return thread, outcome


def _read_data_lines(path, count):
    """The DATA envelopes of a fifo, until there are `count` of them."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    received, pending = [], b""
    try:
        deadline = time.monotonic() + 10
        while len(received) < count and time.monotonic() < deadline:
            try:
                pending += os.read(fd, 1 << 16)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            *lines, pending = pending.split(b"\n")
            envelopes = (lib.decode_envelope(line.decode()) for line in lines if line)
            received += [e for e in envelopes if e.type == lib.TYPE_DATA]
    finally:
        os.close(fd)
    return received


def test_what_was_restored_arrives_before_what_the_replay_sends_again(relay_opts):
    checkpointer = _Relay(opts=relay_opts)
    checkpointer._save_checkpoint(
        lib._Checkpoint(
            epoch=0,
            node_state={},
            out_seq={"outf": 1},
            out_backlog={"outf": [{"seq": 1, "payload": "restored"}]},
        )
    )
    _log_arrivals(relay_opts, ["replayed"])

    node = _Relay(opts=relay_opts)
    thread, outcome = _start_run(node)
    try:
        received = _read_data_lines(relay_opts["outf"], 2)
    finally:
        node._stop_requested.set()
        thread.join(timeout=5)

    assert [(e.seq, e.payload) for e in received] == [(1, "restored"), (2, "replayed")]
    assert not outcome


def test_a_replay_over_the_limit_of_the_backlog_ends_with_a_reader_that_drains(
    relay_opts, caplog
):
    class _SmallBacklog(_Counting):
        OUT_BACKLOG_FAIL_BYTES = 4096

    # More than the pipe and the backlog hold together, on any platform.
    payloads = [f"{i}:" + "p" * 1000 for i in range(200)]
    _log_arrivals(relay_opts, payloads)

    node = _SmallBacklog(opts=relay_opts)
    node.log.addHandler(caplog.handler)
    thread, outcome = _start_run(node)
    try:
        # The replay stops, waiting for room, before anything reads: the
        # warning comes at the first wait, and the count stays still.
        assert _wait_until(lambda: "waits for room in the outbound backlog" in caplog.text)
        assert _wait_until(lambda: _stays_still(lambda: node.replayed), timeout=5)
        assert node.replayed < 200

        received = _read_data_lines(relay_opts["outf"], 200)
        assert _wait_until(lambda: node._brain_thread is not None)
    finally:
        node._stop_requested.set()
        thread.join(timeout=5)
        node.log.removeHandler(caplog.handler)

    assert [e.payload for e in received] == payloads
    assert node.replayed == 200
    assert not outcome


def test_a_replay_with_no_reader_waits_and_a_stop_ends_it_with_the_error(relay_opts, caplog):
    class _SmallBacklog(_Counting):
        OUT_BACKLOG_FAIL_BYTES = 4096

    # More than the pipe and the backlog hold together, and nobody reads.
    _log_arrivals(relay_opts, ["p" * 1000] * 200)

    node = _SmallBacklog(opts=relay_opts)
    node.log.addHandler(caplog.handler)
    thread, outcome = _start_run(node)
    try:
        assert _wait_until(lambda: node.replayed >= 1)
        time.sleep(0.3)
        assert thread.is_alive() and node.replayed < 200
        assert "error" not in outcome
    finally:
        node._stop_requested.set()
        thread.join(timeout=5)
        node.log.removeHandler(caplog.handler)

    assert not thread.is_alive()
    assert "is not reading" in str(outcome["error"])
    assert caplog.text.count("waits for room in the outbound backlog") == 1


def test_a_message_larger_than_the_limit_raises_at_once_with_its_own_error():
    class _TinyFailCap(_Relay):
        OUT_BACKLOG_FAIL_BYTES = 64

    proc = _TinyFailCap(opts=_OPTS)
    proc._handler_thread = threading.get_ident()

    with pytest.raises(RuntimeError, match="larger than OUT_BACKLOG_FAIL_BYTES.*never fits"):
        proc.send_data("outf", "p" * 1000)

    assert proc._out_seq == {}
    assert proc._unwritten == {}


def test_a_message_larger_than_the_limit_raises_at_once_in_a_replay_too():
    class _TinyFailCap(_Relay):
        OUT_BACKLOG_FAIL_BYTES = 64

    proc = _TinyFailCap(opts=_OPTS)
    # A replay with a backlog that nothing drains: no writer thread runs.
    proc._replaying = True
    with proc._out_backlog_lock:
        proc._add_to_out_backlog("outf", 1, lib.encode_data("p", seq=1))
    proc._out_seq["outf"] = 1
    outcome = {}

    def send():
        proc._handler_thread = threading.get_ident()
        try:
            proc.send_data("outf", "p" * 1000)
        except RuntimeError as exc:
            outcome["error"] = exc

    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    try:
        sender.join(timeout=2)
        assert not sender.is_alive(), "send_data waited instead of raising at once"
    finally:
        proc._stop_requested.set()  # ends a wait, if send_data waited
        sender.join(timeout=2)

    assert "larger than OUT_BACKLOG_FAIL_BYTES" in str(outcome.get("error"))
    assert proc._out_seq == {"outf": 1}


def test_a_failure_while_the_threads_start_ends_run_with_no_thread_left(relay_opts):
    class _FailsLate(_Relay):
        def start_threads(self):
            super().start_threads()
            raise RuntimeError("failed while starting")

    node = _FailsLate(opts=relay_opts)
    thread, outcome = _start_run(node)
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert "failed while starting" in str(outcome["error"])
    assert not node._brain_thread.is_alive()
    assert not any(t.is_alive() for t in node._reader_threads.values())
    assert not node._heartbeat_thread.is_alive()


def test_a_first_node_info_file_that_cannot_be_written_leaves_the_node_running(relay_opts, caplog):
    class _NoInfoFile(_Relay):
        def _write_node_info(self, healthy):
            raise OSError(28, "No space left on device")

    node = _NoInfoFile(opts=relay_opts)
    node.log.addHandler(caplog.handler)
    thread, outcome = _start_run(node)
    try:
        assert _wait_until(lambda: node._brain_thread is not None and node._are_all_threads_alive())
    finally:
        node._stop_requested.set()
        thread.join(timeout=5)

    assert not outcome
    assert "cannot write the node info file" in caplog.text
