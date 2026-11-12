"""
Real debasher_exec runs of debasher_backlog_ref.sh: src forwards to sink
whatever arrives from outside, with a limit of 1 MiB on its outbound backlog
(out_backlog_fail_mb). With sink frozen, src goes over the limit and fails.
The test then kills it, so that the Supervisor relaunches it at once instead
of after its heartbeat timeout, long enough for sink to stay frozen meanwhile
(that a dead brain thread is noticed is checked in test_guarantees.py). The
replay of the relaunch waits for room; once sink reads again, the replay
ends, and sink has received every message once, in order.
"""

import os
import signal
from pathlib import Path

from chaos_ref import logged_values
from resident_run import (
    find_fifo,
    id_file,
    kill_node,
    launch,
    outdir,
    read_pid,
    real_run,
    sched_out_file,
    wait_for_text,
    wait_until,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_backlog_ref.sh"

# About 2 MiB of messages of about 1 KiB: more than the limit of 1 MiB and
# the pipe to sink together.
_MESSAGES = 2000
_PAD = "p" * 1000


def _feed(fifo_path, count):
    fd = os.open(fifo_path, os.O_WRONLY)
    try:
        for i in range(count):
            line = '{"type": "DATA", "payload": "%d:%s"}\n' % (i, _PAD)
            os.write(fd, line.encode())
    finally:
        os.close(fd)


def _numbers_at_sink(outdir):
    return [int(value.split(":")[0]) for value in logged_values(outdir, "sink", "insrc")]


def test_a_node_over_its_backlog_limit_is_relaunched_and_its_replay_waits_for_its_reader(outdir):
    launch(PFILE, outdir)
    for name in ("src", "sink"):
        assert wait_until(
            lambda: os.path.exists(os.path.join(outdir, "__exec__", name, "control_ports"))
        ), f"{name} never started"

    sink_pid = int(read_pid(id_file(outdir, "sink")))
    os.killpg(sink_pid, signal.SIGSTOP)
    try:
        src_id = id_file(outdir, "src")
        old_pid = read_pid(src_id)
        _feed(find_fifo(outdir, "src_ext"), _MESSAGES)

        assert wait_for_text(sched_out_file(outdir, "src"), "OUT_BACKLOG_FAIL_BYTES"), (
            "src never went over the limit of its backlog"
        )
        # Its readers go on logging what arrives after the brain thread died;
        # what is still in the fifo when it is killed would be lost with it.
        assert wait_until(lambda: len(logged_values(outdir, "src", "ext")) == _MESSAGES), (
            "src never logged every message"
        )
        kill_node(outdir, "src")
        assert wait_until(lambda: read_pid(src_id) not in (None, old_pid)), "src was never relaunched"
        assert wait_for_text(
            sched_out_file(outdir, "src"), "waits for room in the outbound backlog"
        ), "the replay of src never waited for room"
    finally:
        os.killpg(sink_pid, signal.SIGCONT)

    assert wait_until(lambda: len(_numbers_at_sink(outdir)) >= _MESSAGES, timeout=60.0), (
        "sink never received every message"
    )
    assert _numbers_at_sink(outdir) == list(range(_MESSAGES))
    assert wait_for_text(sched_out_file(outdir, "src"), f"replayed {_MESSAGES} records")

    with open(sched_out_file(outdir, "sup")) as f:
        sup_log = f.read()
    assert "node 'src' is down (attempt 1/" in sup_log
    assert "attempt 2/" not in sup_log, sup_log
