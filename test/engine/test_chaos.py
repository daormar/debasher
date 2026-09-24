"""
Chaos test for the resident-program engine (see the design doc's "Acceptance:
how reliability is shown"): real debasher_exec runs of debasher_chaos_ref.sh
under kill -9 of random nodes, relaunched by the Supervisor, whose trace at
sink has to meet the Acceptance criterion (see chaos_ref.py).
"""

import json
import os
import random
import signal
import threading
import time
from pathlib import Path

import pytest

from chaos_ref import (
    ExtFeeder,
    G8_GAP_RE,
    G8_TORN_RE,
    KILLABLE_NODES,
    SinkTailer,
    SnapshotPacer,
    assert_engineered_gap_trace,
    assert_trace_matches,
    find_g8_error,
    halt_and_check_trace,
    halt_and_wait_for_finished,
    launch_chaos,
    start_sched_out_tailers,
)
from resident_run import (
    SchedOutTailer,
    find_fifo,
    id_file,
    kill_node,
    outdir,
    read_pid,
    real_run,
    sched_out_file,
    wait_for,
    wait_for_any_text,
    wait_for_relaunch,
    wait_for_text,
    write_line,
)

pytestmark = real_run


def test_a_clean_run_produces_the_exact_trace_at_sink(outdir):
    """
    "Run once with no failures" (Acceptance): every value fanin forwards
    from ext, and every one it echoes back through the loop, reaches sink
    exactly once, in the order fanin actually processed it (G1 channel
    order, G2 no silent loss, G4 faithful replay across ports).
    """
    k = 20
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")

    for i in range(1, k + 1):
        write_line(ext_fifo, {"type": "DATA", "payload": i})
        time.sleep(0.02)

    time.sleep(0.5)
    write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    time.sleep(0.5)
    halt_and_wait_for_finished(outdir)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    assert_trace_matches(tailer.records, k)


@pytest.mark.parametrize("run_index", range(10))
def test_a_single_random_node_kill_is_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments"
    (Acceptance), restricted here to exactly one kill of exactly one
    node per run: the only shape that cannot touch the Contract's "both
    endpoints of a channel crashed" limit, since every channel's other
    endpoint stays alive the whole time, holding it open. The kill can
    still land in the window in which the node has taken a message from a
    fifo but not yet logged it, the Contract's other limit: such a run
    passes with the G8 error that reports the loss (see
    halt_and_check_trace), and every other run's trace must match the
    criterion exactly.
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")

    feeder = ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    target = rng.choice(KILLABLE_NODES)
    kill_delay = rng.uniform(0.2, max(0.25, k * interval - 0.2))
    time.sleep(kill_delay)
    old_pid = kill_node(outdir, target)
    new_pid = wait_for_relaunch(outdir, target, old_pid)
    assert new_pid is not None, f"{target} (pid {old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Lets the pipeline settle before the halt: what fanin forwards after
    # its halt marker (the last echoes of a loop still catching up after a
    # relaunch) reaches sink's log only if sink takes it before its stop
    # signal, and the rest would arrive on a resume, which this test does
    # not run.
    time.sleep(1.0)

    stop_snapshots.set()
    snapshots.join(timeout=5)

    context = f" (killed {target}, pid {old_pid} -> {new_pid}, at +{kill_delay:.2f}s)"
    halt_and_check_trace(outdir, tailer, node_outs, {target}, k, context)


@pytest.mark.parametrize("run_index", range(10))
def test_loop_and_sink_killed_together_are_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments,
    including several at once" (Acceptance), extended here to killing loop
    and sink together, each at its own independently chosen moment (some
    seeds land the two kills close to simultaneous, others stagger them
    across most of the run). loop and sink are the only pair of killable
    nodes with no direct channel between them: fanin is the other endpoint
    of every channel that touches either one, so this still cannot touch
    the Contract's "both endpoints of a channel crashed" limit, the same
    reasoning as the single-node-kill driver above. As there, a kill that
    lands between a read and its logging ends the run with a G8 error
    instead (see halt_and_check_trace); every other run's trace must
    match the criterion exactly.
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")

    feeder = ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    window = max(0.25, k * interval - 0.2)
    kills = sorted((("loop", rng.uniform(0.2, window)), ("sink", rng.uniform(0.2, window))), key=lambda kv: kv[1])
    old_pids = {}
    elapsed = 0.0
    for name, delay in kills:
        time.sleep(max(0.0, delay - elapsed))
        old_pids[name] = kill_node(outdir, name)
        elapsed = delay

    new_pids = {}
    for name, old_pid in old_pids.items():
        new_pids[name] = wait_for_relaunch(outdir, name, old_pid)
        assert new_pids[name] is not None, f"{name} (pid {old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Same grace period as the single-node-kill driver above, for the same
    # reason.
    time.sleep(1.0)

    stop_snapshots.set()
    snapshots.join(timeout=5)

    context = " (" + ", ".join(
        f"killed {name} pid {old_pids[name]} -> {new_pids[name]} at +{delay:.2f}s"
        for name, delay in kills
    ) + ")"
    halt_and_check_trace(outdir, tailer, node_outs, set(old_pids), k, context)


@pytest.mark.parametrize("run_index", range(5))
def test_fanin_and_sink_killed_together_without_a_holder_end_in_a_recognized_g8_error(
    outdir, run_index
):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] adjacent pairs" (Acceptance): fanin and sink share exactly
    one, one-way channel (fanin.outsink -> sink.from_fanin), one of the
    only two pairs of killable nodes that can touch the Contract's "both
    endpoints of a channel crashed" limit (see "Limits and non-goals";
    the other is fanin+loop, not covered by this piece). The program is
    run with -no_hold_fifos, so that the Supervisor does not hold that
    fifo and the limit is reached: with it held, the same construction
    loses nothing (see the next piece).

    Left to random timing, this reference program's nodes are fast enough
    that a real loss essentially never happens (confirmed empirically: a
    relaunched writer resends everything after its last checkpoint, so
    only what it had already checkpointed as sent, and was still sitting
    unread in the fifo when both crashed, is ever actually destroyed, and
    that backlog just doesn't build up on its own here), so this piece
    engineers the loss on purpose instead of hoping for it: SIGSTOP sink
    to freeze its reader (the fifo keeps filling for real, since nothing
    stops fanin's writer thread from pushing into it), let a genuine
    backlog build, close a checkpoint on fanin so that backlog now counts
    as "already sent" as far as its own recovery is concerned, then
    SIGKILL both before either relaunches.

    The run must still end in one of the two shapes a G8 violation is
    seen to take on this channel (see find_g8_error) naming 'from_fanin',
    and the surviving trace, once the reachable part of the graph (fanin,
    loop) settles, must satisfy assert_engineered_gap_trace: no
    duplicate, nothing out of order, the missing sends forming a single
    contiguous range, the one the error itself named when it named one.

    sup.finished is also waited on, once sink gives up (exhausts
    MAX_RELAUNCH_ATTEMPTS, which a permanent, engineered gap always
    forces): the Supervisor's escalation must stop the reachable part of
    the graph and then end the Supervisor itself (see "Escalation on a
    permanent node failure" in the design doc). See
    test_supervisor_escalation_stops_the_reachable_graph_after_a_permanent_failure
    for a simpler, dedicated real run of the same mechanism; this one
    checks it in this scenario too.
    """
    # A long tail is deliberate, not padding: detecting the engineered gap
    # depends on a live message actually arriving on the channel after it
    # opens (G8's own mechanism, see _on_arrival), and sink may take
    # several relaunches, roughly HEARTBEAT_TIMEOUT_SECS apart, before it
    # gives up; k/interval keep the feed running well past that whole
    # window so every relaunch still has something live to read. Once
    # sink does give up, the Supervisor's own escalation shuts fanin down
    # right away, on its own, not waiting for the feed to finish, so the
    # feeder is stopped explicitly once that is observed (see stop_event
    # on ExtFeeder) instead of being joined to completion like every
    # other piece: the actual, stable count of what it got to send
    # (feeder.sent), not the nominal k, is what the trace is checked
    # against.
    k = 700
    interval = 0.02
    rng = random.Random(run_index)
    launch_chaos(outdir, "-no_hold_fifos")

    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    sink_out = SchedOutTailer(sched_out_file(outdir, "sink"))
    sink_out.start()
    fanin_out = SchedOutTailer(sched_out_file(outdir, "fanin"))
    fanin_out.start()

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")
    sup_sched_out = sched_out_file(outdir, "sup")

    feeder_stop = threading.Event()
    feeder = ExtFeeder(ext_fifo, k, interval, stop_event=feeder_stop)
    feeder.start()

    time.sleep(0.3)
    sink_pid = int(read_pid(id_file(outdir, "sink")))
    os.killpg(sink_pid, signal.SIGSTOP)

    # A generous, fixed floor, not tuned per seed: reliability of the
    # engineered gap matters more here than exploring the parameter
    # space, so only a small jitter is added on top of it.
    time.sleep(0.8 + rng.uniform(0.0, 0.3))

    write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    assert wait_for_text(
        sup_sched_out, "node 'fanin' saved a checkpoint", timeout=10
    ), "fanin never closed its checkpoint"

    fanin_pid = int(read_pid(id_file(outdir, "fanin")))
    os.killpg(fanin_pid, signal.SIGKILL)
    os.killpg(sink_pid, signal.SIGKILL)

    assert wait_for_text(
        sup_sched_out, "node 'sink' exceeded", timeout=30
    ), "sink never gave up on the engineered, permanent gap"

    feeder_stop.set()
    feeder.join(timeout=10)
    assert not feeder.is_alive(), "feeder did not stop"
    if feeder.error is not None:
        raise feeder.error
    k = feeder.sent

    # fanin is expected to finish cleanly (it stays reachable once sink,
    # its only other neighbor besides loop, is gone for good): but a
    # separate, incidental consequence of this test's own SIGSTOP
    # technique can occasionally also back fanin's OWN loop_in reader up
    # long enough that its later kill -9 loses something it had already
    # pulled off that fifo but not yet logged, the OTHER documented limit
    # ("Messages read from a FIFO but not yet written to the input log"),
    # not the "both endpoints crashed" one this piece targets. Either
    # outcome is accepted, as long as fanin's own gap, if it has one, was
    # also detected, not silent.
    fanin_outcome = wait_for_any_text(
        sup_sched_out,
        ["node 'fanin' finished cleanly", "node 'fanin' exceeded"],
        timeout=30,
    )
    assert fanin_outcome is not None, (
        "fanin (still reachable) neither finished nor gave up after sink gave up"
    )
    fanin_out.stop_and_join()
    if fanin_out.error is not None:
        raise fanin_out.error
    if fanin_outcome == "node 'fanin' exceeded":
        assert G8_GAP_RE.search(fanin_out.text) or G8_TORN_RE.search(fanin_out.text), (
            f"fanin also gave up, but without a recognizable G8 error: {fanin_out.text!r}"
        )

    assert wait_for_text(
        sup_sched_out, "node 'loop' finished cleanly", timeout=30
    ), "loop (still reachable) never finished after sink gave up"

    assert wait_for(
        os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=30
    ), "sup.finished never appeared after the escalation resolved the reachable graph"

    time.sleep(0.5)
    tailer.stop_and_join()
    if tailer.error is not None:
        raise tailer.error
    sink_out.stop_and_join()
    if sink_out.error is not None:
        raise sink_out.error

    reported = find_g8_error(sink_out.text, "from_fanin")
    assert reported is not None, (
        f"no G8 error naming 'from_fanin' found across sink's incarnations: {sink_out.text!r}"
    )
    context = f" (run {run_index}, reported range {reported})"
    assert_engineered_gap_trace(tailer.records, k, reported, context)


def _latest_checkpoint(outdir, name):
    """The latest checkpoint that node `name` has saved, or None."""
    checkpoints = Path(outdir, "__exec__", name, "checkpoints")
    epochs = [int(p.stem) for p in checkpoints.glob("*.json") if p.stem.isdigit()]
    if not epochs:
        return None
    return json.loads((checkpoints / f"{max(epochs)}.json").read_text())


@pytest.mark.parametrize("run_index", range(5))
def test_fanin_and_sink_killed_together_over_an_engineered_backlog_lose_nothing(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] adjacent pairs" (Acceptance): fanin and sink share exactly
    one, one-way channel (fanin.outsink -> sink.from_fanin), so killing
    both is the case of "both endpoints of a channel crashed" (see the
    Contract's limits), which the Supervisor's hold on the fifo of every
    business channel covers.

    Left to random timing, this program's nodes are fast enough that the
    fifo never holds anything that a relaunched fanin would not send again,
    so the case is engineered on purpose: SIGSTOP sink to freeze its
    reader, let a backlog build in the fifo (nothing stops fanin's writer
    thread from pushing into it), close a checkpoint on fanin so that the
    backlog counts as already sent as far as its own recovery is concerned,
    then SIGKILL both before either is relaunched. Without a holder the
    backlog dies with them, and sink reports the hole from the first number
    of the backlog up to the last one that the checkpoint covers (G8, see
    the previous piece). With the Supervisor holding the fifo, the relaunched sink reads the backlog,
    and drops as duplicates what the relaunched fanin sends again.

    The SIGSTOP can also freeze a reader after it has taken a block from a
    fifo but before it has logged it, the other limit ("Messages read from
    a FIFO but not yet written to the input log"), at sink or at fanin's
    loop_in: halt_and_check_trace accepts such a loss when it was reported
    by a killed node. At sink it can only take what was in the fifo when
    it was stopped, so a hole it reports must end before the last number
    that fanin had written when it saved its checkpoint, which is where the
    hole of a lost backlog would end.
    """
    k = 200
    interval = 0.02
    rng = random.Random(run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")
    sup_sched_out = sched_out_file(outdir, "sup")

    feeder = ExtFeeder(ext_fifo, k, interval)
    feeder.start()

    time.sleep(0.3)
    sink_pid = read_pid(id_file(outdir, "sink"))
    os.killpg(int(sink_pid), signal.SIGSTOP)
    time.sleep(0.8 + rng.uniform(0.0, 0.3))

    write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    assert wait_for_text(
        sup_sched_out, "node 'fanin' saved a checkpoint", timeout=10
    ), "fanin never closed its checkpoint"

    # What fanin had written to the fifo when it saved its checkpoint, and
    # what sink, frozen since, has logged: the backlog is in between.
    checkpoint = _latest_checkpoint(outdir, "fanin")
    written = checkpoint["out_seq"]["outsink"] - len(checkpoint["out_backlog"].get("outsink", []))
    logged = max((r["seq"] for r in list(tailer.records) if r.get("type") == "DATA"), default=0)
    assert written > logged, f"no backlog built in the fifo: written {written}, logged {logged}"

    fanin_pid = read_pid(id_file(outdir, "fanin"))
    os.killpg(int(fanin_pid), signal.SIGKILL)
    os.killpg(int(sink_pid), signal.SIGKILL)

    for name, old_pid in (("fanin", fanin_pid), ("sink", sink_pid)):
        assert wait_for_relaunch(outdir, name, old_pid) is not None, (
            f"{name} (pid {old_pid}) was never relaunched"
        )

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error
    time.sleep(1.0)

    context = f" (run {run_index}, backlog {logged + 1} to {written})"
    reported = halt_and_check_trace(outdir, tailer, node_outs, {"fanin", "sink"}, k, context)
    for node, channel, lo, hi in reported:
        if node == "sink" and channel == "from_fanin":
            assert hi is not None and hi < written, (
                f"sink lost the backlog that the fifo held{context}: reported {lo} to {hi}"
            )


@pytest.mark.parametrize("run_index", range(10))
def test_fanin_and_loop_killed_together_are_recovered_with_no_loss_or_duplicate(outdir, run_index):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] adjacent pairs" (Acceptance): fanin and loop are the other
    pair that shares a channel (two, in fact: they are this program's only
    cycle) and so, in principle, could touch the "both endpoints of a
    channel crashed" limit the way fanin+sink does without a holder (see
    the engineered-gap pieces above). Unlike that pair, though, this one cannot touch it, not
    by luck but structurally: closing any round on either of their shared
    channels needs BOTH to be alive and responsive (each is the other's
    peer in the same cycle), so any backlog built while one of them is
    down can never be covered by a checkpoint that has actually closed,
    since closing itself needs the down one's cooperation. On relaunch the
    sender therefore always replays from an older, already-drained
    checkpoint and resends that backlog, self-healing every time.

    Confirmed by trying, first, the same construction the engineered-gap
    pieces use (freeze one side with SIGSTOP, close a checkpoint on the
    other, kill both): freezing loop just left fanin's own round pending
    indefinitely, never closing, until the Supervisor's own heartbeat-
    timeout relaunched loop on its own well past HEARTBEAT_TIMEOUT_SECS,
    at which point fanin's checkpoint closed over a position loop had, by
    construction, already fully drained: no backlog was ever behind it.

    So this piece uses independent random timing instead, the same style
    as the loop+sink piece: no run can end in the "both endpoints"
    exception, because the topology itself rules that limit out here, not
    because timing happened to avoid it. A kill between a read and its
    logging still ends a run with a G8 error, as in the pieces above (see
    halt_and_check_trace).
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")

    feeder = ExtFeeder(ext_fifo, k, interval)
    stop_snapshots = threading.Event()
    snapshots = SnapshotPacer(manual_fifo, 0.7, stop_snapshots)
    feeder.start()
    snapshots.start()

    window = max(0.25, k * interval - 0.2)
    kills = sorted(
        (("fanin", rng.uniform(0.2, window)), ("loop", rng.uniform(0.2, window))),
        key=lambda kv: kv[1],
    )
    old_pids = {}
    elapsed = 0.0
    for name, delay in kills:
        time.sleep(max(0.0, delay - elapsed))
        old_pids[name] = kill_node(outdir, name)
        elapsed = delay

    new_pids = {}
    for name, old_pid in old_pids.items():
        new_pids[name] = wait_for_relaunch(outdir, name, old_pid)
        assert new_pids[name] is not None, f"{name} (pid {old_pid}) was never relaunched"

    # Stopped here, right after both relaunches, not after the settle
    # period below like the other kill/relaunch pieces: fanin is this
    # program's only initiator, so a snapshot the pacer fires while
    # fanin's own relaunch is still catching up on earlier rounds can
    # pile epoch after epoch faster than the cycle (fanin and loop,
    # relaunching independently too) can close any of them, observed
    # once (rare, ~3% of repeats) to still be unsettled by the time the
    # final shutdown's own halt round was requested, which then took
    # over a minute to close. Giving the quiet period below, and the
    # feeder's own drain, no more new rounds to compete with removes the
    # pile-up rather than just waiting longer for it to resolve.
    stop_snapshots.set()
    snapshots.join(timeout=5)

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Same grace period as the other kill/relaunch pieces above, for the
    # same reason.
    time.sleep(1.0)

    context = " (" + ", ".join(
        f"killed {name} pid {old_pids[name]} -> {new_pids[name]} at +{delay:.2f}s"
        for name, delay in kills
    ) + ")"
    halt_and_check_trace(outdir, tailer, node_outs, set(old_pids), k, context)


@pytest.mark.parametrize("run_index", range(10))
def test_fanin_killed_during_an_open_snapshot_round_is_recovered_with_no_loss_or_duplicate(
    outdir, run_index
):
    """
    "run... repeatedly under kill -9 of random nodes at random moments...
    [including] moments in which a snapshot round is open" (Acceptance).

    fanin, this program's only initiator, is the only node with a genuine
    window between opening its own round (the instant it relays a manual
    start_snapshot trigger) and closing it (once loop_in's marker
    completes the round trip through loop): every other node's own round
    closes atomically, in the same step that its one pending port's
    marker arrives, so there is nothing to land a kill inside for them.
    `loop` is briefly `SIGSTOP`ped first (well under
    `HEARTBEAT_TIMEOUT_SECS`, so the `Supervisor`'s own heartbeat-timeout
    machinery never notices or interferes) so the round trip cannot
    complete no matter how long fanin's round stays open, `fanin` is
    killed at its own randomly chosen moment inside that window, then
    `loop` is resumed.

    A crash during an ordinary (non-halt) round recovers cleanly: `fanin`
    forgets the open round on relaunch and a later marker reopens it (see
    "A crash while a round is open" in the Contract's limits). A crash
    during a halt round is a different case, which this piece does not
    exercise. As in the pieces above, a kill that lands between a read and
    its logging ends the run with a G8 error instead (see
    halt_and_check_trace).
    """
    k = 60
    interval = 0.03
    rng = random.Random(run_index)
    launch_chaos(outdir)
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    node_outs = start_sched_out_tailers(outdir)

    ext_fifo = find_fifo(outdir, "fanin_ext")
    manual_fifo = find_fifo(outdir, "sup_manual")

    feeder = ExtFeeder(ext_fifo, k, interval)
    feeder.start()

    time.sleep(rng.uniform(0.1, 0.5))
    loop_pid = int(read_pid(id_file(outdir, "loop")))
    os.killpg(loop_pid, signal.SIGSTOP)

    write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )

    # Anywhere in this range lands inside fanin's still-open round: loop
    # cannot complete the round trip while stopped, and this whole window
    # stays comfortably under HEARTBEAT_TIMEOUT_SECS (3s), so the
    # Supervisor never has a chance to notice or relaunch loop itself.
    open_round_delay = rng.uniform(0.02, 1.5)
    time.sleep(open_round_delay)

    fanin_old_pid = int(read_pid(id_file(outdir, "fanin")))
    os.killpg(fanin_old_pid, signal.SIGKILL)

    os.killpg(loop_pid, signal.SIGCONT)

    fanin_new_pid = wait_for_relaunch(outdir, "fanin", str(fanin_old_pid))
    assert fanin_new_pid is not None, f"fanin (pid {fanin_old_pid}) was never relaunched"

    feeder.join(timeout=60)
    assert not feeder.is_alive(), "feeder did not finish sending"
    if feeder.error is not None:
        raise feeder.error

    # Same grace period as the other kill/relaunch pieces above, for the
    # same reason.
    time.sleep(1.0)

    context = (
        f" (killed fanin pid {fanin_old_pid} -> {fanin_new_pid}, "
        f"{open_round_delay:.2f}s into its open round)"
    )
    halt_and_check_trace(outdir, tailer, node_outs, {"fanin"}, k, context)
