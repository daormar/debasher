"""
Chaos test for the resident-program engine (see the design doc's "Acceptance:
how reliability is shown"). Drives a real debasher_exec run of
debasher_chaos_ref.sh, never mocks, so it is slow and, in later pieces,
disruptive on purpose (real kill -9 of real processes): skipped unless
DEBASHER_RUN_CHAOS_TEST is set, so it never runs as part of the ordinary
suite.
"""

import json
import os
import random
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PFILE = Path(__file__).resolve().parent / "debasher_chaos_ref.sh"
_DEBASHER_EXEC = _REPO_ROOT / "bin" / "debasher_exec"
_DEBASHER_STOP = _REPO_ROOT / "bin" / "debasher_stop"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEBASHER_RUN_CHAOS_TEST"),
    reason="real debasher_exec chaos test, slow and disruptive: set DEBASHER_RUN_CHAOS_TEST=1 to run it",
)


def _write_line(fifo_path, obj):
    fd = os.open(fifo_path, os.O_WRONLY)
    try:
        os.write(fd, (json.dumps(obj) + "\n").encode())
    finally:
        os.close(fd)


def _find_fifo(outdir, name):
    matches = list(Path(outdir, "__fifos__").rglob(name))
    assert matches, f"fifo {name!r} not found under {outdir}"
    return str(matches[0])


def _wait_for(path, timeout=30.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(interval)
    return False


class _SinkTailer(threading.Thread):
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


class _SchedOutTailer(threading.Thread):
    """
    Follows a single node's own .sched_out (its stdout+stderr, where an
    unhandled exception in a reader thread ends up, see debasher::
    _get_process_log_filename) across however many incarnations it takes,
    the same truncation problem _SinkTailer solves for the structured
    input log: debasher_builtin_sched's own `> file 2>&1` redirection
    truncates this file on every relaunch, so reading it once after the
    run can lose an earlier incarnation's own traceback entirely.

    Detects a new incarnation by the current content no longer starting
    with what was last seen (a plain growing file always does): commits
    whatever was captured of the previous incarnation to .text, then
    starts tracking the new one. A poll interval far shorter than the
    node's own relaunch cadence (seconds, driven by HEARTBEAT_TIMEOUT_SECS)
    makes losing a whole incarnation between two polls very unlikely.
    """

    def __init__(self, path, poll_interval=0.02):
        super().__init__(daemon=True)
        self._path = path
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self.text = ""
        self.error = None

    def stop_and_join(self, timeout=10):
        self._stop_event.set()
        self.join(timeout)

    def run(self):
        current = ""
        try:
            while True:
                should_stop = self._stop_event.is_set()
                try:
                    with open(self._path) as f:
                        content = f.read()
                except FileNotFoundError:
                    content = ""

                if not content.startswith(current):
                    self.text += current
                    current = content
                else:
                    current = content

                if should_stop:
                    self.text += current
                    break
                time.sleep(self._poll_interval)
        except Exception as exc:  # surfaced by the test through .error
            self.error = exc


def _wait_for_text(path, needle, timeout=30.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(path) as f:
                if needle in f.read():
                    return True
        except FileNotFoundError:
            pass
        time.sleep(interval)
    return False


def _wait_for_any_text(path, needles, timeout=30.0, interval=0.05):
    """Like _wait_for_text, but for any one of several needles; returns
    the one that matched, or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(path) as f:
                content = f.read()
            for needle in needles:
                if needle in content:
                    return needle
        except FileNotFoundError:
            pass
        time.sleep(interval)
    return None


# Two shapes a G8 violation on a killed node's channel is seen to take in
# practice (see the design doc's Acceptance status): a clean one naming
# the exact missing sequence numbers, raised when the reader notices the
# jump itself; and a "torn line" one with no numbers, raised when a freshly
# relaunched reader reattaches mid-message to a fifo whose writer never
# itself died (so no fresh HELLO is coming to excuse the fragment). Both
# stop the affected part and are detected, never silent, so both count as
# the accepted exception; only the first names a range to cross-check.
_G8_GAP_RE = re.compile(
    r"gap in the sequence numbers on '(?P<channel>[^']+)': "
    r"expected \d+, got \d+, missing (?P<lo>\d+)(?: to (?P<hi>\d+))?"
)
_G8_TORN_RE = re.compile(r"unparsable line on '(?P<channel>[^']+)' not followed by HELLO")


def _find_g8_error(text, channel):
    """
    Returns (lo, hi) of the reported missing range if the clean, numbered
    shape naming `channel` is found; (None, None) if only the numberless
    "torn line" shape naming `channel` is found; None if neither is.
    """
    m = _G8_GAP_RE.search(text)
    if m and m.group("channel") == channel:
        lo = int(m.group("lo"))
        hi = int(m.group("hi")) if m.group("hi") else lo
        return (lo, hi)
    m = _G8_TORN_RE.search(text)
    if m and m.group("channel") == channel:
        return (None, None)
    return None


_KILLABLE_NODES = ("fanin", "loop", "sink")


def _read_pid(id_file):
    try:
        with open(id_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _id_file(outdir, name):
    return os.path.join(outdir, "__exec__", name, f"{name}.id")


def _sched_out_file(outdir, name):
    # debasher::_get_process_log_filename's own naming: "<name>.sched_out",
    # truncated and rewritten on every launch/relaunch of that node.
    return os.path.join(outdir, "__exec__", name, f"{name}.sched_out")


def _kill_node(outdir, name, timeout=10.0):
    """
    kill -9 -- -$pid on the node's own process group (debasher::_stop_pid's
    own mechanism): every node is its own process group leader (see
    debasher_builtin_sched::_launch), so this reaches whatever it forked
    too. Returns the pid that was killed.
    """
    id_file = _id_file(outdir, name)
    assert _wait_for(id_file, timeout=timeout), f"{name}.id never appeared"
    pid = _read_pid(id_file)
    os.killpg(int(pid), signal.SIGKILL)
    return pid


def _wait_for_relaunch(outdir, name, old_pid, timeout=15.0, interval=0.1):
    id_file = _id_file(outdir, name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = _read_pid(id_file)
        if pid is not None and pid != old_pid:
            return pid
        time.sleep(interval)
    return None


class _ExtFeeder(threading.Thread):
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
    """

    def __init__(self, ext_fifo, k, interval, stop_event=None):
        super().__init__(daemon=True)
        self._ext_fifo = ext_fifo
        self._k = k
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
                for i in range(1, self._k + 1):
                    line = (json.dumps({"type": "DATA", "payload": i}) + "\n").encode()
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


class _SnapshotPacer(threading.Thread):
    """Sends start_snapshot through the manual trigger on a steady beat,
    for as long as the chaos run's main data feed lasts. sup itself is
    never a kill target, so the plain per-message open+write+close of
    _write_line is safe here."""

    def __init__(self, manual_fifo, interval, stop_event):
        super().__init__(daemon=True)
        self._manual_fifo = manual_fifo
        self._interval = interval
        self._stop_event = stop_event

    def run(self):
        while not self._stop_event.wait(self._interval):
            try:
                _write_line(
                    self._manual_fifo,
                    {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}},
                )
            except OSError:
                pass


@pytest.fixture
def outdir(tmp_path):
    d = str(tmp_path / "chaos_out")
    yield d
    subprocess.run(
        [str(_DEBASHER_STOP), "-d", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _launch(outdir):
    assert _DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    log_path = os.path.join(os.path.dirname(outdir), "exec.log")
    # A resident program's processes are launched in the background and
    # keep running after debasher_exec itself returns, still holding
    # their inherited stdout/stderr: piping (capture_output=True) would
    # make subprocess.run wait for those too, not just for debasher_exec.
    with open(log_path, "w") as log_file:
        result = subprocess.run(
            [str(_DEBASHER_EXEC), "--pfile", str(_PFILE), "--outdir", outdir],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        pytest.fail(Path(log_path).read_text())


def _assert_trace_matches(records, k, context=""):
    """
    The reformulated Acceptance criterion: each port's own sequence,
    exact, in order, no duplicate, no missing value.
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


def _assert_engineered_gap_trace(records, k, reported_range, context=""):
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


def test_a_clean_run_produces_the_exact_trace_at_sink(outdir):
    """
    "Run once with no failures" (Acceptance): every value fanin forwards
    from ext, and every one it echoes back through the loop, reaches sink
    exactly once, in the order fanin actually processed it (G1 channel
    order, G2 no silent loss, G4 faithful replay across ports).
    """
    k = 20
    _launch(outdir)
    tailer = _SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")

    for i in range(1, k + 1):
        _write_line(ext_fifo, {"type": "DATA", "payload": i})
        time.sleep(0.02)

    time.sleep(0.5)
    _write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    time.sleep(0.5)
    _write_line(manual_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})

    assert _wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"))
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    _assert_trace_matches(tailer.records, k)


@pytest.mark.parametrize("run_index", range(10))
def test_a_single_random_node_kill_is_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments"
    (Acceptance), restricted here to exactly one kill of exactly one
    node per run: the only shape that cannot touch the Contract's "both
    endpoints of a channel crashed" limit, since every channel's other
    endpoint stays alive the whole time, holding it open. No run here
    should ever need the G8-error exception: every run's trace must
    match the criterion exactly.
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    _launch(outdir)
    tailer = _SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")

    feeder = _ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = _SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    target = rng.choice(_KILLABLE_NODES)
    kill_delay = rng.uniform(0.2, max(0.25, k * interval - 0.2))
    time.sleep(kill_delay)
    old_pid = _kill_node(outdir, target)
    new_pid = _wait_for_relaunch(outdir, target, old_pid)
    assert new_pid is not None, f"{target} (pid {old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Deliberate grace period, not a magic number: the Contract's
    # Conformance status has an open, unfixed finding that a shutdown's
    # halt marker can reach a downstream node with only one pending port
    # (sink) well before an upstream node (fanin) has finished forwarding
    # everything a still-recovering peer (loop, here) owed it on the same
    # channel, silently losing the tail. This test is about recovering
    # from a single kill, not about that separate shutdown race, so it
    # waits for the pipeline to settle before asking for a halt.
    time.sleep(1.0)

    stop_snapshots.set()
    snapshots.join(timeout=5)

    _write_line(manual_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})
    assert _wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=60)

    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    context = f" (killed {target}, pid {old_pid} -> {new_pid}, at +{kill_delay:.2f}s)"
    _assert_trace_matches(tailer.records, k, context)


@pytest.mark.parametrize("run_index", range(10))
def test_loop_and_sink_killed_together_are_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments,
    including several at once" (Acceptance), extended here to killing loop
    and sink together, each at its own independently chosen moment (some
    seeds land the two kills close to simultaneous, others stagger them
    across most of the run). loop and sink are the only pair of killable
    nodes with no direct channel between them: fanin is the other endpoint
    of every channel that touches either one, so this still cannot touch
    the Contract's "both endpoints of a channel crashed" limit, the same
    reasoning as the single-node-kill driver above. No G8-error exception
    is expected here either; every run's trace must match the criterion
    exactly.
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    _launch(outdir)
    tailer = _SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")

    feeder = _ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = _SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    window = max(0.25, k * interval - 0.2)
    kills = sorted((("loop", rng.uniform(0.2, window)), ("sink", rng.uniform(0.2, window))), key=lambda kv: kv[1])
    old_pids = {}
    elapsed = 0.0
    for name, delay in kills:
        time.sleep(max(0.0, delay - elapsed))
        old_pids[name] = _kill_node(outdir, name)
        elapsed = delay

    new_pids = {}
    for name, old_pid in old_pids.items():
        new_pids[name] = _wait_for_relaunch(outdir, name, old_pid)
        assert new_pids[name] is not None, f"{name} (pid {old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Same deliberate grace period as the single-node-kill driver above,
    # and for the same reason: the separate, already-recorded ordered-
    # shutdown G2 gap, not what this test is about.
    time.sleep(1.0)

    stop_snapshots.set()
    snapshots.join(timeout=5)

    _write_line(manual_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})
    assert _wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=60)

    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    context = " (" + ", ".join(
        f"killed {name} pid {old_pids[name]} -> {new_pids[name]} at +{delay:.2f}s"
        for name, delay in kills
    ) + ")"
    _assert_trace_matches(tailer.records, k, context)


@pytest.mark.parametrize("run_index", range(5))
def test_fanin_and_sink_killed_together_over_an_engineered_gap_ends_in_a_recognized_g8_error(
    outdir, run_index
):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] adjacent pairs" (Acceptance): fanin and sink share exactly
    one, one-way channel (fanin.to_sink -> sink.from_fanin), one of the
    only two pairs of killable nodes that can touch the Contract's "both
    endpoints of a channel crashed" limit (see "Limits and non-goals";
    the other is fanin+loop, not covered by this piece).

    Left to random timing, this reference program's nodes are fast enough
    that a real loss essentially never happens (confirmed empirically: a
    relaunched writer resends everything after its last checkpoint, so
    only what it had already checkpointed as sent, and was still sitting
    unread in the fifo when both crashed, is ever actually destroyed, and
    that backlog just doesn't build up on its own here), so this piece
    engineers the loss on purpose instead of hoping for it: SIGSTOP sink
    to freeze its reader (the fifo keeps filling for real, since nothing
    stops fanin's writer thread from pushing into it), let a genuine
    backlog build, close a checkpoint on fanin so that backlog now counts
    as "already sent" as far as its own recovery is concerned, then
    SIGKILL both before either relaunches.

    The run must still end in one of the two shapes a G8 violation is
    seen to take on this channel (see _find_g8_error) naming 'from_fanin',
    and the surviving trace, once the reachable part of the graph (fanin,
    loop) settles, must satisfy _assert_engineered_gap_trace: no
    duplicate, nothing out of order, the missing sends forming a single
    contiguous range, the one the error itself named when it named one.

    sup.finished is not waited on: once sink gives up (exhausts
    MAX_RELAUNCH_ATTEMPTS, which a permanent, engineered gap always
    forces), a separate, already-recorded gap in the Supervisor's own
    escalation-resolution path (see Conformance status) means it may
    never actually appear, even though fanin and loop do finish cleanly.
    The `outdir` fixture's own teardown stops whatever is left running.
    """
    # A long tail is deliberate, not padding: detecting the engineered gap
    # depends on a live message actually arriving on the channel after it
    # opens (G8's own mechanism, see _on_arrival), and sink may take
    # several relaunches, roughly HEARTBEAT_TIMEOUT_SECS apart, before it
    # gives up; k/interval keep the feed running well past that whole
    # window so every relaunch still has something live to read. Once
    # sink does give up, the Supervisor's own escalation shuts fanin down
    # right away, on its own, not waiting for the feed to finish, so the
    # feeder is stopped explicitly once that is observed (see stop_event
    # on _ExtFeeder) instead of being joined to completion like every
    # other piece: the actual, stable count of what it got to send
    # (feeder.sent), not the nominal k, is what the trace is checked
    # against.
    k = 700
    interval = 0.02
    rng = random.Random(run_index)
    _launch(outdir)

    tailer = _SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    sink_out = _SchedOutTailer(_sched_out_file(outdir, "sink"))
    sink_out.start()
    fanin_out = _SchedOutTailer(_sched_out_file(outdir, "fanin"))
    fanin_out.start()

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")
    sup_sched_out = _sched_out_file(outdir, "sup")

    feeder_stop = threading.Event()
    feeder = _ExtFeeder(ext_fifo, k, interval, stop_event=feeder_stop)
    feeder.start()

    time.sleep(0.3)
    sink_pid = int(_read_pid(_id_file(outdir, "sink")))
    os.killpg(sink_pid, signal.SIGSTOP)

    # A generous, fixed floor, not tuned per seed: reliability of the
    # engineered gap matters more here than exploring the parameter
    # space, so only a small jitter is added on top of it.
    time.sleep(0.8 + rng.uniform(0.0, 0.3))

    _write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    assert _wait_for_text(
        sup_sched_out, "node 'fanin' saved a checkpoint", timeout=10
    ), "fanin never closed its checkpoint"

    fanin_pid = int(_read_pid(_id_file(outdir, "fanin")))
    os.killpg(fanin_pid, signal.SIGKILL)
    os.killpg(sink_pid, signal.SIGKILL)

    assert _wait_for_text(
        sup_sched_out, "node 'sink' exceeded", timeout=30
    ), "sink never gave up on the engineered, permanent gap"

    feeder_stop.set()
    feeder.join(timeout=10)
    assert not feeder.is_alive(), "feeder did not stop"
    if feeder.error is not None:
        raise feeder.error
    k = feeder.sent

    # fanin is expected to finish cleanly (it stays reachable once sink,
    # its only other neighbor besides loop, is gone for good): but a
    # separate, incidental consequence of this test's own SIGSTOP
    # technique can occasionally also back fanin's OWN loop_in reader up
    # long enough that its later kill -9 loses something it had already
    # pulled off that fifo but not yet logged, the OTHER documented limit
    # ("Messages read from a FIFO but not yet written to the input log"),
    # not the "both endpoints crashed" one this piece targets. Either
    # outcome is accepted, as long as fanin's own gap, if it has one, was
    # also detected, not silent.
    fanin_outcome = _wait_for_any_text(
        sup_sched_out,
        ["node 'fanin' finished cleanly", "node 'fanin' exceeded"],
        timeout=30,
    )
    assert fanin_outcome is not None, (
        "fanin (still reachable) neither finished nor gave up after sink gave up"
    )
    fanin_out.stop_and_join()
    if fanin_out.error is not None:
        raise fanin_out.error
    if fanin_outcome == "node 'fanin' exceeded":
        assert _G8_GAP_RE.search(fanin_out.text) or _G8_TORN_RE.search(fanin_out.text), (
            f"fanin also gave up, but without a recognizable G8 error: {fanin_out.text!r}"
        )

    assert _wait_for_text(
        sup_sched_out, "node 'loop' finished cleanly", timeout=30
    ), "loop (still reachable) never finished after sink gave up"

    time.sleep(0.5)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    sink_out.stop_and_join()
    if sink_out.error is not None:
        raise sink_out.error

    reported = _find_g8_error(sink_out.text, "from_fanin")
    assert reported is not None, (
        f"no G8 error naming 'from_fanin' found across sink's incarnations: {sink_out.text!r}"
    )
    context = f" (run {run_index}, reported range {reported})"
    _assert_engineered_gap_trace(tailer.records, k, reported, context)


@pytest.mark.parametrize("run_index", range(10))
def test_fanin_and_loop_killed_together_are_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] adjacent pairs" (Acceptance): fanin and loop are the other
    pair that shares a channel (two, in fact: they are this program's only
    cycle) and so, in principle, could touch the "both endpoints of a
    channel crashed" limit the way fanin+sink does (see the engineered-gap
    piece above). Unlike that pair, though, this one cannot touch it, not
    by luck but structurally: closing any round on either of their shared
    channels needs BOTH to be alive and responsive (each is the other's
    peer in the same cycle), so any backlog built while one of them is
    down can never be covered by a checkpoint that has actually closed,
    since closing itself needs the down one's cooperation. On relaunch the
    sender therefore always replays from an older, already-drained
    checkpoint and resends that backlog, self-healing every time.

    Confirmed by trying, first, the same construction the engineered-gap
    piece uses (freeze one side with SIGSTOP, close a checkpoint on the
    other, kill both): freezing loop just left fanin's own round pending
    indefinitely, never closing, until the Supervisor's own heartbeat-
    timeout relaunched loop on its own well past HEARTBEAT_TIMEOUT_SECS,
    at which point fanin's checkpoint closed over a position loop had, by
    construction, already fully drained: no backlog was ever behind it.

    So this piece uses independent random timing instead, the same style
    as the loop+sink piece: every repeat's trace must still match the
    criterion exactly, with no G8 exception expected, because the
    topology itself rules the limit out here, not because timing happened
    to avoid it.
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    _launch(outdir)
    tailer = _SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")

    feeder = _ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = _SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    window = max(0.25, k * interval - 0.2)
    kills = sorted(
        (("fanin", rng.uniform(0.2, window)), ("loop", rng.uniform(0.2, window))),
        key=lambda kv: kv[1],
    )
    old_pids = {}
    elapsed = 0.0
    for name, delay in kills:
        time.sleep(max(0.0, delay - elapsed))
        old_pids[name] = _kill_node(outdir, name)
        elapsed = delay

    new_pids = {}
    for name, old_pid in old_pids.items():
        new_pids[name] = _wait_for_relaunch(outdir, name, old_pid)
        assert new_pids[name] is not None, f"{name} (pid {old_pid}) was never relaunched"

    # Stopped here, right after both relaunches, not after the settle
    # period below like the other kill/relaunch pieces: fanin is this
    # program's only initiator, so a snapshot the pacer fires while
    # fanin's own relaunch is still catching up on earlier rounds can
    # pile epoch after epoch faster than the cycle (fanin and loop,
    # relaunching independently too) can close any of them, observed
    # once (rare, ~3% of repeats) to still be unsettled by the time the
    # final shutdown's own halt round was requested, which then took
    # over a minute to close. Giving the quiet period below, and the
    # feeder's own drain, no more new rounds to compete with removes the
    # pile-up rather than just waiting longer for it to resolve.
    stop_snapshots.set()
    snapshots.join(timeout=5)

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Same deliberate grace period as the other kill/relaunch pieces
    # above, and for the same reason: the separate, already-recorded
    # ordered-shutdown G2 gap, not what this test is about.
    time.sleep(1.0)

    _write_line(manual_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})
    assert _wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=60)

    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    context = " (" + ", ".join(
        f"killed {name} pid {old_pids[name]} -> {new_pids[name]} at +{delay:.2f}s"
        for name, delay in kills
    ) + ")"
    _assert_trace_matches(tailer.records, k, context)
