"""
Real debasher_exec runs of debasher_selfloop_ref.sh, a resident program in
which counter emits on its own through a self-loop: each step sends a value
to sink and sends counter itself the message that triggers the next one.
Checks that a round goes round the loop like any other channel, and that a
counter killed while it counts, and so while the loop holds a message that
only it could read, is relaunched and goes on with no value missing or
repeated at sink.
"""

import json
import os
import signal
from pathlib import Path

from chaos_ref import SinkTailer
from resident_run import (
    find_fifo,
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_until,
    write_line,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_selfloop_ref.sh"

_LIMIT = 300


def _values_at_sink(tailer):
    return [env["payload"] for env in list(tailer.records) if env.get("type") == "DATA"]


def _counter_checkpoint(outdir, epoch):
    return os.path.join(outdir, "__exec__", "counter", "checkpoints", f"{epoch}.json")


def test_a_self_loop_survives_a_round_and_a_crash_of_its_node(outdir):
    """
    A round started while counter counts closes, since its marker goes round
    the loop behind the message in transit, which the checkpoint keeps as the
    channel state of the loop. counter, killed later with its process group,
    takes with it what the loop held; the Supervisor relaunches it, its
    replay resends that with the same numbers, and sink sees 0 to the limit,
    each value once and in order.
    """
    launch(PFILE, outdir)
    assert wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", "counter", "control_ports")))
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    try:
        write_line(find_fifo(outdir, "counter_ext"), {"type": "DATA", "payload": {"limit": _LIMIT}})
        assert wait_until(lambda: len(_values_at_sink(tailer)) >= _LIMIT // 5)

        write_line(
            find_fifo(outdir, "sup_manual"),
            {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {"epoch": 1}}},
        )
        checkpoint = _counter_checkpoint(outdir, 1)
        assert wait_until(lambda: os.path.exists(checkpoint))
        with open(checkpoint) as f:
            saved = json.load(f)
        assert saved["node_state"] == {"limit": _LIMIT}
        assert saved["channel_state"].get("self"), saved["channel_state"]

        count_at_kill = len(_values_at_sink(tailer)) + _LIMIT // 5
        assert wait_until(lambda: len(_values_at_sink(tailer)) >= count_at_kill)
        id_path = id_file(outdir, "counter")
        old_pid = read_pid(id_path)
        os.killpg(int(old_pid), signal.SIGKILL)
        assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)

        assert wait_until(lambda: _LIMIT - 1 in _values_at_sink(tailer), timeout=60.0)
    finally:
        tailer.stop_and_join()
    assert tailer.error is None, tailer.error
    assert _values_at_sink(tailer) == list(range(_LIMIT))
