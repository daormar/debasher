"""
Focused real tests of the guarantees of the Contract (see "Acceptance" in the
design doc), each stated in the guarantee's words, in the one situation that
exercises it, on real debasher_exec runs of debasher_chaos_ref.sh: G1, G2,
G4, G5, G6 and G7. G3 is checked by every trace criterion of chaos_ref.py,
through fanin's node state, so by every run that relaunches fanin, and G8 by
the engineered gap of test_chaos.py and the escalation of
test_stop_resident.py.
"""

import json
import os
import random
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

from chaos_ref import (
    DETECTION_MARGIN_SECS,
    ExtFeeder,
    HEARTBEAT_CHECK_INTERVAL_SECS,
    HEARTBEAT_TIMEOUT_SECS,
    SinkTailer,
    SnapshotPacer,
    assert_node_state_restored,
    assert_trace_matches,
    copy_at_sink,
    data_numbered,
    down_reported_at,
    feed,
    halt_and_check_trace,
    halt_and_wait_for_finished,
    launch_chaos,
    logged_values,
    start_sched_out_tailers,
    values_at_sink,
    wait_for_logged,
)
from resident_run import (
    DEBASHER_STOP_RESIDENT,
    find_fifo,
    id_file,
    kill_node,
    outdir,
    read_pid,
    real_run,
    sched_out_file,
    wait_for_relaunch,
    wait_for_text,
    write_line,
)

pytestmark = real_run


def test_on_every_channel_messages_are_delivered_in_the_order_they_were_sent(outdir):
    """
    G1, channel order: on every channel, messages are delivered in the
    order they were sent. A burst with no pause between messages goes
    through the three channels inside the program, fanin to loop, loop
    back to fanin and fanin to sink, and each receiver must have logged
    them in the order they were sent. No round runs, so no log is pruned.
    """
    k = 300
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    feed(find_fifo(outdir, "fanin_ext"), 1, k, 0)
    assert wait_for_logged(outdir, "sink", "from_fanin", copy_at_sink("loop_in", k)), (
        "sink never received the last echo"
    )

    expected = list(range(1, k + 1))
    assert logged_values(outdir, "loop", "from_fanin") == expected, "fanin to loop out of order"
    assert logged_values(outdir, "fanin", "loop_in") == expected, "loop to fanin out of order"
    time.sleep(0.5)
    halt_and_wait_for_finished(outdir)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    seqs = [r["seq"] for r in tailer.records if r.get("type") == "DATA"]
    assert seqs == list(range(1, 2 * k + 1)), "fanin to sink out of order"
    assert_trace_matches(tailer.records, k)


def test_a_message_sent_while_a_round_is_open_reaches_process_data(outdir):
    """
    G2, no silent loss without failures, also while a round is open: send
    5 and then 7 through a fan-in node while a round is open, and
    process_data receives both. loop is frozen, well under
    HEARTBEAT_TIMEOUT_SECS, so that the round fanin opens, which waits for
    loop's marker, stays open. The echo of a 3 sent before the round
    opened reaches fanin while the round is open too, on the port the
    round is waiting on: process_data receives it, and the round keeps a
    copy of it as the state of that channel.
    """
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    ext_fifo = find_fifo(outdir, "fanin_ext")
    checkpoints_dir = Path(outdir, "__exec__", "fanin", "checkpoints")

    loop_pid = int(read_pid(id_file(outdir, "loop")))
    os.killpg(loop_pid, signal.SIGSTOP)
    try:
        write_line(ext_fifo, {"type": "DATA", "seq": 1, "payload": 3})
        assert wait_for_logged(outdir, "fanin", "ext", data_numbered(1)), "fanin never got 3"
        write_line(
            find_fifo(outdir, "sup_trig_fanin"),
            {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}},
        )
        trigger = lambda env: (
            env.get("type") == "INTERACT" and env["payload"]["command"] == "start_snapshot"
        )
        assert wait_for_logged(outdir, "fanin", "trigger", trigger), "fanin never got the trigger"

        write_line(ext_fifo, {"type": "DATA", "seq": 2, "payload": 5})
        write_line(ext_fifo, {"type": "DATA", "seq": 3, "payload": 7})
        for value in (5, 7):
            assert wait_for_logged(outdir, "sink", "from_fanin", copy_at_sink("ext", value)), (
                f"process_data never received {value} while the round was open"
            )
        assert not list(checkpoints_dir.glob("*.json")), "the round closed while loop was frozen"
    finally:
        os.killpg(loop_pid, signal.SIGCONT)

    assert wait_for_logged(outdir, "sink", "from_fanin", copy_at_sink("loop_in", 7)), (
        "the echoes never came back"
    )
    checkpoints = list(checkpoints_dir.glob("*.json"))
    assert len(checkpoints) == 1, f"the round did not close once: {checkpoints}"
    with open(checkpoints[0]) as f:
        assert json.load(f)["channel_state"] == {"loop_in": [3]}

    time.sleep(0.5)
    halt_and_wait_for_finished(outdir)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    assert values_at_sink(tailer.records, "ext") == [3, 5, 7]
    assert values_at_sink(tailer.records, "loop_in") == [3, 5, 7]
    assert_node_state_restored(tailer.records)


@pytest.mark.parametrize("run_index", range(5))
def test_a_relaunched_node_replays_its_ports_in_the_order_it_processed_them(outdir, run_index):
    """
    G4, faithful replay: the input log is one log per node, in the order
    in which the node processes what arrives on all its input ports, so
    that replay reproduces that order exactly, and a node with several
    input ports does not have to be insensitive to how their messages
    interleave. fanin's digest depends on that interleaving; fanin is
    killed while both its ports are busy and snapshots are taken, and the
    digest in every copy sink sees must still follow from the order of
    sink's trace (see assert_node_state_restored).
    """
    k = 60
    interval = 0.03
    rng = random.Random(1000 + run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    feeder = ExtFeeder(find_fifo(outdir, "fanin_ext"), k, interval)
    stop_snapshots = threading.Event()
    snapshots = SnapshotPacer(find_fifo(outdir, "sup_manual"), 0.5, stop_snapshots)
    feeder.start()
    snapshots.start()

    kill_delay = rng.uniform(0.8, k * interval - 0.2)
    time.sleep(kill_delay)
    old_pid = kill_node(outdir, "fanin")
    new_pid = wait_for_relaunch(outdir, "fanin", old_pid)
    assert new_pid is not None, f"fanin (pid {old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error
    time.sleep(1.0)
    stop_snapshots.set()
    snapshots.join(timeout=5)

    context = f" (killed fanin, pid {old_pid} -> {new_pid}, at +{kill_delay:.2f}s)"
    halt_and_check_trace(outdir, tailer, node_outs, {"fanin"}, k, context)


def test_a_running_neighbor_sees_each_message_of_a_relaunched_node_once(outdir):
    """
    G5, no duplicates across a crash: a neighbor that keeps running
    observes each message of a relaunched node once, not twice, and in
    order. fanin is killed after sink has received messages that fanin
    processed after its last checkpoint: its replay sends them again,
    with the same numbers, and sink must drop every one of them. (The
    other half of G5, that a message lost anyway is noticed, is the
    engineered-gap piece of test_chaos.py.)
    """
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    ext_fifo = find_fifo(outdir, "fanin_ext")
    sup_out = sched_out_file(outdir, "sup")

    feed(ext_fifo, 1, 10, 0.01)
    assert wait_for_logged(outdir, "fanin", "loop_in", data_numbered(10)), (
        "the loop never settled"
    )
    write_line(
        find_fifo(outdir, "sup_manual"),
        {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}},
    )
    assert wait_for_text(sup_out, "node 'fanin' saved a checkpoint"), "fanin never checkpointed"

    feed(ext_fifo, 11, 20, 0.01)
    assert wait_for_logged(outdir, "sink", "from_fanin", copy_at_sink("loop_in", 20)), (
        "sink never received everything fanin processed after its checkpoint"
    )
    old_pid = kill_node(outdir, "fanin")
    assert wait_for_relaunch(outdir, "fanin", old_pid) is not None, "fanin was never relaunched"
    replayed = re.compile(r"replayed (\d+) records of the input log")
    deadline = time.monotonic() + 15
    count = None
    while count is None and time.monotonic() < deadline:
        with open(sched_out_file(outdir, "fanin")) as f:
            m = replayed.search(f.read())
        count = int(m.group(1)) if m else None
        time.sleep(0.05)
    assert count is not None and count >= 20, (
        f"fanin's replay did not resend what sink had: {count}"
    )

    feed(ext_fifo, 21, 30, 0.01)
    time.sleep(1.0)
    halt_and_wait_for_finished(outdir)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    assert_trace_matches(tailer.records, 30)


def test_a_program_resumed_after_a_halt_goes_on_where_it_stopped(outdir):
    """
    G6, orderly halt: after a halt every node resumes in the state it had
    when it stopped, loading its checkpoint and replaying from its input
    log what it processed after capturing it. The halt here closes with
    messages in flight: loop is frozen while the last values go round, so
    that their echoes reach fanin only after fanin has captured its state
    for the halt. The program is then stopped and launched again with
    debasher_exec on the same outdir, which is how it resumes (see
    "Ordered shutdown" in the design doc), and fed the rest. Across both
    runs, sink must see each port's exact sequence, and fanin's counts
    must go on from where they stopped.
    """
    k_frozen, k_before, k = 25, 30, 60
    interval = 0.02
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    sup_out = sched_out_file(outdir, "sup")

    feed(find_fifo(outdir, "fanin_ext"), 1, k_frozen, interval)
    assert wait_for_logged(outdir, "fanin", "loop_in", data_numbered(k_frozen)), (
        "the loop never settled before being frozen"
    )

    # Well under HEARTBEAT_TIMEOUT_SECS: debasher_stop_resident stops the
    # Supervisor before anything else, so it never relaunches loop.
    loop_pid = int(read_pid(id_file(outdir, "loop")))
    os.killpg(loop_pid, signal.SIGSTOP)
    try:
        feed(find_fifo(outdir, "fanin_ext"), k_frozen + 1, k_before, interval)
        assert wait_for_logged(outdir, "fanin", "ext", data_numbered(k_before)), (
            f"fanin never logged ext value {k_before}"
        )
        halt = {}
        halter = threading.Thread(
            target=lambda: halt.update(
                result=subprocess.run(
                    [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "60"],
                    capture_output=True,
                    text=True,
                )
            )
        )
        halter.start()
        shutdown = lambda env: env.get("type") == "INTERACT" and env["payload"]["command"] == "shutdown"
        assert wait_for_logged(outdir, "fanin", "trigger", shutdown), "fanin never got the halt"
    finally:
        os.killpg(loop_pid, signal.SIGCONT)
    halter.join(timeout=90)
    result = halt["result"]
    assert result.returncode == 0, f"debasher_stop_resident failed:\n{result.stdout}\n{result.stderr}"
    with open(sup_out) as f:
        assert "node 'loop' is down" not in f.read(), "the Supervisor relaunched the frozen loop"

    launch_chaos(outdir)
    feed(find_fifo(outdir, "fanin_ext"), k_before + 1, k, interval)

    # Same grace period as the kill/relaunch pieces of test_chaos.py, for
    # the same reason.
    time.sleep(1.0)
    halt_and_wait_for_finished(outdir, timeout=60)

    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    assert_trace_matches(tailer.records, k, " (halted with messages in flight, then resumed)")


def test_a_node_whose_process_is_gone_is_noticed_within_the_check_interval(outdir):
    """
    G7, bounded detection: a crashed node is noticed within
    HEARTBEAT_CHECK_INTERVAL_SECS when its PID is verifiably gone, and
    then relaunched.
    """
    launch_chaos(outdir)
    time.sleep(1.0)  # let every node send at least one heartbeat first

    killed_at = time.time()
    old_pid = kill_node(outdir, "fanin")
    noticed_at = down_reported_at(outdir, "fanin")
    assert noticed_at is not None, "the Supervisor never declared fanin down"
    delay = noticed_at - killed_at
    assert delay <= HEARTBEAT_CHECK_INTERVAL_SECS + DETECTION_MARGIN_SECS, (
        f"fanin was declared down {delay:.2f}s after it was killed"
    )
    assert wait_for_relaunch(outdir, "fanin", old_pid) is not None, "fanin was never relaunched"


def test_a_node_with_a_dead_thread_is_noticed_within_the_heartbeat_timeout(outdir):
    """
    G7, bounded detection: a node that is alive but unhealthy, because one
    of its threads died, is noticed within HEARTBEAT_TIMEOUT_SECS, and
    then relaunched. A line that is not JSON, followed by one that is not
    a HELLO, stops the reader thread of fanin's ext port (see the resync
    line in the design doc) while the process and its other threads go
    on.
    """
    launch_chaos(outdir)
    time.sleep(1.0)  # let every node send at least one heartbeat first
    old_pid = read_pid(id_file(outdir, "fanin"))

    fd = os.open(find_fifo(outdir, "fanin_ext"), os.O_WRONLY)
    try:
        broken_at = time.time()
        os.write(fd, b"not json\n" + (json.dumps({"type": "DATA", "seq": 1, "payload": 1}) + "\n").encode())
    finally:
        os.close(fd)

    # Still alive well before the timeout: this is the path of an unhealthy
    # node, not of a process that is gone.
    time.sleep(1.0)
    os.killpg(int(old_pid), 0)

    noticed_at = down_reported_at(outdir, "fanin")
    assert noticed_at is not None, "the Supervisor never declared fanin down"
    delay = noticed_at - broken_at
    assert delay <= HEARTBEAT_TIMEOUT_SECS + HEARTBEAT_CHECK_INTERVAL_SECS + DETECTION_MARGIN_SECS, (
        f"fanin was declared down {delay:.2f}s after its reader thread died"
    )
    assert wait_for_relaunch(outdir, "fanin", old_pid) is not None, "fanin was never relaunched"
