"""
Real debasher_exec runs of debasher_array_ref.sh, a resident program with an
array process: start fans out to the three tasks of worker, and collect fans
in from them. Checks that every task keeps its own files next to the others'
in the process's directory, and that debasher_stop_resident treats each task
as a node of its own. Every test also runs on debasher_array_gen_ref.sh, the
same program with worker's tasks produced by an option generator.
"""

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from resident_run import (
    DEBASHER_STOP_RESIDENT,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_until,
    write_line,
)

pytestmark = real_run

_PFILES = {
    "loop": Path(__file__).resolve().parent / "debasher_array_ref.sh",
    "generator": Path(__file__).resolve().parent / "debasher_array_gen_ref.sh",
}

_NUM_WORKERS = 3


@pytest.fixture(params=sorted(_PFILES))
def pfile(request):
    return _PFILES[request.param]


def _execdir(outdir, processname):
    return os.path.join(outdir, "__exec__", processname)


def _worker_file(outdir, name, idx):
    return os.path.join(_execdir(outdir, "worker"), f"{name}_{idx}")


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_until_every_node_started(outdir):
    control_ports = [
        os.path.join(_execdir(outdir, "start"), "control_ports"),
        os.path.join(_execdir(outdir, "collect"), "control_ports"),
    ] + [_worker_file(outdir, "control_ports", idx) for idx in range(_NUM_WORKERS)]
    assert wait_until(lambda: all(os.path.exists(p) for p in control_ports)), control_ports


def _start_trigger_fifo(outdir):
    with open(os.path.join(_execdir(outdir, "start"), "control_ports")) as f:
        return f.read().split()[0]


def test_every_task_of_an_array_keeps_its_own_files_and_takes_part_in_a_round(pfile, outdir):
    """
    A snapshot started at start reaches every task of worker through its own
    fifo, and collect through the fifos of the tasks: each task writes its
    checkpoint in checkpoints_<idx>, next to the others', and none of them
    writes to the names that a process that is not an array uses.
    """
    launch(pfile, outdir)
    _wait_until_every_node_started(outdir)

    write_line(_start_trigger_fifo(outdir), {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {"epoch": 7}}})

    checkpoints = [
        os.path.join(_execdir(outdir, "start"), "checkpoints", "7.json"),
        os.path.join(_execdir(outdir, "collect"), "checkpoints", "7.json"),
    ] + [os.path.join(_worker_file(outdir, "checkpoints", idx), "7.json") for idx in range(_NUM_WORKERS)]
    assert wait_until(lambda: all(os.path.exists(p) for p in checkpoints)), checkpoints

    worker_entries = set(os.listdir(_execdir(outdir, "worker")))
    for name in ("checkpoints", "control_ports", "halted", "log"):
        assert name not in worker_entries, sorted(worker_entries)


def test_debasher_stop_resident_stops_every_task_of_an_array(pfile, outdir):
    """
    debasher_stop_resident halts and signals each task of worker as a node of
    its own: every task writes its own halted marker, all with the epoch of
    the one shutdown, and every task ends cleanly, with its own .finished.
    """
    launch(pfile, outdir)
    _wait_until_every_node_started(outdir)

    start = time.monotonic()
    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert elapsed < 10.0, f"took {elapsed:.1f}s, the hard fallback must not have been needed"

    halted = [os.path.join(_execdir(outdir, "start"), "halted"), os.path.join(_execdir(outdir, "collect"), "halted")]
    halted += [_worker_file(outdir, "halted", idx) for idx in range(_NUM_WORKERS)]
    epochs = set()
    for path in halted:
        with open(path) as f:
            epochs.add(int(f.read()))
    assert len(epochs) == 1, epochs

    finished = [
        os.path.join(_execdir(outdir, "start"), "start.finished"),
        os.path.join(_execdir(outdir, "collect"), "collect.finished"),
    ] + [os.path.join(_execdir(outdir, "worker"), f"worker_{idx}.finished") for idx in range(_NUM_WORKERS)]
    for path in finished:
        assert os.path.exists(path), f"{path} was never written"


def test_debasher_stop_resident_leaves_alone_only_the_task_named_with_dash_x(pfile, outdir):
    """
    -x worker:1 names one task: the tool neither waits for it nor signals it,
    and still stops the other tasks of the same array. Task 1 halts all the
    same, since the round reaches it through its fifo, but it keeps running.
    """
    launch(pfile, outdir)
    _wait_until_every_node_started(outdir)

    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "-x", "worker:1", "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    for idx in (0, 2):
        assert os.path.exists(os.path.join(_execdir(outdir, "worker"), f"worker_{idx}.finished"))
    assert not os.path.exists(os.path.join(_execdir(outdir, "worker"), "worker_1.finished"))
    pid = int(read_pid(os.path.join(_execdir(outdir, "worker"), "worker_1.id")))
    assert _pid_alive(pid)

    os.killpg(pid, signal.SIGTERM)
    assert wait_until(lambda: os.path.exists(os.path.join(_execdir(outdir, "worker"), "worker_1.finished")))
