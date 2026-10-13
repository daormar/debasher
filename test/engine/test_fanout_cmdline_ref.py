"""
Real debasher_exec runs of debasher_fanout_cmdline_ref.sh, a resident program
whose fan-out and fan-in have as many ports as the option -w says: start
sends each message from outside to the next task of worker, the tasks
forward it to collect, and a Supervisor that declares no port of its own
watches every node and relays a manual trigger to start. Checks that the
number of ports and of nodes follows -w, including the nodes the Supervisor
watches, and that it relaunches one task of the array, or the node that fans
in, like any other node. Every test runs too on debasher_fanout_tasks_ref.sh,
the same program with worker as an option generator whose number of tasks -w
gives, and the other processes asking the engine for it, and on
debasher_fanout_array_ref.sh, where worker is an array without an option
generator, asked for in the same way: a relaunched node asks again and finds
as many ports as before.
"""

import json
import os
import signal
from pathlib import Path

import pytest

from resident_run import (
    find_fifo,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_until,
    write_line,
)

pytestmark = real_run

_REFS_DIR = Path(__file__).resolve().parent


@pytest.fixture(
    params=["debasher_fanout_cmdline_ref.sh", "debasher_fanout_tasks_ref.sh", "debasher_fanout_array_ref.sh"]
)
def pfile(request):
    return _REFS_DIR / request.param


def _execdir(outdir, processname):
    return os.path.join(outdir, "__exec__", processname)


def _checkpoint(outdir, node, epoch):
    """The checkpoint of `node` at `epoch`: a process name, or (process, idx)
    for a task of worker."""
    if isinstance(node, tuple):
        processname, idx = node
        return os.path.join(_execdir(outdir, processname), f"checkpoints_{idx}", f"{epoch}.json")
    return os.path.join(_execdir(outdir, node), "checkpoints", f"{epoch}.json")


def _nodes(w):
    return ["start", "collect"] + [("worker", idx) for idx in range(w)]


def _wait_until_every_node_started(outdir, w):
    control_ports = [
        os.path.join(_execdir(outdir, "start"), "control_ports"),
        os.path.join(_execdir(outdir, "collect"), "control_ports"),
    ] + [os.path.join(_execdir(outdir, "worker"), f"control_ports_{idx}") for idx in range(w)]
    assert wait_until(lambda: all(os.path.exists(p) for p in control_ports)), control_ports


def _node_state(path):
    with open(path) as f:
        return json.load(f)["node_state"]


def _round_until(outdir, w, first_epoch, done, timeout=30.0):
    """
    Starts one round after another, through the Supervisor's manual trigger,
    until the checkpoint of collect at a round satisfies `done`: what start
    sends is on its way while the trigger is, so an early round may not
    have it all yet. Checks that each round reaches every node, and returns
    its epoch.
    """
    manual = find_fifo(outdir, "sup_manual")
    epoch = first_epoch

    def next_round_is_done():
        nonlocal epoch
        epoch += 1
        write_line(manual, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {"epoch": epoch}}})
        paths = [_checkpoint(outdir, node, epoch) for node in _nodes(w)]
        assert wait_until(lambda: all(os.path.exists(p) for p in paths), timeout=10.0), paths
        return done(_node_state(_checkpoint(outdir, "collect", epoch)))

    assert wait_until(next_round_is_done, timeout=timeout, interval=0.2)
    return epoch


def test_the_fanout_and_the_fanin_have_as_many_ports_as_the_option_says(pfile, outdir):
    """
    With -w 4, start sends eight messages from outside to the four tasks of
    worker in turn, and collect gets two on each of its four ports. The
    manual trigger reaches start through the port that the engine gave the
    Supervisor, and each round reaches every task.
    """
    w = 4
    launch(pfile, outdir, "-w", str(w))
    _wait_until_every_node_started(outdir, w)

    ext = find_fifo(outdir, "start_ext")
    for i in range(2 * w):
        write_line(ext, {"type": "DATA", "payload": i})

    expected = {f"ind{idx}": 2 for idx in range(w)}
    epoch = _round_until(outdir, w, 0, lambda state: state["counts"] == expected)
    assert _node_state(_checkpoint(outdir, "start", epoch)) == {"sent": 2 * w}


def test_the_supervisor_relaunches_one_task_of_the_array(pfile, outdir):
    """
    A task of worker killed with its process group is relaunched by the
    Supervisor on its own, with its own .id, and goes on forwarding what
    start sends it.
    """
    w = 3
    launch(pfile, outdir, "-w", str(w))
    _wait_until_every_node_started(outdir, w)

    id_path = os.path.join(_execdir(outdir, "worker"), "worker_1.id")
    old_pid = read_pid(id_path)
    os.killpg(int(old_pid), signal.SIGKILL)
    assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)

    ext = find_fifo(outdir, "start_ext")
    for i in range(w):
        write_line(ext, {"type": "DATA", "payload": i})

    expected = {f"ind{idx}": 1 for idx in range(w)}
    _round_until(outdir, w, 0, lambda state: state["counts"] == expected)


def test_the_supervisor_relaunches_the_node_that_fans_in_with_all_its_ports(pfile, outdir):
    """
    collect killed with its process group is relaunched by the Supervisor,
    and gets as many ports as before: what start sends to every task of
    worker afterwards reaches it on each of them.
    """
    w = 3
    launch(pfile, outdir, "-w", str(w))
    _wait_until_every_node_started(outdir, w)

    id_path = os.path.join(_execdir(outdir, "collect"), "collect.id")
    old_pid = read_pid(id_path)
    os.killpg(int(old_pid), signal.SIGKILL)
    assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)

    ext = find_fifo(outdir, "start_ext")
    for i in range(w):
        write_line(ext, {"type": "DATA", "payload": i})

    expected = {f"ind{idx}": 1 for idx in range(w)}
    _round_until(outdir, w, 0, lambda state: state["counts"] == expected)
