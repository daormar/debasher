"""
Real debasher_exec runs inspected with debasher_inspect_resident (see
"`debasher_inspect_resident`: what a node keeps" in the design doc): the
summary of a node while it lives, after a round and once it is down or
stopped, its checkpoint and its input log, the tasks of an array process,
the batch runs of a launcher node, and the nodes and commands that the tool
refuses.
"""

import json
import os
import re
import signal
import subprocess
from pathlib import Path

from resident_run import (
    DEBASHER_SNAPSHOT_RESIDENT,
    DEBASHER_STOP_RESIDENT,
    REPO_ROOT,
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

DEBASHER_INSPECT_RESIDENT = REPO_ROOT / "bin" / "debasher_inspect_resident"
ENGINE_TEST_DIR = Path(__file__).resolve().parent

_CLOSED_RE = re.compile(r"^Round (\d+) closed at every node of ", re.MULTILINE)


def inspect(outdir, *args):
    return subprocess.run(
        [str(DEBASHER_INSPECT_RESIDENT), "-d", outdir, *args],
        capture_output=True,
        text=True,
    )


def inspected(outdir, *args):
    """What the tool prints, which has to be JSON and nothing else."""
    result = inspect(outdir, *args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _started(outdir, name):
    return wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", name, "node_info")))


def test_a_node_while_it_lives_after_a_round_and_once_it_stops(outdir):
    launch(ENGINE_TEST_DIR / "debasher_halt_ref.sh", outdir)
    assert _started(outdir, "solo")

    summary = inspected(outdir, "-p", "solo", "summary")
    assert summary["task_state"] == "alive"
    assert summary["checkpoints"] == []
    info = summary["node_info"]
    assert info["runtime_class"] == "FBPProcess"
    assert info["healthy"] is True
    assert info["stale"] is False

    snapshot = subprocess.run(
        [str(DEBASHER_SNAPSHOT_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert snapshot.returncode == 0, snapshot.stderr
    epoch = int(_CLOSED_RE.search(snapshot.stdout).group(1))

    summary = inspected(outdir, "-p", "solo", "summary")
    assert [c["epoch"] for c in summary["checkpoints"]] == [epoch]
    checkpoint = inspected(outdir, "-p", "solo", "checkpoint", str(epoch))
    assert checkpoint["readable"] is True
    assert checkpoint["node_state"] == {}
    # The trigger that opened the round came in through the control port.
    records = inspected(outdir, "-p", "solo", "log")["records"]
    assert [(r["port"], r["type"]) for r in records] == [("trigger", "INTERACT")]
    assert records[0]["payload"]["command"] == "start_snapshot"

    stop = subprocess.run([str(DEBASHER_STOP_RESIDENT), "-d", outdir], capture_output=True, text=True)
    assert stop.returncode == 0, stop.stderr

    summary = inspected(outdir, "-p", "solo", "summary")
    assert summary["task_state"] == "finished"
    assert summary["halted_epoch"] is not None


def test_a_node_that_crashed_is_down(outdir):
    launch(ENGINE_TEST_DIR / "debasher_halt_ref.sh", outdir)
    assert _started(outdir, "solo")

    os.killpg(int(read_pid(id_file(outdir, "solo"))), signal.SIGKILL)

    assert wait_until(lambda: inspected(outdir, "-p", "solo", "summary")["task_state"] == "down")


def test_the_tasks_of_an_array_process(outdir):
    launch(ENGINE_TEST_DIR / "debasher_array_ref.sh", outdir)
    assert wait_until(
        lambda: os.path.exists(os.path.join(outdir, "__exec__", "worker", "node_info_2"))
    )

    summary = inspected(outdir, "-p", "worker", "-t", "2", "summary")
    assert summary["task"] == 2
    assert summary["task_state"] == "alive"

    missing = inspect(outdir, "-p", "worker", "summary")
    assert missing.returncode == 1
    assert "-t has to name one" in missing.stderr
    beyond = inspect(outdir, "-p", "worker", "-t", "3", "summary")
    assert beyond.returncode == 1
    assert "there is no task 3" in beyond.stderr
    not_an_array = inspect(outdir, "-p", "start", "-t", "0", "summary")
    assert not_an_array.returncode == 1
    assert "not an array process" in not_an_array.stderr


def _put_notice(outdir, process, name, text):
    """A notice file as a node leaves it (see set_notice): what `notices`
    reads is the file, whichever code wrote it."""
    path = os.path.join(outdir, "__exec__", process, name)
    with open(path, "w") as f:
        json.dump({"level": "warning", "text": text, "set_at": 1.0}, f)


def test_the_notices_of_every_node_in_order_of_process_and_task(outdir):
    launch(ENGINE_TEST_DIR / "debasher_array_ref.sh", outdir)
    assert wait_until(
        lambda: os.path.exists(os.path.join(outdir, "__exec__", "worker", "node_info_2"))
    )
    _put_notice(outdir, "worker", "notice_2", "task two")
    _put_notice(outdir, "worker", "notice_0", "task zero")
    _put_notice(outdir, "collect", "notice", "collecting")

    result = inspected(outdir, "notices")

    assert [(n["process"], n["task"], n["text"]) for n in result["notices"]] == [
        ("collect", None, "collecting"),
        ("worker", 0, "task zero"),
        ("worker", 2, "task two"),
    ]
    with_process = inspect(outdir, "-p", "worker", "notices")
    assert with_process.returncode == 1
    assert "-p and -t do not apply" in with_process.stderr


def test_the_batch_runs_of_a_launcher_node_and_what_the_tool_refuses(outdir):
    launch(ENGINE_TEST_DIR / "debasher_launcher_ref.sh", outdir)
    assert _started(outdir, "launch")
    write_line(
        find_fifo(outdir, "launch_requests"),
        {"type": "DATA", "payload": {"opts": {"-text": "one", "-secs": "0"}, "run": "r1"}},
    )

    def ended():
        runs = inspected(outdir, "-p", "launch", "runs")["runs"]
        return runs and runs[0]["state"] == "finished"

    assert wait_until(ended, timeout=60.0)
    result = inspected(outdir, "-p", "launch", "runs")
    assert os.path.samefile(result["runs_root"], os.path.join(outdir, "launch"))
    assert [(r["pos"], r["run"], r["exit_code"]) for r in result["runs"]] == [(1, "r1", 0)]
    assert inspected(outdir, "-p", "launch", "summary")["node_info"]["runtime_class"] == "ProgramLauncher"

    supervisor = inspect(outdir, "-p", "sup", "summary")
    assert supervisor.returncode == 1
    assert "Supervisor" in supervisor.stderr
    unknown = inspect(outdir, "-p", "nope", "summary")
    assert unknown.returncode == 1
    not_a_launcher = inspect(outdir, "-p", "sink", "runs")
    assert not_a_launcher.returncode == 1
    assert "not a launcher node" in not_a_launcher.stderr
    no_epoch = inspect(outdir, "-p", "sink", "checkpoint", "12")
    assert no_epoch.returncode == 1
    no_command = inspect(outdir, "-p", "sink")
    assert no_command.returncode == 1

    # The Supervisor has no notice, whatever its execdir holds.
    _put_notice(outdir, "sup", "notice", "not a node")
    _put_notice(outdir, "sink", "notice", "a node")
    assert [n["process"] for n in inspected(outdir, "notices")["notices"]] == ["sink"]
