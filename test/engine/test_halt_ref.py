"""
Real debasher_exec run of debasher_halt_ref.sh, a single node with no
Supervisor at all: the cleanest, most isolated real-run check of pieza 1
(third G2 fix candidate, design doc, Conformance status) on its own, with
nothing else in the program that could relaunch or otherwise interfere.
See test_chaos.py's own test_a_halt_keeps_every_node_running_until_an_
external_signal_stops_it for the same guarantee against a busier topology
that does have a Supervisor.
"""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PFILE = Path(__file__).resolve().parent / "debasher_halt_ref.sh"
_DEBASHER_EXEC = _REPO_ROOT / "bin" / "debasher_exec"
_DEBASHER_STOP = _REPO_ROOT / "bin" / "debasher_stop"
_DEBASHER_STOP_RESIDENT = _REPO_ROOT / "bin" / "debasher_stop_resident"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEBASHER_RUN_CHAOS_TEST"),
    reason="real debasher_exec run: set DEBASHER_RUN_CHAOS_TEST=1 to run it",
)


def _write_line(fifo_path, obj):
    fd = os.open(fifo_path, os.O_WRONLY)
    try:
        os.write(fd, (json.dumps(obj) + "\n").encode())
    finally:
        os.close(fd)


def _wait_for(path, timeout=30.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def outdir(tmp_path):
    d = str(tmp_path / "halt_ref_out")
    yield d
    subprocess.run(
        [str(_DEBASHER_STOP), "-d", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _launch(outdir):
    assert _DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"
    log_path = os.path.join(os.path.dirname(outdir), "exec.log")
    with open(log_path, "w") as log_file:
        result = subprocess.run(
            [str(_DEBASHER_EXEC), "--pfile", str(_PFILE), "--outdir", outdir],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        pytest.fail(Path(log_path).read_text())


def test_a_lone_node_with_no_supervisor_stays_up_after_halting_and_stops_cleanly_on_sigterm(outdir):
    """
    solo has only a control port, fed from outside, and no Supervisor is
    even part of this program (SUPERVISOR_PORT is optional): checks that
    pieza 1 needs nothing supervisor-shaped to work. A trigger written
    straight into the fifo control_ports names closes solo's round
    (checkpoint, halted marker) without stopping it; only a real SIGTERM
    to its whole process group, sent well after that, makes it exit, and
    cleanly (.finished appears).
    """
    _launch(outdir)

    control_ports_path = os.path.join(outdir, "__exec__", "solo", "control_ports")
    assert _wait_for(control_ports_path), "solo never wrote its control_ports file"
    with open(control_ports_path) as f:
        trigger_fifo = f.read().splitlines()[0]

    _write_line(trigger_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})

    halted_path = os.path.join(outdir, "__exec__", "solo", "halted")
    assert _wait_for(halted_path, timeout=15.0), "solo never marked itself halted"
    with open(halted_path) as f:
        assert f.read() == "0"

    id_path = os.path.join(outdir, "__exec__", "solo", "solo.id")
    assert _wait_for(id_path)
    pid = int(open(id_path).read().strip())
    os.kill(pid, 0)  # raises ProcessLookupError if it is not alive

    # The actual guarantee: still running a couple of seconds after halting,
    # unlike the old self-stopping behaviour.
    time.sleep(2.0)
    os.kill(pid, 0)

    os.killpg(pid, signal.SIGTERM)

    finished_path = os.path.join(outdir, "__exec__", "solo", "solo.finished")
    assert _wait_for(finished_path, timeout=15.0), "solo never exited cleanly after SIGTERM"

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_debasher_stop_resident_stops_a_supervisor_less_program(outdir):
    """
    debasher_stop_resident (pieza 2) against the same lone-node,
    no-Supervisor program: confirms the tool itself does not need one
    either (stop_supervisor_if_any is a no-op when there is none).
    """
    _launch(outdir)

    result = subprocess.run(
        [str(_DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "forcing debasher_stop" not in result.stderr, result.stderr

    finished_path = os.path.join(outdir, "__exec__", "solo", "solo.finished")
    assert os.path.exists(finished_path)
