"""
Real debasher_exec runs of debasher_chaos_ref.sh that stop the program: a halt
that leaves every node running until a stop signal, debasher_stop_resident
(a graceful stop, -x, the exit code of its hard-kill fallback), and the
Supervisor's escalation after a node fails for good.
"""

import os
import signal
import subprocess
import time

import pytest

from chaos_ref import (
    KILLABLE_NODES,
    launch_chaos,
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
    wait_for,
    wait_for_relaunch,
    wait_for_text,
    write_line,
)

pytestmark = real_run


def test_a_halt_keeps_every_node_running_until_an_external_signal_stops_it(outdir):
    """
    A halt behaves like an ordinary snapshot at every node, and only an
    external actor decides when it is safe to stop, by a real SIGTERM once
    every node's halted marker exists (see "Ordered shutdown" in the design
    doc). This checks the nodes' side, without the tool that normally
    sends that SIGTERM (debasher_stop_resident, tested below): fanin's
    control port is discoverable from its own execdir (no Supervisor
    involved in finding it), every node marks itself halted once its own
    round closes, every node is still alive at that point (a node that
    stopped as soon as its own round closed would lose what its peers
    were still sending it, against G2), and a real SIGTERM then stops
    each one cleanly.
    """
    launch_chaos(outdir)

    control_ports = {}
    for name in KILLABLE_NODES:
        path = os.path.join(outdir, "__exec__", name, "control_ports")
        assert wait_for(path), f"{name} never wrote its control_ports file"
        with open(path) as f:
            control_ports[name] = f.read().splitlines()

    assert control_ports["fanin"] == [find_fifo(outdir, "sup_trig_fanin")]
    assert control_ports["loop"] == []
    assert control_ports["sink"] == []

    # Trigger the halt directly on fanin's own control port, the way
    # debasher_stop_resident does (not through the Supervisor's manual
    # trigger, which is a separate path entirely).
    write_line(
        control_ports["fanin"][0], {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}}
    )

    halted_paths = {name: os.path.join(outdir, "__exec__", name, "halted") for name in KILLABLE_NODES}
    for name, path in halted_paths.items():
        assert wait_for(path, timeout=15.0), f"{name} never marked itself halted"

    # The guarantee this piece exists for: closing the round does not stop
    # anyone by itself, unlike before.
    pids = {}
    for name in KILLABLE_NODES:
        pid = read_pid(id_file(outdir, name))
        assert pid is not None, f"{name} has no pid"
        os.kill(int(pid), 0)  # raises ProcessLookupError if it is not alive
        pids[name] = int(pid)
    time.sleep(1.0)
    for name, pid in pids.items():
        os.kill(pid, 0)  # still alive a moment later, not a race with a self-stop that never happens

    for name, pid in pids.items():
        # The whole process group, not the lone pid: the pid in .id is the
        # process-group leader (the script launch_chaos backgrounds), and a
        # resident process's own Python interpreter sits at least one
        # pipeline subshell below it (see
        # debasher_builtin_sched::_execute_funct_plus_postfunct); a plain
        # single-pid SIGTERM never reaches it at all: it only kills the
        # wrapper, orphaning a Python process that then never receives
        # anything and runs forever, and the dead wrapper never gets to
        # write .finished either. The wrapper
        # itself survives this same broadcast (see
        # debasher_builtin_sched::_print_script_trap) so it can still do
        # so once its own child actually exits.
        os.killpg(pid, signal.SIGTERM)

    for name in KILLABLE_NODES:
        finished = os.path.join(outdir, "__exec__", name, f"{name}.finished")
        assert wait_for(finished, timeout=15.0), f"{name} never exited cleanly after SIGTERM"

    # Nothing about how the Supervisor notices a clean finish had to change
    # for this: .finished is already checked unconditionally, every tick.
    assert wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=15.0)


def test_debasher_stop_resident_stops_the_whole_program_cleanly(outdir):
    """
    debasher_stop_resident itself (see "`debasher_stop_resident`: the
    graceful stop tool" in the design doc): stops the Supervisor first, by
    the same graceful signal
    (its own new SIGTERM handler, engine/debasher_runtime_supervisor.py),
    so it cannot relaunch a node while the rest of this runs, then halts
    and signals every business node. Every process, sup included, must
    exit cleanly (.finished), and quickly: this is the plain, no-failure
    case, nothing here should ever need the hard fallback to debasher_stop.
    """
    launch_chaos(outdir)
    time.sleep(1.0)  # let every node send at least one heartbeat first

    start = time.monotonic()
    start_ms = time.time_ns() // 1_000_000
    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    end_ms = time.time_ns() // 1_000_000
    elapsed = time.monotonic() - start

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "forcing debasher_stop" not in result.stderr, result.stderr
    assert elapsed < 10.0, f"took {elapsed:.1f}s, the hard fallback must not have been needed"

    # The shutdown carries its epoch, the time in milliseconds when the tool sent it, and every
    # node halts in that same round.
    halted_epochs = set()
    for name in KILLABLE_NODES:
        with open(os.path.join(outdir, "__exec__", name, "halted")) as f:
            halted_epochs.add(int(f.read()))
    assert len(halted_epochs) == 1, halted_epochs
    assert start_ms <= halted_epochs.pop() <= end_ms

    for name in (*KILLABLE_NODES, "sup"):
        finished = os.path.join(outdir, "__exec__", name, f"{name}.finished")
        assert os.path.exists(finished), f"{name} never wrote .finished"


def test_debasher_stop_resident_dash_x_leaves_the_named_node_alone(outdir):
    """
    The -x flag: a node named there is not waited for and not signalled,
    which the Supervisor's escalation relies on to leave out a node it
    has given up on. Excludes sink, still healthy here (nothing has
    failed): every other node, sup included, must still stop cleanly, and
    sink must still be running afterward, completely untouched.
    """
    launch_chaos(outdir)
    time.sleep(1.0)

    sink_pid = int(read_pid(id_file(outdir, "sink")))

    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "-x", "sink", "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    for name in ("fanin", "loop", "sup"):
        finished = os.path.join(outdir, "__exec__", name, f"{name}.finished")
        assert os.path.exists(finished), f"{name} never wrote .finished"

    assert not os.path.exists(os.path.join(outdir, "__exec__", "sink", "sink.finished"))
    os.kill(sink_pid, 0)  # raises ProcessLookupError if sink was touched


def test_debasher_stop_resident_forced_exit_code_on_the_hard_kill_fallback(outdir):
    """
    The exit code of the hard-kill fallback (see "Failing loudly instead of
    retrying" in the design doc; DEBASHER_STOP_RESIDENT_FORCED_EXIT in
    engine/debasher_stop_resident.sh): a graceful stop and a forced one
    both end the program, but only the exit code (2, not whatever
    debasher_stop's own happens to be, typically 0) tells a caller which
    one actually happened, since a caller that redirects stderr (the
    Supervisor's own escalation, in particular) would otherwise never
    know.

    Forces the fallback for real: SIGSTOPs loop before calling the tool, so
    it can never process the shutdown trigger or write its own halted
    marker, then calls the tool with a short --timeout. The tool must still
    end the whole program (the hard-kill fallback actually running, not just
    the exit code alone), but return 2, not 0, and say so on stderr too.
    """
    launch_chaos(outdir)
    time.sleep(1.0)

    loop_pid = int(read_pid(id_file(outdir, "loop")))
    os.killpg(loop_pid, signal.SIGSTOP)

    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "3"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2, f"{result.stdout}\n{result.stderr}"
    assert "forcing debasher_stop" in result.stderr

    # The hard kill actually ran, SIGSTOP notwithstanding (SIGKILL is not
    # blockable and reaches a stopped process the same as a running one):
    # every process the program launched must be gone.
    for name in ("fanin", "loop", "sink", "sup"):
        pid = read_pid(id_file(outdir, name))
        assert pid is not None, f"{name} has no pid to check"
        with pytest.raises(ProcessLookupError):
            os.killpg(int(pid), 0)


def test_supervisor_escalation_stops_the_reachable_graph_after_a_permanent_failure(outdir):
    """
    The Supervisor's escalation (Supervisor._escalate_shutdown calling
    debasher_stop_resident with -x and --keep-supervisor, see "Escalation
    on a permanent node failure" in the design doc). Drives sink to
    genuinely exhaust
    MAX_RELAUNCH_ATTEMPTS: a real, repeated kill -9 of each fresh
    relaunch, SIGSTOP first (before SIGKILL) so it can never send a
    heartbeat in between and accidentally reset its own relaunch budget
    (a relaunched node's heartbeat thread waits one full
    HEARTBEAT_INTERVAL_SECONDS from start_threads() before its first
    send, per the reference program's own Sup class comment; freezing it
    first removes the race rather than trying to outrun it).

    Once sink has given up, this checks what the escalation guarantees:
    fanin and loop, still reachable, are gracefully halted and signalled
    by the escalation's own debasher_stop_resident call (not left running
    unattended), and sup.finished actually appears, on its own, well under
    FORCE_STOP_TIMEOUT_SECS (60s): if -x were not actually excluding
    sink (already dead by then), the tool would instead hang waiting on
    a control_ports/halted marker/.finished that can never come, time
    out, and fall back to a hard debasher_stop, which kills fanin and
    loop too, ungracefully (no "finished cleanly" logged for either).
    sup.finished appearing also shows that the Supervisor's own
    resolution after a node gives up completes, after relaunching that
    node several times.
    """
    launch_chaos(outdir)

    sup_out = sched_out_file(outdir, "sup")
    pid = kill_node(outdir, "sink")
    gave_up = False
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        # A tight poll interval, and no wait between detecting a fresh
        # relaunch and freezing it: the race this loop is trying to win
        # (SIGSTOP landing before the relaunch's own first heartbeat,
        # sent one HEARTBEAT_INTERVAL_SECONDS after its start_threads())
        # is won or lost within a few hundred ms, so any extra delay this
        # loop itself adds between iterations just hands it back.
        new_pid = wait_for_relaunch(outdir, "sink", pid, timeout=15.0, interval=0.01)
        if new_pid is None:
            # No further relaunch is exactly what a give-up also looks
            # like from here (nothing left to detect a new pid for): the
            # check below after the loop is what actually decides it.
            break
        os.killpg(int(new_pid), signal.SIGSTOP)
        os.killpg(int(new_pid), signal.SIGKILL)
        pid = new_pid
        try:
            with open(sup_out) as f:
                if "node 'sink' exceeded" in f.read():
                    gave_up = True
                    break
        except FileNotFoundError:
            pass
    if not gave_up:
        gave_up = wait_for_text(sup_out, "node 'sink' exceeded", timeout=2.0)
    assert gave_up, "sink never exceeded MAX_RELAUNCH_ATTEMPTS"

    escalation_start = time.monotonic()
    assert wait_for_text(
        sup_out, "node 'fanin' finished cleanly", timeout=30
    ), "fanin (still reachable) never finished after sink gave up"
    assert wait_for_text(
        sup_out, "node 'loop' finished cleanly", timeout=30
    ), "loop (still reachable) never finished after sink gave up"
    assert wait_for(
        os.path.join(outdir, "__exec__", "sup", "sup.finished"), timeout=30
    ), "sup.finished never appeared after the escalation resolved the reachable graph"
    elapsed = time.monotonic() - escalation_start
    assert elapsed < 30.0, (
        f"took {elapsed:.1f}s: this close to FORCE_STOP_TIMEOUT_SECS (60s) is the sign "
        "debasher_stop_resident fell back to a hard kill instead of stopping gracefully "
        "(e.g. -x not actually excluding sink, or --keep-supervisor not applied)"
    )
