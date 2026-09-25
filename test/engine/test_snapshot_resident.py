"""
Real debasher_exec runs that start snapshot rounds with
debasher_snapshot_resident (see "`debasher_snapshot_resident`: rounds from
outside the program" in the design doc): a single round in a program with no
Supervisor (debasher_halt_ref.sh) and in one with a Supervisor
(debasher_chaos_ref.sh), a round every few seconds that ends by itself when
the program stops, and the exit codes of a round that does not close and of
a program that is not running.
"""

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from chaos_ref import (
    KILLABLE_NODES,
    launch_chaos,
)
from resident_run import (
    DEBASHER_SNAPSHOT_RESIDENT,
    DEBASHER_STOP_RESIDENT,
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_for,
    wait_until,
)

pytestmark = real_run

_HALT_PFILE = Path(__file__).resolve().parent / "debasher_halt_ref.sh"

_CLOSED_RE = re.compile(r"^Round (\d+) closed at every node of ", re.MULTILINE)


def checkpoint_epochs(outdir, name):
    checkpoints_dir = os.path.join(outdir, "__exec__", name, "checkpoints")
    try:
        names = os.listdir(checkpoints_dir)
    except FileNotFoundError:
        return set()
    return {int(n[: -len(".json")]) for n in names if n.endswith(".json")}


def snapshot(outdir, *opts):
    return subprocess.run(
        [str(DEBASHER_SNAPSHOT_RESIDENT), "-d", outdir, *opts],
        capture_output=True,
        text=True,
    )


def test_a_round_closes_in_a_program_with_no_supervisor(outdir):
    """
    solo has no Supervisor to relay a trigger to it, only a control port fed
    from outside: the tool writes the trigger there itself, and the round
    closes with a checkpoint numbered with the time in milliseconds at which
    the tool sent it. A snapshot, not a halt: solo keeps running and writes
    no halted marker.
    """
    launch(_HALT_PFILE, outdir)

    start_ms = time.time_ns() // 1_000_000
    result = snapshot(outdir, "--timeout", "30")
    end_ms = time.time_ns() // 1_000_000

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    match = _CLOSED_RE.search(result.stdout)
    assert match, result.stdout
    epoch = int(match.group(1))
    assert start_ms <= epoch <= end_ms
    assert epoch in checkpoint_epochs(outdir, "solo")

    assert not os.path.exists(os.path.join(outdir, "__exec__", "solo", "halted"))
    os.killpg(int(read_pid(id_file(outdir, "solo"))), 0)


def test_a_round_closes_at_every_node_of_a_program_with_a_supervisor(outdir):
    """
    With a Supervisor, fanin's control port is the Supervisor's trigger
    fifo: the tool writes into it next to the Supervisor, and the round
    that fanin opens reaches loop and sink through the business channels.
    Every node has a checkpoint of that same epoch.
    """
    launch_chaos(outdir)
    time.sleep(1.0)  # let every node send at least one heartbeat first

    result = snapshot(outdir, "--timeout", "30")

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    epoch = int(_CLOSED_RE.search(result.stdout).group(1))
    for name in KILLABLE_NODES:
        assert epoch in checkpoint_epochs(outdir, name), name


def test_every_starts_rounds_until_the_program_stops(outdir):
    """
    --every 1: a round a second, each numbered afresh, and the tool ends by
    itself, with exit code 0, once debasher_stop_resident has stopped the
    program, without being told to.
    """
    launch(_HALT_PFILE, outdir)

    log_path = os.path.join(os.path.dirname(outdir), "snapshot.log")
    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            [str(DEBASHER_SNAPSHOT_RESIDENT), "-d", outdir, "--every", "1"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    try:
        assert wait_until(lambda: len(checkpoint_epochs(outdir, "solo")) >= 3, timeout=20.0), (
            Path(log_path).read_text()
        )

        stop = subprocess.run(
            [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
            capture_output=True,
            text=True,
        )
        assert stop.returncode == 0, f"{stop.stdout}\n{stop.stderr}"

        assert proc.wait(timeout=15) == 0, Path(log_path).read_text()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    log = Path(log_path).read_text()
    closed = [int(e) for e in _CLOSED_RE.findall(log)]
    assert len(closed) >= 3, log
    assert closed == sorted(set(closed)), log
    assert "no more rounds" in log, log


def test_a_round_that_does_not_close_exits_with_2_naming_the_node(outdir):
    """
    solo is frozen (SIGSTOP): the trigger still goes into its control port,
    which it holds open, but the round never closes there, and the tool
    gives up at --timeout with exit code 2, not 1, naming it. A program
    with no Supervisor, which would relaunch a frozen node once its
    heartbeats stop and let the relaunched one close the round.
    """
    launch(_HALT_PFILE, outdir)
    # Frozen once its threads run, not while it starts up
    assert wait_for(os.path.join(outdir, "__exec__", "solo", "control_ports"))

    solo_pid = int(read_pid(id_file(outdir, "solo")))
    os.killpg(solo_pid, signal.SIGSTOP)
    try:
        result = snapshot(outdir, "--timeout", "3")
    finally:
        os.killpg(solo_pid, signal.SIGCONT)

    assert result.returncode == 2, f"{result.stdout}\n{result.stderr}"
    assert re.search(r"no checkpoint of round \d+ or of a newer one at solo$", result.stderr, re.MULTILINE), (
        result.stderr
    )
    assert "did not close at every node" in result.stderr


def test_a_program_that_is_not_running_is_an_error(outdir):
    launch(_HALT_PFILE, outdir)
    stop = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert stop.returncode == 0, f"{stop.stdout}\n{stop.stderr}"

    result = snapshot(outdir, "--timeout", "5")

    assert result.returncode == 1, f"{result.stdout}\n{result.stderr}"
    assert "is running" in result.stderr
