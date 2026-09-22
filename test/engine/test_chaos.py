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


_KILLABLE_NODES = ("fanin", "loop", "sink")


def _read_pid(id_file):
    try:
        with open(id_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _id_file(outdir, name):
    return os.path.join(outdir, "__exec__", name, f"{name}.id")


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

    def __init__(self, ext_fifo, k, interval):
        super().__init__(daemon=True)
        self._ext_fifo = ext_fifo
        self._k = k
        self._interval = interval
        self.error = None

    def run(self):
        try:
            fd = os.open(self._ext_fifo, os.O_WRONLY)
            try:
                for i in range(1, self._k + 1):
                    line = (json.dumps({"type": "DATA", "payload": i}) + "\n").encode()
                    while True:
                        try:
                            os.write(fd, line)
                            break
                        except BrokenPipeError:
                            time.sleep(0.05)
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
