"""
Helpers for the tests that run a resident program for real: debasher_exec
and the other tools that make install puts under bin/, never mocks. Such
tests are slow, and some of them kill processes on purpose, so a module that
uses these helpers marks itself with `pytestmark = real_run`, which skips it
unless DEBASHER_RUN_CHAOS_TEST is set: it never runs as part of the ordinary
suite.
"""

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBASHER_EXEC = REPO_ROOT / "bin" / "debasher_exec"
DEBASHER_STOP = REPO_ROOT / "bin" / "debasher_stop"
DEBASHER_STOP_RESIDENT = REPO_ROOT / "bin" / "debasher_stop_resident"

real_run = pytest.mark.skipif(
    not os.environ.get("DEBASHER_RUN_CHAOS_TEST"),
    reason="real debasher_exec run, slow and disruptive: set DEBASHER_RUN_CHAOS_TEST=1 to run it",
)


@pytest.fixture
def outdir(tmp_path):
    """
    The output directory of the program a test runs. Whatever the test
    leaves running is killed when it ends (debasher_stop).
    """
    d = str(tmp_path / "out")
    yield d
    subprocess.run(
        [str(DEBASHER_STOP), "-d", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def launch(pfile, outdir):
    """Runs debasher_exec on the module `pfile`, into `outdir`."""
    assert DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    log_path = os.path.join(os.path.dirname(outdir), "exec.log")
    # A resident program's processes are launched in the background and
    # keep running after debasher_exec itself returns, still holding
    # their inherited stdout/stderr: piping (capture_output=True) would
    # make subprocess.run wait for those too, not just for debasher_exec.
    with open(log_path, "w") as log_file:
        result = subprocess.run(
            [str(DEBASHER_EXEC), "--pfile", str(pfile), "--outdir", outdir],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        pytest.fail(Path(log_path).read_text())


def wait_until(predicate, timeout=30.0, interval=0.1):
    """Waits until `predicate()` is true; returns whether it became so."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def write_line(fifo_path, obj):
    fd = os.open(fifo_path, os.O_WRONLY)
    try:
        os.write(fd, (json.dumps(obj) + "\n").encode())
    finally:
        os.close(fd)


def find_fifo(outdir, name):
    matches = list(Path(outdir, "__fifos__").rglob(name))
    assert matches, f"fifo {name!r} not found under {outdir}"
    return str(matches[0])


def wait_for(path, timeout=30.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(interval)
    return False


def wait_for_text(path, needle, timeout=30.0, interval=0.05):
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


def wait_for_any_text(path, needles, timeout=30.0, interval=0.05):
    """Like wait_for_text, but for any one of several needles; returns
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


class SchedOutTailer(threading.Thread):
    """
    Follows a single node's own .sched_out (its stdout+stderr, where an
    unhandled exception in a reader thread ends up, see debasher::
    _get_process_log_filename) across however many incarnations it takes,
    the same truncation problem SinkTailer solves for the structured
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


def read_pid(id_file):
    try:
        with open(id_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def id_file(outdir, name):
    return os.path.join(outdir, "__exec__", name, f"{name}.id")


def sched_out_file(outdir, name):
    # debasher::_get_process_log_filename's own naming: "<name>.sched_out",
    # truncated and rewritten on every launch/relaunch of that node.
    return os.path.join(outdir, "__exec__", name, f"{name}.sched_out")


def kill_node(outdir, name, timeout=10.0):
    """
    kill -9 -- -$pid on the node's own process group (debasher::_stop_pid's
    own mechanism): every node is its own process group leader (see
    debasher_builtin_sched::launch_chaos), so this reaches whatever it forked
    too. Returns the pid that was killed.
    """
    id_path = id_file(outdir, name)
    assert wait_for(id_path, timeout=timeout), f"{name}.id never appeared"
    pid = read_pid(id_path)
    os.killpg(int(pid), signal.SIGKILL)
    return pid


def wait_for_relaunch(outdir, name, old_pid, timeout=15.0, interval=0.1):
    id_path = id_file(outdir, name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = read_pid(id_path)
        if pid is not None and pid != old_pid:
            return pid
        time.sleep(interval)
    return None
