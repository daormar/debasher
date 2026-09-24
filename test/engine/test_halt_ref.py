"""
Real debasher_exec run of debasher_halt_ref.sh, a single node with no
Supervisor at all: the most isolated real-run check that a halt leaves a
node running until a stop signal (see "Ordered shutdown" in the design doc),
with nothing else in the program that could relaunch or otherwise
interfere. See test_stop_resident.py's own
test_a_halt_keeps_every_node_running_until_an_external_signal_stops_it for
the same behavior in a busier program that does have a Supervisor.
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
    real_run,
    wait_for,
    write_line,
)

pytestmark = real_run

_PFILE = Path(__file__).resolve().parent / "debasher_halt_ref.sh"


def test_a_lone_node_with_no_supervisor_stays_up_after_halting_and_stops_cleanly_on_sigterm(outdir):
    """
    solo has only a control port, fed from outside, and no Supervisor is
    even part of this program (SUPERVISOR_PORT is optional): checks that
    a halt needs nothing supervisor-shaped to work. A trigger written
    straight into the fifo control_ports names closes solo's round
    (checkpoint, halted marker) without stopping it; only a real SIGTERM
    to its whole process group, sent well after that, makes it exit, and
    cleanly (.finished appears).
    """
    launch(_PFILE, outdir)

    control_ports_path = os.path.join(outdir, "__exec__", "solo", "control_ports")
    assert wait_for(control_ports_path), "solo never wrote its control_ports file"
    with open(control_ports_path) as f:
        trigger_fifo = f.read().splitlines()[0]

    write_line(trigger_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})

    halted_path = os.path.join(outdir, "__exec__", "solo", "halted")
    assert wait_for(halted_path, timeout=15.0), "solo never marked itself halted"
    with open(halted_path) as f:
        assert f.read() == "0"

    id_path = os.path.join(outdir, "__exec__", "solo", "solo.id")
    assert wait_for(id_path)
    pid = int(open(id_path).read().strip())
    os.kill(pid, 0)  # raises ProcessLookupError if it is not alive

    # The actual guarantee: still running a couple of seconds after halting,
    # unlike the old self-stopping behaviour.
    time.sleep(2.0)
    os.kill(pid, 0)

    os.killpg(pid, signal.SIGTERM)

    finished_path = os.path.join(outdir, "__exec__", "solo", "solo.finished")
    assert wait_for(finished_path, timeout=15.0), "solo never exited cleanly after SIGTERM"

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_debasher_stop_resident_stops_a_supervisor_less_program(outdir):
    """
    debasher_stop_resident against the same lone-node,
    no-Supervisor program: confirms the tool itself does not need one
    either (stop_supervisor_if_any is a no-op when there is none).
    """
    launch(_PFILE, outdir)

    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "forcing debasher_stop" not in result.stderr, result.stderr

    finished_path = os.path.join(outdir, "__exec__", "solo", "solo.finished")
    assert os.path.exists(finished_path)
