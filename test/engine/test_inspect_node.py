"""
Unit tests of debasher_inspect_node (engine/debasher_inspect_node.py), the
half of debasher_inspect_resident that reads the files of a node, on an
execdir written here by hand: what each command prints, and the rules of
recovery with which it reads (a torn tail does not count, a segment pruned
while it reads is skipped, a checkpoint of another schema version is only
reported).
"""

import json
import stat
import subprocess
import time

import pytest

import debasher_inspect_node as inspect
import debasher_runtime_inputlog as inputlog
from debasher_runtime_fbp import FBPProcess
from debasher_runtime_envelope import encode_barrier, encode_data

_SCHEMA = FBPProcess.CHECKPOINT_SCHEMA_VERSION


def _record(pos, port, envelope_line):
    return f'{{"pos": {pos}, "port": "{port}", "env": {envelope_line}}}\n'


def _data(pos, port, payload, seq):
    return _record(pos, port, encode_data(payload, seq=seq))


def _checkpoint(epoch, capture_pos, schema_version=_SCHEMA, **fields):
    content = {
        "schema_version": schema_version,
        "epoch": epoch,
        "capture_pos": capture_pos,
        "closed_ports": [],
        "out_seq": {"outf": 7},
        "last_seq": {"inf": 5},
        "out_backlog": {},
        "node_state": {"count": capture_pos},
        "channel_state": {},
    }
    content.update(fields)
    return content


def _node_info(**fields):
    info = {
        "runtime_class": "FBPProcess",
        "started_at": time.time() - 60,
        "heartbeat_interval_secs": 5,
        "limits": {
            "input_log_max_bytes": 1000,
            "out_backlog_max_bytes": 100,
            "out_backlog_fail_bytes": 200,
            "gil_switch_interval_secs": 0.0005,
        },
        "updated_at": time.time(),
        "healthy": True,
        "out_backlog_bytes": {"outf": 12},
        "checkpoints_skipped_since": None,
    }
    info.update(fields)
    return info


@pytest.fixture
def execdir(tmp_path):
    """The execdir of a node `relay` with two checkpoints (the latest one
    captured at position 4), a halted marker, a node info file, and an input
    log of two segments, the second of which ends in a torn tail."""
    d = tmp_path / "__exec__" / "relay"
    (d / "checkpoints").mkdir(parents=True)
    for epoch, capture_pos in ((3, 2), (5, 4)):
        (d / "checkpoints" / f"{epoch}.json").write_text(json.dumps(_checkpoint(epoch, capture_pos)))
    (d / "halted").write_text("5")
    (d / "node_info").write_text(json.dumps(_node_info()))
    (d / "log").mkdir()
    (d / "log" / "1.log").write_text(
        _data(1, "inf", "a", 1)
        + _record(2, "inf", encode_barrier(3))
        + _data(3, "ctl", "b", None)
    )
    (d / "log" / "4.log").write_text(
        _data(4, "inf", "c", 2) + _data(5, "ctl", "d", None) + _data(6, "inf", "e", 3) + '{"pos": 7, "po'
    )
    return d


def _run(execdir, *command, task_idx=None, process_outdir="/nonexistent", debasher_status="/bin/false"):
    argv = [
        "--process",
        "relay",
        "--task-state",
        "alive",
        "--execdir",
        str(execdir),
        "--process-outdir",
        str(process_outdir),
        "--debasher-status",
        str(debasher_status),
    ]
    if task_idx is not None:
        argv += ["--task-idx", str(task_idx)]
    return inspect.run_command([*argv, *command])


# --- summary -------------------------------------------------------------------


def test_the_summary_of_a_node(execdir):
    result = _run(execdir, "summary")

    assert result["process"] == "relay"
    assert result["task"] is None
    assert result["task_state"] == "alive"
    assert [c["epoch"] for c in result["checkpoints"]] == [3, 5]
    assert all(c["written_at"] for c in result["checkpoints"])
    assert result["capture_pos"] == 4
    assert result["halted_epoch"] == 5
    log = result["input_log"]
    assert log["segments"] == 2
    assert log["bytes"] == sum(p.stat().st_size for p in (execdir / "log").iterdir())
    assert log["max_bytes"] == 1000
    # The torn tail of the second segment does not count.
    assert (log["first_pos"], log["last_pos"], log["to_replay"]) == (1, 6, 2)
    info = result["node_info"]
    assert info["out_backlog_bytes"] == {"outf": 12}
    assert info["age_secs"] < 5
    assert info["stale"] is False
    assert result["notice"] is None


def test_the_summary_gives_the_notice_of_the_node(execdir):
    notice = {"level": "warning", "text": "the configuration file is missing", "set_at": 1790000000.5}
    (execdir / "notice").write_text(json.dumps(notice))

    assert _run(execdir, "summary")["notice"] == notice


def test_a_node_info_file_older_than_two_heartbeats_is_stale(execdir):
    (execdir / "node_info").write_text(json.dumps(_node_info(updated_at=time.time() - 11)))
    assert _run(execdir, "summary")["node_info"]["stale"] is True


def test_the_summary_of_a_node_that_has_kept_nothing(tmp_path):
    result = _run(tmp_path, "summary")

    assert result["checkpoints"] == []
    assert result["capture_pos"] is None
    assert result["halted_epoch"] is None
    assert result["node_info"] is None
    assert result["input_log"] == {
        "bytes": 0,
        "max_bytes": None,
        "segments": 0,
        "first_pos": None,
        "last_pos": None,
        "to_replay": 0,
    }


def test_a_task_reads_the_files_with_its_index(execdir):
    for name in ("checkpoints", "log", "halted", "node_info"):
        (execdir / name).rename(execdir / f"{name}_2")

    result = _run(execdir, "summary", task_idx=2)

    assert result["task"] == 2
    assert result["capture_pos"] == 4
    assert result["input_log"]["last_pos"] == 6


def test_a_latest_checkpoint_of_another_schema_version_gives_no_capture_pos(execdir):
    (execdir / "checkpoints" / "5.json").write_text(json.dumps(_checkpoint(5, 4, schema_version=1)))
    assert _run(execdir, "summary")["capture_pos"] is None


def test_a_log_with_nothing_above_the_capture_replays_nothing(execdir):
    (execdir / "checkpoints" / "9.json").write_text(json.dumps(_checkpoint(9, 20)))
    assert _run(execdir, "summary")["input_log"]["to_replay"] == 0


# --- checkpoint ------------------------------------------------------------------


def test_a_checkpoint(execdir):
    backlog = {"outf": [{"seq": 8, "payload": "x"}, {"seq": 9, "payload": "yy"}]}
    in_transit = {"inf": ["z"]}
    (execdir / "checkpoints" / "5.json").write_text(
        json.dumps(_checkpoint(5, 4, out_backlog=backlog, channel_state=in_transit))
    )

    result = _run(execdir, "checkpoint", "5")

    assert result["path"] == str(execdir / "checkpoints" / "5.json")
    assert result["readable"] is True
    assert result["capture_pos"] == 4
    assert result["node_state"] == {"count": 4}
    assert result["out_seq"] == {"outf": 7}
    assert result["last_seq"] == {"inf": 5}
    assert result["out_backlog"] == {
        "outf": {"messages": 2, "bytes": sum(len(json.dumps(m)) for m in backlog["outf"])}
    }
    assert result["channel_state"] == {"inf": {"messages": 1, "bytes": len('"z"')}}


def test_a_checkpoint_of_another_schema_version_is_only_reported(execdir):
    (execdir / "checkpoints" / "5.json").write_text(json.dumps(_checkpoint(5, 4, schema_version=1)))

    result = _run(execdir, "checkpoint", "5")

    assert result["readable"] is False
    assert result["schema_version"] == 1
    assert "node_state" not in result


def test_an_epoch_that_the_node_does_not_retain_is_an_error(execdir):
    with pytest.raises(inspect.InspectError, match=r"epoch 4 .*retains: 3, 5"):
        _run(execdir, "checkpoint", "4")


# --- log -----------------------------------------------------------------------


def test_the_latest_records_of_the_log(execdir):
    result = _run(execdir, "log", "--last", "2")

    assert result["capture_pos"] == 4
    assert result["records"] == [
        {"pos": 5, "port": "ctl", "type": "DATA", "seq": None, "payload": "d"},
        {"pos": 6, "port": "inf", "type": "DATA", "seq": 3, "payload": "e"},
    ]


def test_the_latest_records_of_one_port_across_segments(execdir):
    result = _run(execdir, "log", "--port", "inf", "--last", "3")

    assert [(r["pos"], r["payload"]) for r in result["records"]] == [
        (2, {"epoch": 3, "halt": False}),
        (4, "c"),
        (6, "e"),
    ]
    assert result["records"][0]["type"] == "BARRIER"


def test_the_whole_log_by_default(execdir):
    assert [r["pos"] for r in _run(execdir, "log")["records"]] == [1, 2, 3, 4, 5, 6]


def test_a_line_that_is_not_a_record_is_shown_in_its_place(execdir):
    with open(execdir / "log" / "1.log", "a") as f:
        f.write("garbage\n")

    records = _run(execdir, "log")["records"]

    assert [r.get("pos") for r in records] == [1, 2, 3, None, 4, 5, 6]
    assert records[3]["segment"] == str(execdir / "log" / "1.log")
    assert records[3]["line"] == 4
    assert "not valid JSON" in records[3]["error"]


def test_a_segment_pruned_while_the_log_is_read_is_skipped(execdir, monkeypatch):
    # The node prunes 1.log right after the reader has listed the segments.
    listed = inputlog._list_segment_files(str(execdir / "log"))
    (execdir / "log" / "1.log").unlink()
    monkeypatch.setattr(inputlog, "_list_segment_files", lambda directory: listed)

    assert [r["pos"] for r in _run(execdir, "log")["records"]] == [4, 5, 6]
    assert _run(execdir, "summary")["input_log"]["first_pos"] == 4


# --- runs ----------------------------------------------------------------------

_FAKE_DEBASHER_STATUS = """#!/bin/bash
[ -f "$2/fake_status" ] || exit 1
exit "$(cat "$2/fake_status")"
"""


@pytest.fixture
def launcher(tmp_path, execdir):
    """A launcher node with three registered batch runs: one that ended
    well, one submitted whose program is still in progress, and one never
    launched."""
    runs_root = tmp_path / "runs"
    process_outdir = tmp_path / "launch"
    registrations = process_outdir / ".launcher" / "registrations"
    registrations.mkdir(parents=True)
    for pos, run in ((3, "b"), (1, "a"), (5, "c/v2")):
        (registrations / f"{pos}.json").write_text(json.dumps({"run": run}))
        (runs_root / run).mkdir(parents=True)
    (runs_root / "a" / "exit_code").write_text("0\n")
    (runs_root / "b" / "submitted").touch()
    (runs_root / "b" / "fake_status").write_text("2\n")
    (execdir / "node_info").write_text(
        json.dumps(
            _node_info(
                runtime_class="ProgramLauncher",
                launcher={"runs_root": str(runs_root), "process": None},
            )
        )
    )
    status = tmp_path / "debasher_status"
    status.write_text(_FAKE_DEBASHER_STATUS)
    status.chmod(status.stat().st_mode | stat.S_IXUSR)
    return {"runs_root": runs_root, "process_outdir": process_outdir, "status": status}


def test_the_batch_runs_of_a_launcher_node(execdir, launcher):
    result = _run(
        execdir,
        "runs",
        process_outdir=launcher["process_outdir"],
        debasher_status=launcher["status"],
    )

    root = launcher["runs_root"]
    assert result == {
        "runs_root": str(root),
        "runs": [
            {"pos": 1, "run": "a", "run_dir": str(root / "a"), "state": "finished", "exit_code": 0},
            {"pos": 3, "run": "b", "run_dir": str(root / "b"), "state": "running", "exit_code": None},
            {"pos": 5, "run": "c/v2", "run_dir": str(root / "c/v2"), "state": "registered", "exit_code": None},
        ],
    }


def test_the_tool_only_reads_the_state_of_a_batch_run(execdir, launcher):
    # The program of b has ended: the rule finds it failed, and only the
    # node writes that down.
    (launcher["runs_root"] / "b" / "fake_status").write_text("3\n")

    result = _run(
        execdir, "runs", process_outdir=launcher["process_outdir"], debasher_status=launcher["status"]
    )

    assert result["runs"][1]["state"] == "failed"
    assert result["runs"][1]["exit_code"] == 3
    assert not (launcher["runs_root"] / "b" / "exit_code").exists()


def test_runs_on_a_node_that_is_not_a_launcher_is_an_error(execdir):
    with pytest.raises(inspect.InspectError, match="not a launcher node"):
        _run(execdir, "runs")


def test_runs_on_a_node_that_never_started_is_an_error(tmp_path):
    with pytest.raises(inspect.InspectError, match="never written its node info file"):
        _run(tmp_path, "runs")


# --- notices -------------------------------------------------------------------


def test_the_notices_of_every_node_that_has_one_in_their_order(tmp_path):
    relay, fanout = tmp_path / "relay", tmp_path / "fanout"
    relay.mkdir()
    fanout.mkdir()
    (relay / "notice").write_text(json.dumps({"level": "info", "text": "waiting", "set_at": 1.0}))
    (fanout / "notice_2").write_text(json.dumps({"level": "warning", "text": "task two", "set_at": 2.0}))

    result = inspect.run_command(
        [
            "notices",
            "--node", "fanout", "0", str(fanout),
            "--node", "fanout", "2", str(fanout),
            "--node", "relay", "-", str(relay),
            "--node", "sink", "-", str(tmp_path / "sink"),
        ]
    )

    assert result == {
        "notices": [
            {"process": "fanout", "task": 2, "level": "warning", "text": "task two", "set_at": 2.0},
            {"process": "relay", "task": None, "level": "info", "text": "waiting", "set_at": 1.0},
        ]
    }


def test_notices_of_no_node_is_an_empty_list():
    assert inspect.run_command(["notices"]) == {"notices": []}


def test_a_command_of_one_node_needs_the_node(execdir):
    with pytest.raises(inspect.InspectError, match="--process"):
        inspect.run_command(["--execdir", str(execdir), "summary"])


# --- the command line ----------------------------------------------------------


def test_the_command_line_prints_json_and_ends_with_0(execdir):
    result = subprocess.run(
        [
            "python3",
            inspect.__file__,
            "--process",
            "relay",
            "--task-state",
            "down",
            "--execdir",
            str(execdir),
            "--process-outdir",
            "/nonexistent",
            "--debasher-status",
            "/bin/false",
            "summary",
        ],
        capture_output=True,
        text=True,
        cwd=str(execdir.parent),
        env={"PYTHONPATH": str(inspect.__file__).rsplit("/", 1)[0], "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["task_state"] == "down"


@pytest.mark.parametrize(
    "command",
    [[], ["nonsense"], ["checkpoint", "x"], ["log", "--last", "0"], ["log", "--wrong"]],
)
def test_a_command_it_does_not_understand_is_an_error(execdir, command, capsys):
    argv = [
        "--process", "relay", "--task-state", "alive", "--execdir", str(execdir),
        "--process-outdir", "/x", "--debasher-status", "/bin/false", *command,
    ]
    assert inspect.main(argv) == 1
    assert capsys.readouterr().err.startswith("Error: ")
