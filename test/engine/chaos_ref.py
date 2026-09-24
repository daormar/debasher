"""
Helpers for the real runs of debasher_chaos_ref.sh: what feeds its external
port, what paces its snapshots, what follows sink's input log, and the
criteria that sink's trace has to meet (see "Acceptance" in the design doc).
"""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from resident_run import (
    DEBASHER_STOP_RESIDENT,
    SchedOutTailer,
    launch,
    sched_out_file,
    wait_for,
    write_line,
)

PFILE = Path(__file__).resolve().parent / "debasher_chaos_ref.sh"


def launch_chaos(outdir):
    """Runs debasher_chaos_ref.sh into `outdir`."""
    launch(PFILE, outdir)


# Two shapes a G8 violation on a killed node's channel is seen to take in
# practice (see "Acceptance" in the design doc): a clean one naming
# the exact missing sequence numbers, raised when the reader notices the
# jump itself; and a "torn line" one with no numbers, raised when a freshly
# relaunched reader reattaches mid-message to a fifo whose writer never
# itself died (so no fresh HELLO is coming to excuse the fragment). Both
# stop the affected part and are detected, never silent, so both count as
# the accepted exception; only the first names a range to cross-check.
G8_GAP_RE = re.compile(
    r"gap in the sequence numbers on '(?P<channel>[^']+)': "
    r"expected \d+, got \d+, missing (?P<lo>\d+)(?: to (?P<hi>\d+))?"
)


G8_TORN_RE = re.compile(r"unparsable line on '(?P<channel>[^']+)' not followed by HELLO")


def find_g8_error(text, channel):
    """
    Returns (lo, hi) of the reported missing range if the clean, numbered
    shape naming `channel` is found; (None, None) if only the numberless
    "torn line" shape naming `channel` is found; None if neither is.
    """
    m = G8_GAP_RE.search(text)
    if m and m.group("channel") == channel:
        lo = int(m.group("lo"))
        hi = int(m.group("hi")) if m.group("hi") else lo
        return (lo, hi)
    m = G8_TORN_RE.search(text)
    if m and m.group("channel") == channel:
        return (None, None)
    return None


KILLABLE_NODES = ("fanin", "loop", "sink")


class SinkTailer(threading.Thread):
    """
    Follows sink's own input log continuously, from before anything is
    sent until told to stop, across however many segments (and however
    many incarnations of sink) it takes.

    Reading the log directory once, after the run, is not reliable once
    sink itself can be a kill target: a checkpoint sink's relaunched
    incarnation takes right after replaying the pre-crash log already
    covers everything in it, so pruning (see the Input log section)
    deletes that pre-crash segment, however high CHECKPOINT_RETENTION is
    set (retention counts this incarnation's own epochs, not history
    from before a crash it never checkpointed itself). Tailing from the
    start sidesteps this: every record is captured, in memory, well
    before any future pruning could ever remove it from disk.
    """

    def __init__(self, log_dir, poll_interval=0.02):
        super().__init__(daemon=True)
        self._log_dir = Path(log_dir)
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self.records = []
        self.error = None

    def stop_and_join(self, timeout=10):
        self._stop_event.set()
        self.join(timeout)

    def _segments(self):
        if not self._log_dir.is_dir():
            return []
        return sorted(self._log_dir.glob("*.log"), key=lambda p: int(p.stem))

    def run(self):
        current = None
        fh = None
        try:
            while True:
                should_stop = self._stop_event.is_set()
                segments = self._segments()
                if current is None and segments:
                    current = segments[0]
                    fh = open(current)

                if fh is not None:
                    while True:
                        pos = fh.tell()
                        line = fh.readline()
                        if not line:
                            break
                        if not line.endswith("\n"):
                            # A torn tail, or a line still being written:
                            # rewind and try again once more is there.
                            fh.seek(pos)
                            break
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        self.records.append(record["env"])

                    # By stem, not list position: `current` itself may
                    # already be gone from a fresh listing by now (pruned
                    # once a later checkpoint supersedes it), but the
                    # already-open handle is still perfectly readable.
                    current_pos = int(current.stem)
                    newer = [s for s in segments if int(s.stem) > current_pos]
                    if newer:
                        fh.close()
                        current = min(newer, key=lambda p: int(p.stem))
                        fh = open(current)

                if should_stop:
                    break
                time.sleep(self._poll_interval)
        except Exception as exc:  # surfaced by the test through .error
            self.error = exc
        finally:
            if fh is not None:
                fh.close()


class ExtFeeder(threading.Thread):
    """
    Feeds 1..k into ext, one write per value, from outside the program.
    Keeps a single write fd open for the whole run and retries a write
    that raises BrokenPipeError (fanin currently down) on that same fd.

    Verified empirically (not assumed) with a standalone fifo, before
    writing this: a value already buffered in ext, unread, when fanin
    dies survives for its relaunched incarnation to read, but only if
    something keeps a fd open on ext the whole time; with no fd open at
    all, even for an instant, the kernel discards it. A write attempted
    while fanin is down always raises BrokenPipeError at once (it never
    blocks and never partially writes, every payload here being far
    under PIPE_BUF), and retrying that same write on that same fd once
    fanin reopens ext succeeds and is delivered whole, so no value is
    ever lost or duplicated as long as the retry loop below keeps going
    until each one is actually accepted.

    Every value carries its own sequence number, as a source that knows
    the protocol may send it: a value that fanin takes from ext and loses
    before writing it to its input log (see the Contract's limits) is
    then a gap that fanin reports (G8), not a silent loss at the
    boundary of the program.
    """

    def __init__(self, ext_fifo, k, interval, stop_event=None, first=1):
        super().__init__(daemon=True)
        self._ext_fifo = ext_fifo
        self._k = k
        # The first value, and number, to send: above 1 only to go on
        # after a resume, where fanin has already accepted the ones before
        self._first = first
        self._interval = interval
        # Only a permanently-failed peer (a node given up on for good, not
        # just down for a relaunch) needs this: it never reopens ext
        # again, so retrying forever would hang the feeder past the point
        # where anyone is still listening. None (the default) keeps every
        # other piece's plain "retry until it is accepted" behavior.
        self._stop_event = stop_event
        self.error = None
        self.sent = 0

    def run(self):
        try:
            fd = os.open(self._ext_fifo, os.O_WRONLY)
            try:
                for i in range(self._first, self._k + 1):
                    line = (json.dumps({"type": "DATA", "seq": i, "payload": i}) + "\n").encode()
                    while True:
                        if self._stop_event is not None and self._stop_event.is_set():
                            return
                        try:
                            os.write(fd, line)
                            break
                        except BrokenPipeError:
                            time.sleep(0.05)
                    self.sent = i
                    if self._stop_event is not None and self._stop_event.wait(self._interval):
                        return
                    elif self._stop_event is None:
                        time.sleep(self._interval)
            finally:
                os.close(fd)
        except Exception as exc:  # surfaced by the test through .error
            self.error = exc


class SnapshotPacer(threading.Thread):
    """Sends start_snapshot through the manual trigger on a steady beat,
    for as long as the chaos run's main data feed lasts. sup itself is
    never a kill target, so the plain per-message open+write+close of
    write_line is safe here."""

    def __init__(self, manual_fifo, interval, stop_event):
        super().__init__(daemon=True)
        self._manual_fifo = manual_fifo
        self._interval = interval
        self._stop_event = stop_event

    def run(self):
        while not self._stop_event.wait(self._interval):
            try:
                write_line(
                    self._manual_fifo,
                    {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}},
                )
            except OSError:
                pass


def halt_and_wait_for_finished(outdir, timeout=30.0):
    """
    Ends a run with debasher_stop_resident, the graceful stop tool, for
    real: it stops the Supervisor first, halts the program through fanin's
    own control port, waits for every node's halted marker, signals every
    node (whole process group, see
    debasher_builtin_sched::_print_script_trap), and falls back to
    debasher_stop if it cannot finish within timeout. The tests use it to
    end a run cleanly enough to look at its trace afterward; the tool
    itself is checked by test_stop_resident.py.
    """
    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", str(int(timeout))],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"debasher_stop_resident failed:\n{result.stdout}\n{result.stderr}"
    assert wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=timeout)


def assert_node_state_restored(records, context=""):
    """
    G3 (and G6 across a resume): fanin's node state travels in every copy
    it sends to sink. On each port the counts that sink sees must be 1, 2,
    3... with no jump and no restart: a relaunch or a resume that did not
    restore the state as it was would start counting again, or skip.

    G4: the digest in each copy folds every message fanin processed, on
    any port, in the order it processed them, and sink sees the copies in
    that same order. Folding sink's own trace must give the digest of
    every copy: a replay that reproduced another interleaving of the ports
    would leave fanin with a digest that no longer follows from the trace.

    Both hold whether or not a message was lost before fanin processed
    it, since the state only follows what fanin processed, and sink sees
    a prefix of that when its own channel has a gap.
    """
    data = [r for r in records if r.get("type") == "DATA"]
    for port in ("ext", "loop_in"):
        counts = [r["payload"]["count"] for r in data if r["payload"]["port"] == port]
        assert counts == list(range(1, len(counts) + 1)), (
            f"fanin's count on {port} was not restored{context}: {counts}"
        )
    digest = ""
    for position, r in enumerate(data, start=1):
        payload = r["payload"]
        folded = f"{digest}|{payload['port']}:{payload['value']}"
        digest = hashlib.sha256(folded.encode()).hexdigest()
        assert payload["digest"] == digest, (
            f"fanin's digest does not follow from the order of sink's trace at copy "
            f"{position} ({payload['port']}:{payload['value']}){context}"
        )


def assert_trace_matches(records, k, context=""):
    """
    The reformulated Acceptance criterion: each port's own sequence,
    exact, in order, no duplicate, no missing value; and fanin's node
    state restored wherever it was relaunched.
    """
    ext_seq = [
        r["payload"]["value"]
        for r in records
        if r.get("type") == "DATA" and r["payload"]["port"] == "ext"
    ]
    loop_seq = [
        r["payload"]["value"]
        for r in records
        if r.get("type") == "DATA" and r["payload"]["port"] == "loop_in"
    ]

    expected = list(range(1, k + 1))
    assert ext_seq == expected, f"ext_seq mismatch{context}: {ext_seq}"
    assert loop_seq == expected, f"loop_seq mismatch{context}: {loop_seq}"
    assert_node_state_restored(records, context)


def assert_engineered_gap_trace(records, k, reported_range, context=""):
    """
    The Acceptance criterion's exception clause, for a run that engineers
    a real loss on the fanin->sink channel on purpose (see
    test_fanin_and_sink_killed_together_over_an_engineered_gap_ends_in_a_recognized_g8_error).

    Once the gap opens, sink's reader thread for this channel dies on it
    identically on every relaunch (the same durable hole is still there
    to rediscover each time), so it never gets past it before giving up
    for good: what survives is not "everything except a hole in the
    middle", it is an exact, gapless prefix of the channel's own sequence
    numbers (each DATA record's own `seq`, not the derived per-port
    value), ending exactly where the gap the G8 error named begins.
    """
    data = [r for r in records if r.get("type") == "DATA" and r.get("seq") is not None]
    seqs = [r["seq"] for r in data]

    lo, hi = reported_range
    if lo is not None:
        assert seqs == list(range(1, lo)), (
            f"surviving trace should be exactly seq 1..{lo - 1}, the reported gap's "
            f"own start, got{context}: {seqs}"
        )
    else:
        # The "torn line" shape names no numbers: still require a clean,
        # gapless prefix (no trust in a number we don't have), and that
        # real loss actually happened rather than a silently full trace.
        assert seqs == list(range(1, len(seqs) + 1)), (
            f"surviving trace is not a clean, gapless prefix{context}: {seqs}"
        )
        assert len(seqs) < 2 * k, f"no loss actually happened{context}: got all {2 * k} sends"

    ext_seq = [r["payload"]["value"] for r in data if r["payload"]["port"] == "ext"]
    loop_seq = [r["payload"]["value"] for r in data if r["payload"]["port"] == "loop_in"]
    assert ext_seq == sorted(set(ext_seq)), f"ext_seq out of order or duplicated{context}: {ext_seq}"
    assert loop_seq == sorted(set(loop_seq)), (
        f"loop_seq out of order or duplicated{context}: {loop_seq}"
    )
    assert_node_state_restored(data, context)


def start_sched_out_tailers(outdir):
    """One SchedOutTailer per killable node, started, keyed by name."""
    tailers = {name: SchedOutTailer(sched_out_file(outdir, name)) for name in KILLABLE_NODES}
    for out in tailers.values():
        out.start()
    return tailers


def find_reported_losses(texts):
    """
    Every G8 error that the nodes' outputs hold, as (node, channel, lo, hi):
    lo..hi is the missing range, or (None, None) for the "torn line" shape,
    which names no numbers (see find_g8_error).
    """
    reported = []
    for name, text in texts.items():
        for m in G8_GAP_RE.finditer(text):
            lo = int(m.group("lo"))
            hi = int(m.group("hi")) if m.group("hi") else lo
            reported.append((name, m.group("channel"), lo, hi))
        for m in G8_TORN_RE.finditer(text):
            reported.append((name, m.group("channel"), None, None))
    return reported


def assert_trace_with_reported_losses(records, k, reported, context=""):
    """
    The Acceptance criterion's exception clause, for a run in which a
    killed node reported a loss: sink's trace is a gapless prefix of its
    channel's sequence numbers (ending right before the gap, if the gap
    is sink's own), and each port's values are in order, with no
    duplicate and nothing that ext was never sent.
    """
    seqs = [r["seq"] for r in records if r.get("type") == "DATA"]
    sink_gaps = [lo for node, _, lo, _ in reported if node == "sink" and lo is not None]
    if sink_gaps:
        assert seqs == list(range(1, min(sink_gaps))), (
            f"sink's trace should be exactly seq 1..{min(sink_gaps) - 1}, before the gap it "
            f"reported{context}: {seqs}"
        )
    else:
        assert seqs == list(range(1, len(seqs) + 1)), (
            f"sink's trace is not a gapless prefix{context}: {seqs}"
        )

    for port in ("ext", "loop_in"):
        values = [
            r["payload"]["value"]
            for r in records
            if r.get("type") == "DATA" and r["payload"]["port"] == port
        ]
        assert values == sorted(set(values)), (
            f"{port} values out of order or duplicated{context}: {values}"
        )
        assert set(values) <= set(range(1, k + 1)), f"{port} values never sent{context}: {values}"
    assert_node_state_restored(records, context)


def halt_and_check_trace(outdir, tailer, node_outs, killed, k, context=""):
    """
    Ends a run in which the nodes named in `killed` were killed at random
    moments, and checks it against the Acceptance criterion.

    A kill can land in the window in which a node has taken a message
    from a fifo but not yet written it to its input log (see the
    Contract's limits): the message is lost for good, the node reports
    it with a G8 error when the next one arrives, and the halt may never
    complete, since that node's reader has stopped. Such a run passes if
    every G8 error came from a killed node and the trace satisfies
    assert_trace_with_reported_losses. A run with no G8 error has to
    halt cleanly and give the exact trace.
    """
    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "60"],
        capture_output=True,
        text=True,
    )
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    texts = {}
    for name, out in node_outs.items():
        out.stop_and_join()
        if out.error is not None:
            raise out.error
        texts[name] = out.text

    reported = find_reported_losses(texts)
    if not reported:
        assert result.returncode == 0, (
            f"debasher_stop_resident failed:\n{result.stdout}\n{result.stderr}"
        )
        assert wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=60)
        assert_trace_matches(tailer.records, k, context)
        return

    not_killed = [loss for loss in reported if loss[0] not in killed]
    assert not not_killed, f"G8 error at a node that was never killed{context}: {not_killed}"
    assert_trace_with_reported_losses(tailer.records, k, reported, f"{context}, reported {reported}")


def wait_for_logged(outdir, name, port, matches, timeout=30.0, interval=0.05):
    """Waits until the input log of node `name` holds an envelope on `port`
    for which `matches(envelope)` is true."""
    log_dir = Path(outdir, "__exec__", name, "log")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for segment in log_dir.glob("*.log"):
            try:
                lines = segment.read_text().splitlines()
            except FileNotFoundError:
                continue
            for line in lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record["port"] == port and matches(record["env"]):
                    return True
        time.sleep(interval)
    return False


def data_numbered(seq):
    return lambda env: env.get("type") == "DATA" and env.get("seq") == seq


def feed(ext_fifo, first, last, interval):
    feeder = ExtFeeder(ext_fifo, last, interval, first=first)
    feeder.start()
    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error


# The detection settings of the Supervisor of the reference program (Sup in
# debasher_chaos_ref.sh), and the margin a real run needs on top of them for
# the processes involved to be scheduled.
HEARTBEAT_CHECK_INTERVAL_SECS = 0.5


HEARTBEAT_TIMEOUT_SECS = 3


DETECTION_MARGIN_SECS = 1.0


DOWN_RE = r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) WARNING +\[checker\] node '{name}' is down"


def down_reported_at(outdir, name, timeout=30.0, interval=0.05):
    """
    The time at which the Supervisor declared node `name` down, from the
    timestamp of its own log line, or None if it did not within `timeout`.
    """
    pattern = re.compile(DOWN_RE.replace("{name}", re.escape(name)), re.MULTILINE)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(sched_out_file(outdir, "sup")) as f:
                m = pattern.search(f.read())
        except FileNotFoundError:
            m = None
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").timestamp()
        time.sleep(interval)
    return None


def copy_at_sink(port, value):
    """Matches the copy of `value`, processed by fanin on `port`, that
    sink receives."""
    return lambda env: (
        env.get("type") == "DATA"
        and env["payload"]["port"] == port
        and env["payload"]["value"] == value
    )


def values_at_sink(records, port):
    return [
        r["payload"]["value"]
        for r in records
        if r.get("type") == "DATA" and r["payload"]["port"] == port
    ]


def logged_values(outdir, name, port):
    """The values of the DATA on `port` in node `name`'s input log, in
    order, read once from disk (nothing may have pruned it)."""
    log_dir = Path(outdir, "__exec__", name, "log")
    values = []
    for segment in sorted(log_dir.glob("*.log"), key=lambda p: int(p.stem)):
        for line in segment.read_text().splitlines():
            record = json.loads(line)
            if record["port"] == port and record["env"].get("type") == "DATA":
                values.append(record["env"]["payload"])
    return values
