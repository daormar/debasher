"""
Node tests of webui_readfish: the business logic of Acquire, which runs the
stand-in of readfish and watches its log, and of Report, which keeps the
timeline, built without the engine with the node harness, run with
debasher_test. The stand-in runs with intervals of milliseconds.
"""

import json
import os
import shutil
import sys
import time

import pytest

from debasher_runtime_testing import load_node

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = f"{sys.executable} {os.path.join(MODULE_DIR, 'fake_readfish.py')} --batch-interval-s 0.005"


def acquire(tmp_path, monkeypatch, fake_opts="", **opts):
    # readfish and its files live in the output directory of the process
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(tmp_path))
    opts = {"command": f"{FAKE} {fake_opts}".strip(), "stall-timeout-s": "0.2", "scan-timeout-s": "0.5",
            "start-timeout-s": "0.5", **opts}
    return load_node("Acquire", opts=opts, inputs=["notes"], outputs=["outevents"])


def report(tmp_path, monkeypatch, **opts):
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(tmp_path))
    return load_node("Report", opts=opts, inputs=["inevents", "indone"], outputs=["outtimeline"])


def wait_for_batches():
    # The stand-in writes a batch every 5 ms
    time.sleep(0.1)


def observe_until(node, kind, tries=20):
    """Observes until an event of `kind` comes in, and returns it."""
    for _ in range(tries):
        for event in node.observe():
            if event["kind"] == kind:
                return event
        time.sleep(0.05)
    raise AssertionError(f"no {kind} event")


def kinds(events):
    return [event["kind"] for event in events]


def stop_child(node):
    node.node._stop_child()


# --- Acquire ----------------------------------------------------------------------


def test_acquire_announces_its_start_and_sends_the_progress_of_readfish(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch)
    try:
        wait_for_batches()
        events = node.observe()

        assert kinds(events)[:2] == ["started", "phase"]
        assert events[0]["incarnation"] == 1
        assert events[1]["phase"] == "PHASE_SEQUENCING"
        progress = [e for e in events if e["kind"] == "progress"]
        assert len(progress) == 1
        assert progress[0]["batches"] >= 1
        assert progress[0]["reads"] >= 1
        assert progress[0]["unb"] >= 0
        assert node.sent("outevents") == events
    finally:
        stop_child(node)


def test_acquire_forwards_a_note_written_by_hand(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch)
    try:
        node.feed("notes", {"text": "flow cell changed"})

        assert node.sent("outevents") == [{"kind": "note", "text": "flow cell changed"}]
    finally:
        stop_child(node)


def test_acquire_raises_when_readfish_stalls_in_the_sequencing_phase(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, "--stall-after 3")
    try:
        observe_until(node, "progress")
        time.sleep(0.3)

        with pytest.raises(RuntimeError, match="no batch of reads"):
            node.observe()

        # The stall event is in the input log, for Report; the child is gone
        assert node.node.child is None
        # A stall after progress is not an attempt without reads
        assert not (tmp_path / "attempts").exists() or (tmp_path / "attempts").read_text().strip() == "0"
    finally:
        stop_child(node)


def test_a_mux_scan_is_not_a_stall_until_the_scan_timeout(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, "--scan-secs 0.3", **{"scan-timeout-s": "0.6"})
    try:
        observe_until(node, "progress")
        (tmp_path / "scan").touch()
        event = observe_until(node, "phase")
        assert event["phase"] == "PHASE_MUX_SCAN"

        # Past the stall timeout, inside the scan: no stall
        time.sleep(0.25)
        node.observe()

        event = observe_until(node, "phase")
        assert event["phase"] == "PHASE_SEQUENCING"
        observe_until(node, "progress")
    finally:
        stop_child(node)


def test_a_scan_that_never_ends_is_a_stall(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, "--scan-secs 60", **{"scan-timeout-s": "0.3"})
    try:
        observe_until(node, "progress")
        (tmp_path / "scan").touch()
        observe_until(node, "phase")
        time.sleep(0.4)

        with pytest.raises(RuntimeError, match="PHASE_MUX_SCAN"):
            node.observe()
    finally:
        stop_child(node)


def test_a_readfish_that_ends_makes_acquire_raise(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, "--exit-after 2 --exit-code 3")
    try:
        time.sleep(0.2)
        with pytest.raises(RuntimeError, match="ended with code 3"):
            node.observe()

        assert node.node.child is None
    finally:
        stop_child(node)


def test_relaunches_with_no_reads_are_counted_and_then_stop(tmp_path, monkeypatch):
    # A readfish that never gives a batch: each incarnation is an attempt
    for attempt in (1, 2):
        node = acquire(tmp_path, monkeypatch, "--batch-interval-s 60", **{"max-attempts": "2"})
        try:
            time.sleep(0.6)
            with pytest.raises(RuntimeError, match="since its start"):
                node.observe()
            assert (tmp_path / "attempts").read_text().strip() == str(attempt)
        finally:
            stop_child(node)

    # At the bound the node stays, with an exhausted event and no exception
    node = acquire(tmp_path, monkeypatch, "--batch-interval-s 60", **{"max-attempts": "2"})
    try:
        time.sleep(0.6)
        events = node.observe()

        assert kinds(events)[-1] == "exhausted"
        assert events[-1]["attempts"] == 2
        assert node.node.child.poll() is None
        assert node.observe() == []
    finally:
        stop_child(node)


def test_reads_again_reset_the_attempts(tmp_path, monkeypatch):
    (tmp_path / "attempts").write_text("3\n")
    node = acquire(tmp_path, monkeypatch)
    try:
        observe_until(node, "progress")

        assert (tmp_path / "attempts").read_text().strip() == "0"
    finally:
        stop_child(node)


def test_each_incarnation_starts_its_own_readfish_and_kills_the_earlier_one(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch)
    first = node.node.child
    try:
        assert (tmp_path / "launches").read_text().strip() == "1"
        # As after a kill -9 of the node: the child is left running
        node.node.child = None

        node = acquire(tmp_path, monkeypatch)

        assert (tmp_path / "launches").read_text().strip() == "2"
        first.wait(timeout=5)
        assert first.poll() is not None
        assert node.node.child.poll() is None
        assert (tmp_path / "readfish.2.log").exists()
    finally:
        first.kill()
        stop_child(node)


def test_a_relative_path_in_the_command_names_a_file_next_to_the_module(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(tmp_path))
    node = load_node("Acquire", opts={"command": f"{sys.executable} fake_readfish.py --batch-interval-s 0.005"},
                     inputs=["notes"], outputs=["outevents"])
    try:
        # The child runs in the output directory of the process, where there
        # is no fake_readfish.py; it is found next to the module
        observe_until(node, "progress")
    finally:
        stop_child(node)


# --- Report -----------------------------------------------------------------------


def progress(t, incarnation=1, batches=5, reads=100, seq=10, unb=90):
    return {"kind": "progress", "t": t, "incarnation": incarnation, "batches": batches, "reads": reads,
            "seq": seq, "unb": unb, "pro": 0}


def test_report_keeps_the_totals_and_sends_a_status_line_per_period(tmp_path, monkeypatch):
    node = report(tmp_path, monkeypatch, **{"status-every-s": "10"})
    node.feed("inevents", progress(100.0))
    node.feed("inevents", progress(105.0, seq=12, unb=200))
    node.feed("inevents", progress(111.0, seq=12, unb=300))

    assert node.sent("outtimeline") == [
        {"kind": "status", "t": 100.0, "phase": None, "incarnation": 1, "batches": 5, "reads": 100, "seq": 10, "unb": 90, "pro": 0},
        {"kind": "status", "t": 111.0, "phase": None, "incarnation": 1, "batches": 15, "reads": 300, "seq": 12, "unb": 300, "pro": 0},
    ]
    timeline = json.loads((tmp_path / "timeline.json").read_text())
    assert timeline["totals"] == {"batches": 15, "reads": 300, "seq": 12, "unb": 300, "pro": 0}


def test_report_records_the_incidents_and_the_phases(tmp_path, monkeypatch):
    node = report(tmp_path, monkeypatch)
    node.feed("inevents", {"kind": "started", "t": 1.0, "incarnation": 1, "command": "readfish"})
    node.feed("inevents", {"kind": "phase", "t": 2.0, "incarnation": 1, "phase": "PHASE_MUX_SCAN"})
    node.feed("inevents", {"kind": "stall", "t": 3.0, "incarnation": 1, "reason": "no reads", "phase": "PHASE_SEQUENCING"})
    node.feed("inevents", {"kind": "started", "t": 4.0, "incarnation": 2, "command": "readfish"})
    node.feed("inevents", {"kind": "note", "text": "by hand"})

    assert kinds(node.sent("outtimeline")) == ["started", "phase", "stall", "started", "note"]
    timeline = json.loads((tmp_path / "timeline.json").read_text())
    assert timeline["incarnations"] == 2
    assert timeline["stalls"] == 1
    assert timeline["phase"] == "PHASE_MUX_SCAN"
    assert len(timeline["incidents"]) == 5


def test_report_takes_the_summary_of_a_finished_batch_run(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "f1"
    (run_dir / "read_lengths").mkdir(parents=True)
    (run_dir / "read_lengths" / "summary.json").write_text(json.dumps({"count": 4, "median": 2250, "short_fraction": 0.5}))
    node = report(tmp_path, monkeypatch)

    node.feed("indone", {"run": "f1", "run_dir": str(run_dir), "status": "finished", "exit_code": 0})
    node.feed("indone", {"run": "f2", "run_dir": str(tmp_path / "runs" / "f2"), "status": "failed", "exit_code": 1})

    sent = node.sent("outtimeline")
    assert sent[0] == {"kind": "file", "run": "f1", "status": "finished", "exit_code": 0, "count": 4, "median": 2250, "short_fraction": 0.5}
    assert sent[1] == {"kind": "file", "run": "f2", "status": "failed", "exit_code": 1}
    assert json.loads((tmp_path / "timeline.json").read_text())["files"] == sent


def test_the_summary_of_a_run_is_remembered_once_its_directory_is_gone(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "f1"
    (run_dir / "read_lengths").mkdir(parents=True)
    (run_dir / "read_lengths" / "summary.json").write_text(json.dumps({"count": 4}))
    done = {"run": "f1", "run_dir": str(run_dir), "status": "finished", "exit_code": 0}
    report(tmp_path, monkeypatch).feed("indone", done)
    shutil.rmtree(run_dir)

    # As a replay does: the same message, processed again, gives the same
    # record, from the memo in the output directory of the process
    node = report(tmp_path, monkeypatch)
    node.feed("indone", done)

    assert node.sent("outtimeline")[0]["count"] == 4


def test_a_finished_run_without_a_summary_is_recorded_as_such(tmp_path, monkeypatch):
    node = report(tmp_path, monkeypatch)

    node.feed("indone", {"run": "f3", "run_dir": str(tmp_path / "nowhere"), "status": "finished", "exit_code": 0})

    assert node.sent("outtimeline")[0]["status"] == "no summary"


def test_a_restarted_report_goes_on_with_its_timeline(tmp_path, monkeypatch):
    node = report(tmp_path, monkeypatch)
    node.feed("inevents", {"kind": "started", "t": 1.0, "incarnation": 1, "command": "readfish"})

    node = node.restart()
    node.feed("inevents", {"kind": "stall", "t": 3.0, "incarnation": 1, "reason": "no reads", "phase": "PHASE_SEQUENCING"})

    timeline = json.loads((tmp_path / "timeline.json").read_text())
    assert timeline["incarnations"] == 1
    assert timeline["stalls"] == 1
    assert kinds(timeline["incidents"]) == ["started", "stall"]


def test_a_replay_of_the_events_gives_the_same_timeline(tmp_path, monkeypatch):
    feeds = [
        ("inevents", {"kind": "started", "t": 1.0, "incarnation": 1, "command": "readfish"}),
        ("inevents", progress(2.0)),
        ("inevents", {"kind": "stall", "t": 70.0, "incarnation": 1, "reason": "no reads", "phase": "PHASE_SEQUENCING"}),
        ("inevents", {"kind": "started", "t": 80.0, "incarnation": 2, "command": "readfish"}),
        ("inevents", progress(90.0, incarnation=2)),
        ("indone", {"run": "f2", "run_dir": str(tmp_path / "none"), "status": "failed", "exit_code": 1}),
    ]
    report(tmp_path, monkeypatch).check_replay(feeds, capture_after=3)
