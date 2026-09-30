"""
The notice of a node (set_notice, clear_notice; see "Notices" in the design
doc): one message in its notice file, which the next replaces, written at
once, or once at the end of a replay, and removed when an incarnation starts.
"""

import json
import logging
import os
import threading
import time

import pytest

import debasher_runtime_lib as lib
import debasher_runtime_fbp as fbp


@pytest.fixture(autouse=True)
def execdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path))
    monkeypatch.delenv("DEBASHER_PROCESS_TASK_IDX", raising=False)
    return tmp_path


class _Node(lib.FBPProcess):
    INPUT_PORTS = ["inf"]

    # What restore_node_state() and initialize_runtime() set, if anything.
    startup_notice = None

    def process_data(self, port_name, packet):
        if packet is None:
            self.clear_notice()
        else:
            self.set_notice(f"received {packet}")

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        if self.startup_notice is not None:
            self.set_notice(self.startup_notice, level="warning")


def _notice(execdir, name="notice"):
    path = execdir / name
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _count_writes(monkeypatch):
    """Counts the notice files renamed into place."""
    writes = []
    real_replace = os.replace

    def counting_replace(src, dst):
        if os.path.basename(dst).startswith("notice"):
            writes.append(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(fbp.os, "replace", counting_replace)
    return writes


def test_a_notice_is_written_with_its_level_and_when_it_was_set(execdir):
    before = time.time()
    _Node(opts={"inf": "/dev/null"}).set_notice("the configuration file is missing", level="warning")

    notice = _notice(execdir)
    assert notice["level"] == "warning"
    assert notice["text"] == "the configuration file is missing"
    assert notice["set_at"] >= before


def test_a_new_notice_replaces_the_previous_one_and_clearing_removes_it(execdir):
    node = _Node(opts={"inf": "/dev/null"})
    node.set_notice("first")
    node.set_notice("second")

    assert _notice(execdir)["text"] == "second"
    assert _notice(execdir)["level"] == "info"

    node.clear_notice()
    node.clear_notice()

    assert _notice(execdir) is None


def test_setting_the_notice_that_the_node_already_has_writes_nothing(execdir, monkeypatch):
    writes = _count_writes(monkeypatch)
    node = _Node(opts={"inf": "/dev/null"})

    node.set_notice("waiting")
    node.set_notice("waiting")
    node.set_notice("waiting", level="warning")

    assert len(writes) == 2


def test_a_level_that_is_not_info_or_warning_is_an_error_and_writes_nothing(execdir):
    with pytest.raises(ValueError, match="level"):
        _Node(opts={"inf": "/dev/null"}).set_notice("x", level="error")

    assert _notice(execdir) is None


def test_a_text_that_is_too_long_is_cut_with_a_warning_in_the_log(execdir, caplog):
    node = _Node(opts={"inf": "/dev/null"})

    with caplog.at_level(logging.WARNING):
        node.set_notice("x" * (node.NOTICE_MAX_CHARS + 5))

    assert _notice(execdir)["text"] == "x" * node.NOTICE_MAX_CHARS
    assert "NOTICE_MAX_CHARS" in caplog.text


def test_a_task_of_an_array_names_its_notice_file_with_its_index(execdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_TASK_IDX", "3")

    _Node(opts={"inf": "/dev/null"}).set_notice("task three")

    assert _notice(execdir, "notice_3")["text"] == "task three"
    assert _notice(execdir) is None


def test_the_file_holds_the_notice_set_last_by_any_thread(execdir):
    node = _Node(opts={"inf": "/dev/null"})

    def set_many(prefix):
        for i in range(200):
            node.set_notice(f"{prefix}{i}")

    threads = [threading.Thread(target=set_many, args=(p,)) for p in "ab"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert _notice(execdir)["text"] == node._notice["text"]


# --- the replay ---------------------------------------------------------------


def _log(node, *packets):
    node._open_input_log(0)
    for packet in packets:
        line = lib.encode_data(packet)
        node._on_arrival("inf", lib.decode_envelope(line), line)


def test_a_replay_writes_only_the_last_notice_asked_for_once_it_ends(execdir, monkeypatch):
    writes = _count_writes(monkeypatch)
    node = _Node(opts={"inf": "/dev/null"})
    _log(node, 1, 2, 3)

    node._replay_input_log(0)

    assert _notice(execdir)["text"] == "received 3"
    assert len(writes) == 1


def test_a_replay_that_ends_by_clearing_the_notice_leaves_none(execdir):
    node = _Node(opts={"inf": "/dev/null"})
    node.set_notice("set before the replay")
    _log(node, 1, None)

    node._replay_input_log(0)

    assert _notice(execdir) is None


def test_a_replay_that_asks_nothing_leaves_the_notice_as_it_was(execdir):
    class Quiet(_Node):
        def process_data(self, port_name, packet):
            pass

    node = Quiet(opts={"inf": "/dev/null"})
    node.set_notice("set in initialize_runtime")
    _log(node, 1)

    node._replay_input_log(0)

    assert _notice(execdir)["text"] == "set in initialize_runtime"


# --- each incarnation starts with none ---------------------------------------


def _run_until_started(node):
    thread = threading.Thread(target=node.run)
    thread.start()
    deadline = time.monotonic() + 5
    while not (node._brain_thread and node._brain_thread.is_alive()) and time.monotonic() < deadline:
        time.sleep(0.01)
    return thread


def _stop(node, thread):
    node._stop_requested.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


class _Portless(_Node):
    INPUT_PORTS = []


def test_an_incarnation_starts_without_the_notice_of_the_previous_one(execdir):
    (execdir / "notice").write_text(json.dumps({"level": "warning", "text": "old", "set_at": 0}))
    node = _Portless(opts={})

    thread = _run_until_started(node)
    try:
        assert _notice(execdir) is None
    finally:
        _stop(node, thread)


def test_what_the_startup_sets_is_there_once_the_node_runs(execdir):
    (execdir / "notice").write_text(json.dumps({"level": "info", "text": "old", "set_at": 0}))
    node = _Portless(opts={})
    node.startup_notice = "the configuration file is missing"

    thread = _run_until_started(node)
    try:
        assert _notice(execdir)["text"] == "the configuration file is missing"
        assert _notice(execdir)["level"] == "warning"
    finally:
        _stop(node, thread)
