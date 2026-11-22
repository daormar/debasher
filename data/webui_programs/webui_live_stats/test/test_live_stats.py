"""
Node tests of webui_live_stats, a non-durable program: the business logic of
Acquire, which reads a fake stream, and of Stats, which keeps live statistics
in memory, built without the engine with the node harness, run with
debasher_test. There is no restart or replay test: the program is
non-durable, so nothing is restored or replayed.
"""

import json
import time

from debasher_runtime_testing import load_node


def acquire(**opts):
    return load_node("Acquire", opts={"interval-ms": "1", **opts}, inputs=["readings"], outputs=["outreadings"])


def stats(tmp_path, monkeypatch, **opts):
    # The summary file goes into the output directory of the process
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(tmp_path))
    return load_node("Stats", opts=opts, inputs=["inreadings"], outputs=["outstats"])


def test_acquire_sends_the_readings_of_the_stream_with_their_source():
    node = acquire()
    # The stream gives one reading every millisecond
    time.sleep(0.05)

    readings = node.observe()

    assert readings[0] == {"source": "stream", "t": 0, "value": 0.0}
    assert [reading["t"] for reading in readings] == list(range(len(readings)))
    assert node.sent("outreadings") == readings


def test_acquire_gives_a_reading_written_by_hand_its_source():
    node = acquire()
    node.feed("readings", {"value": 5})
    node.feed("readings", {"source": "probe", "value": 7})

    assert node.sent("outreadings") == [{"source": "hand", "value": 5}, {"source": "probe", "value": 7}]


def test_stats_keeps_the_count_and_the_mean_of_each_source(tmp_path, monkeypatch):
    node = stats(tmp_path, monkeypatch)
    node.feed("inreadings", {"source": "stream", "t": 0, "value": 2.0})
    node.feed("inreadings", {"source": "stream", "t": 1, "value": 4.0})
    node.feed("inreadings", {"source": "hand", "value": 5})

    assert node.sent("outstats") == [
        {"source": "stream", "value": 2.0, "count": 1, "mean": 2.0},
        {"source": "stream", "value": 4.0, "count": 2, "mean": 3.0},
        {"source": "hand", "value": 5, "count": 1, "mean": 5.0},
    ]


def test_stats_drops_a_reading_with_no_numeric_value(tmp_path, monkeypatch):
    node = stats(tmp_path, monkeypatch)
    node.feed("inreadings", {"source": "hand", "value": "high"})
    node.feed("inreadings", "not a reading")

    assert node.sent("outstats") == []


def test_stats_summarizes_the_stream_every_so_many_readings(tmp_path, monkeypatch):
    node = stats(tmp_path, monkeypatch, **{"window-s": "60"})
    for t in range(node.node.NOTICE_EVERY):
        node.feed("inreadings", {"source": "stream", "t": t, "value": float(t % 10)})

    lines = (tmp_path / "summary.jsonl").read_text().splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["count"] == node.node.NOTICE_EVERY
    assert summary["window_count"] == node.node.NOTICE_EVERY
    assert summary["window_mean"] == 4.5
    assert summary["rate_per_s"] == round(node.node.NOTICE_EVERY / 60, 3)


def test_the_window_forgets_the_readings_older_than_its_span(tmp_path, monkeypatch):
    node = stats(tmp_path, monkeypatch, **{"window-s": "0.01"})
    node.feed("inreadings", {"source": "stream", "t": 0, "value": 100.0})
    time.sleep(0.05)
    node.feed("inreadings", {"source": "stream", "t": 1, "value": 2.0})

    window_count, _, window_mean = node.node._window_stats("stream", time.monotonic())
    assert (window_count, window_mean) == (1, 2.0)
    # The count and the mean of every reading since the start are kept
    assert node.sent("outstats")[-1] == {"source": "stream", "value": 2.0, "count": 2, "mean": 51.0}
