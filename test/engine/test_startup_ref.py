"""
Real debasher_exec runs of debasher_startup_ref.sh: slow takes a while over
every message, so its relaunch, which replays its input log, is silent for
longer than the heartbeat timeout of the Supervisor. The startup deadline
that its computational specifications give it (startup_timeout_s), which
the engine passes to the Supervisor, covers the replay, and the Supervisor
does not declare it down again.
"""

import os
import signal
import time
from pathlib import Path

from resident_run import (
    find_fifo,
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    sched_out_file,
    wait_for_text,
    wait_until,
    write_line,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_startup_ref.sh"

_MESSAGES = 10
# The heartbeat timeout of the Supervisor, heartbeat_timeout_s in the program.
_HEARTBEAT_TIMEOUT_SECS = 2


def _logged_data(outdir):
    log_dir = Path(outdir, "__exec__", "slow", "log")
    return sum(
        segment.read_text().count('"type": "DATA"') for segment in log_dir.glob("*.log")
    )


def test_a_replay_longer_than_the_heartbeat_timeout_fits_in_the_startup_deadline(outdir):
    launch(PFILE, outdir)
    assert wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", "slow", "control_ports")))

    ext = find_fifo(outdir, "slow_ext")
    for i in range(_MESSAGES):
        write_line(ext, {"type": "DATA", "payload": i})
    assert wait_until(lambda: _logged_data(outdir) == _MESSAGES)

    id_path = id_file(outdir, "slow")
    old_pid = read_pid(id_path)
    os.killpg(int(old_pid), signal.SIGKILL)
    assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)
    relaunched_at = time.monotonic()

    # No checkpoint, so the relaunch replays every message, half a second
    # each, before its first heartbeat.
    assert wait_for_text(sched_out_file(outdir, "slow"), f"replayed {_MESSAGES} records", timeout=30.0)
    assert time.monotonic() - relaunched_at > _HEARTBEAT_TIMEOUT_SECS
    time.sleep(_HEARTBEAT_TIMEOUT_SECS)

    with open(sched_out_file(outdir, "sup")) as f:
        sup_log = f.read()
    assert "node 'slow' is down (attempt 1/" in sup_log
    assert "attempt 2/" not in sup_log, sup_log
    assert read_pid(id_path) != old_pid
