"""
The Supervisor holds the fifo of every business channel of the program
through a read end that it never reads, so that what a fifo holds outlives
the crash of both nodes of its channel; and a process raises its limit of
open descriptors to what its ports need.

The endpoints here are forked processes that open their fifo exactly as a
node does (_open_fifo_reader, _open_fifo_writer), and both are killed with a
single SIGKILL to their process group, so that neither outlives the other.
"""

import json
import os
import random
import resource
import signal
import subprocess
import sys
import time

import pytest

import debasher_runtime_lib as lib
from debasher_runtime_transport import _open_fifo_reader, _open_fifo_writer, _write_all

_ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")


@pytest.fixture(autouse=True)
def process_execdir(tmp_path, monkeypatch):
    execdir = tmp_path / "out" / "__exec__" / "sup"
    execdir.mkdir(parents=True)
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(execdir))


class _Holder(lib.Supervisor):
    """A Supervisor that watches no node: only what it holds matters here."""


def _holder(paths):
    class Holder(_Holder):
        HOLD_FIFOS = list(paths)

    return Holder(opts={})


# --- the fifos, from the engine -------------------------------------------


def test_the_engine_gives_the_fifos_to_hold_relative_to_the_fifo_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DEBASHER_PROCESS_PORTS",
        "nodes=;trigger=;manual_trigger=;startup=;hold=a/a_to_b,worker/worker_out_1",
    )
    proc = _Holder(opts={})
    assert proc.HOLD_FIFOS == ["a/a_to_b", "worker/worker_out_1"]
    fifodir = tmp_path / "out" / "__fifos__"
    assert proc._held_fifo_paths() == [str(fifodir / "a" / "a_to_b"), str(fifodir / "worker" / "worker_out_1")]


def test_a_supervisor_that_lists_fifos_to_hold_is_refused_when_the_engine_gives_them(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_PORTS", "nodes=;trigger=;manual_trigger=;startup=;hold=")

    class Declares(_Holder):
        HOLD_FIFOS = ["/tmp/x"]

    with pytest.raises(ValueError, match="remove HOLD_FIFOS"):
        Declares(opts={})


def test_the_flag_no_hold_fifos_makes_the_supervisor_hold_nothing(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(
        "DEBASHER_PROCESS_PORTS", "nodes=;trigger=;manual_trigger=;startup=;hold=a/a_to_b"
    )
    proc = _Holder(argv=["-c", "--", "-no_hold_fifos"])
    assert proc.opts == {"no_hold_fifos": True}
    assert proc.HOLD_FIFOS == []
    assert proc._fds_needed() == lib.Supervisor.FD_MARGIN
    # Nothing is opened, so the missing fifo is no error.
    proc._open_fifos()
    assert proc._held_fds == {}


def test_a_missing_fifo_to_hold_stops_the_supervisor(tmp_path):
    proc = _holder([str(tmp_path / "missing")])
    with pytest.raises(FileNotFoundError):
        proc._open_fifos()


# --- what a fifo holds outlives both of its nodes ---------------------------


def _spawn(target, pgid=0):
    pid = os.fork()
    if pid == 0:
        try:
            os.setpgid(0, pgid)
            target()
        finally:
            os._exit(0)
    os.setpgid(pid, pgid or pid)
    return pid


def _kill_group(pgid, *pids):
    os.killpg(pgid, signal.SIGKILL)
    for pid in pids:
        os.waitpid(pid, 0)


def _drain(path):
    """What a relaunched reader finds in the fifo, opened as a node opens it."""
    rfd, gfd = _open_fifo_reader(path)
    os.set_blocking(rfd, False)
    data = b""
    try:
        while True:
            try:
                chunk = os.read(rfd, 65536)
            except BlockingIOError:
                break
            if not chunk:
                break
            data += chunk
    finally:
        os.close(rfd)
        os.close(gfd)
    return data


def _line(seq, size):
    return json.dumps({"type": "DATA", "seq": seq, "payload": "x" * size}) + "\n"


def _unread_after_both_die(path, messages, read_first):
    """
    A writer sends `messages` lines and a reader takes the first `read_first`
    of them; once both are idle, both die together. Returns what a new
    reader then finds in the fifo.
    """
    ready_r, ready_w = os.pipe()

    def reader():
        rfd, _ = _open_fifo_reader(path)
        os.write(ready_w, b"r")
        got = b""
        while got.count(b"\n") < read_first:
            got += os.read(rfd, 1)
        os.write(ready_w, b"R")
        time.sleep(60)

    def writer():
        wfd, _ = _open_fifo_writer(path)
        _write_all(wfd, "".join(_line(seq, 100) for seq in range(1, messages + 1)))
        os.write(ready_w, b"W")
        time.sleep(60)

    r = _spawn(reader)
    assert os.read(ready_r, 1) == b"r"
    w = _spawn(writer, pgid=r)
    assert {os.read(ready_r, 1), os.read(ready_r, 1)} == {b"R", b"W"}
    _kill_group(r, r, w)
    os.close(ready_r)
    os.close(ready_w)
    return _drain(path)


def test_without_a_holder_what_a_fifo_holds_dies_with_both_of_its_nodes(tmp_path):
    path = str(tmp_path / "f")
    os.mkfifo(path)
    assert _unread_after_both_die(path, messages=30, read_first=10) == b""


def test_the_supervisor_keeps_what_a_fifo_holds_when_both_of_its_nodes_die(tmp_path):
    path = str(tmp_path / "f")
    os.mkfifo(path)
    proc = _holder([path])
    proc._open_fifos()
    try:
        left = _unread_after_both_die(path, messages=30, read_first=10)
    finally:
        proc._close_held_fifos()
    assert left == "".join(_line(seq, 100) for seq in range(11, 31)).encode()


def _race_writer(path):
    wfd, _ = _open_fifo_writer(path)
    _write_all(wfd, '\n{"type": "HELLO"}\n')
    seq = 0
    while True:
        seq += 1
        # Some lines above PIPE_BUF, which a kill can cut in two.
        _write_all(wfd, _line(seq, random.choice([50, 500, 3000, 6000, 12000])))


def _race_reader(path):
    rfd, _ = _open_fifo_reader(path)
    while True:
        os.read(rfd, random.choice([1000, 4096, 20000]))
        time.sleep(random.uniform(0, 0.003))


@pytest.mark.parametrize("seed", range(20))
def test_what_the_supervisor_holds_survives_both_nodes_killed_at_any_instant(tmp_path, seed):
    """
    A writer that never stops and a slower reader, killed together at a
    random instant, whatever each was doing: in the middle of a line, of a
    read, blocked on a full pipe. A new reader finds what was left, complete
    lines with consecutive numbers between at most a piece of a line at the
    start (the rest of what the dead reader was taking) and one at the end
    (what the dead writer was writing).
    """
    random.seed(seed)
    path = str(tmp_path / "f")
    os.mkfifo(path)
    proc = _holder([path])
    proc._open_fifos()
    try:
        r = _spawn(lambda: _race_reader(path))
        w = _spawn(lambda: _race_writer(path), pgid=r)
        time.sleep(random.uniform(0.02, 0.2))
        _kill_group(r, r, w)
        left = _drain(path)
    finally:
        proc._close_held_fifos()

    assert left
    pieces = left.split(b"\n")
    seqs = []
    for i, piece in enumerate(pieces):
        if not piece:
            continue
        try:
            envelope = json.loads(piece)
        except ValueError:
            assert i in (0, len(pieces) - 1), f"a broken line in the middle, at {i}"
            continue
        if envelope["type"] == "DATA":
            seqs.append(envelope["seq"])
    assert seqs, left[:200]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))


def test_the_supervisor_lets_go_of_what_it_holds_when_it_stops(tmp_path):
    path = str(tmp_path / "f")
    os.mkfifo(path)
    proc = _holder([path])
    proc.start_threads()
    assert list(proc._held_fds) == [path]
    proc.stop_threads(timeout=5)
    assert proc._held_fds == {}
    assert _unread_after_both_die(path, messages=3, read_first=1) == b""


# --- the limit of open descriptors ---------------------------------------------

_LIMIT_SCRIPT = r"""
import os, resource, sys
sys.path.insert(0, sys.argv[1])
import debasher_runtime_lib as lib

soft, hard = int(sys.argv[3]), int(sys.argv[4])
resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
paths = []
for i in range(int(sys.argv[5])):
    path = os.path.join(sys.argv[2], f"f{i}")
    os.mkfifo(path)
    paths.append(path)

class Holder(lib.Supervisor):
    HOLD_FIFOS = paths

proc = Holder(opts={})
try:
    proc._open_fifos()
except RuntimeError as exc:
    print("error:", exc)
    sys.exit(0)
print("opened", len(proc._held_fds), "soft", resource.getrlimit(resource.RLIMIT_NOFILE)[0])
"""


def _run_limit_script(tmp_path, soft, hard, fifos):
    result = subprocess.run(
        [sys.executable, "-c", _LIMIT_SCRIPT, _ENGINE_DIR, str(tmp_path), str(soft), str(hard), str(fifos)],
        capture_output=True,
        text=True,
        env={**os.environ, "DEBASHER_PROCESS_PORTS": ""},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_a_supervisor_raises_its_limit_of_descriptors_to_what_it_holds(tmp_path):
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard != resource.RLIM_INFINITY and hard < 400:
        pytest.skip(f"the hard limit of descriptors here, {hard}, is too low")
    out = _run_limit_script(tmp_path, soft=128, hard=hard, fifos=300)
    assert out == f"opened 300 soft {300 + lib.Supervisor.FD_MARGIN}"


def test_a_supervisor_whose_hard_limit_is_too_low_stops_before_it_opens_anything(tmp_path):
    out = _run_limit_script(tmp_path, soft=128, hard=128, fifos=300)
    assert out.startswith("error:")
    assert f"needs {300 + lib.Supervisor.FD_MARGIN} open descriptors" in out
    assert "hard limit" in out and "is 128" in out


class _Node(lib.FBPProcess):
    INPUT_PORTS = [f"in{i}" for i in range(5)]
    OUTPUT_PORTS = ["out"]

    def process_data(self, port_name, packet):
        pass

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


def test_a_node_needs_both_ends_of_the_fifo_of_every_port():
    opts = {port: "/dev/null" for port in [*_Node.INPUT_PORTS, *_Node.OUTPUT_PORTS]}
    assert _Node(opts=opts)._fds_needed() == 2 * 6 + lib.FBPProcess.FD_MARGIN
