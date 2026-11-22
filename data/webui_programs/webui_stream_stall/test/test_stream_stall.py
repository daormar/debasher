"""
Node tests of webui_stream_stall: the business logic of its nodes Acquire,
which reads a fake stream that can stall, and Tally, built without the
engine with the node harness, run with debasher_test.
"""

import time

import pytest

from debasher_runtime_testing import load_node


def acquire(tmp_path, monkeypatch, **opts):
    # The stream keeps its files in the output directory of the process
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(tmp_path))
    return load_node("Acquire", opts={"chunk-interval-ms": "1", **opts}, inputs=["reads"], outputs=["outreads"])


def tally():
    return load_node("Tally", inputs=["inreads"], outputs=["outdecisions"])


def wait_for_reads():
    # The stream gives one read every millisecond
    time.sleep(0.05)


def test_acquire_sends_on_the_reads_of_the_stream(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, **{"stall-after": "3"})
    wait_for_reads()

    reads = node.observe()

    assert [read["id"] for read in reads] == ["read-1-0", "read-1-1", "read-1-2"]
    assert node.sent("outreads") == reads


def test_acquire_sends_on_a_read_written_by_hand(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch)
    node.feed("reads", {"id": "by-hand", "channel": 7, "length": 300})

    assert node.sent("outreads") == [{"id": "by-hand", "channel": 7, "length": 300}]


def test_acquire_raises_when_the_stream_stalls(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch, **{"stall-after": "2", "stall-timeout-s": "0.05"})
    wait_for_reads()
    assert len(node.observe()) == 2
    time.sleep(0.1)

    with pytest.raises(RuntimeError, match="stream stalled"):
        node.observe()


def test_a_stall_file_stalls_the_stream_until_a_new_connection(tmp_path, monkeypatch):
    node = acquire(tmp_path, monkeypatch)
    (tmp_path / "stall").touch()
    wait_for_reads()
    assert node.observe() == []

    # The restart reconnects, as the relaunch of the node does
    node = node.restart()
    wait_for_reads()

    assert not (tmp_path / "stall").exists()
    assert node.observe()[0]["id"] == "read-2-0"


def test_tally_decides_on_each_read():
    node = tally()
    node.feed("inreads", {"id": "a", "channel": 1, "length": 300})
    node.feed("inreads", {"id": "b", "channel": 1, "length": 3000})

    assert node.sent("outdecisions") == [
        {"id": "a", "decision": "unblock", "channel_reads": 1},
        {"id": "b", "decision": "stop_receiving", "channel_reads": 2},
    ]


def test_a_restarted_tally_goes_on_counting():
    node = tally()
    node.feed("inreads", {"id": "a", "channel": 1, "length": 300})

    node = node.restart()
    node.feed("inreads", {"id": "b", "channel": 1, "length": 300})

    assert node.sent("outdecisions") == [{"id": "b", "decision": "unblock", "channel_reads": 2}]


def test_a_replay_of_the_reads_gives_the_same_tally():
    feeds = [("inreads", {"id": f"r{i}", "channel": i % 3, "length": 500 * i}) for i in range(6)]
    tally().check_replay(feeds, capture_after=2)
