"""
Unit tests of DirectoryWatcher (engine/debasher_runtime_watcher.py), with no
engine: the directory it watches, when observe() takes a file for complete
and brings it in, and the request process_data sends, once per file.
"""

import os

import pytest

import debasher_runtime_lib as lib


class _Watch(lib.DirectoryWatcher):
    PATTERN = "*.bam"
    OUTPUT_PORTS = ["outrequests"]


@pytest.fixture
def watch_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "node"))
    monkeypatch.setenv("DEBASHER_PROCESS_MODULE_DIR", str(tmp_path / "program"))
    monkeypatch.delenv("DEBASHER_PROCESS_PORTS", raising=False)
    d = tmp_path / "incoming"
    d.mkdir()
    return d


def _node(watch_dir, cls=_Watch):
    node = cls(opts={"outrequests": "/dev/null", "watchdir": str(watch_dir)})
    node.brought_in = []
    node.inject = lambda payload: node.brought_in.append(payload["file"])
    return node


def _sent(node):
    return [lib.decode_envelope(line).payload for line in list(node._outbound_queues["outrequests"].queue)]


# --- the directory ------------------------------------------------------------


def test_the_option_names_the_directory_to_watch(watch_dir):
    assert _node(watch_dir)._watch_dir == str(watch_dir)


def test_a_relative_directory_is_resolved_against_the_module(watch_dir, tmp_path):
    class Relative(_Watch):
        WATCH_DIR = "incoming"

    node = Relative(opts={"outrequests": "/dev/null"})
    assert node._watch_dir == str(tmp_path / "program" / "incoming")


def test_a_watcher_needs_a_directory(watch_dir):
    with pytest.raises(ValueError, match="no directory to watch"):
        _Watch(opts={"outrequests": "/dev/null"})


# --- when a file is complete ----------------------------------------------------


def test_a_file_is_brought_in_once_it_has_not_changed_for_two_observations(watch_dir):
    node = _node(watch_dir)
    (watch_dir / "s17.bam").write_text("reads\n")

    node.observe()
    assert node.brought_in == []
    node.observe()
    assert node.brought_in == [str(watch_dir / "s17.bam")]
    node.observe()
    assert node.brought_in == [str(watch_dir / "s17.bam")]


def test_a_file_that_is_still_growing_is_not_complete(watch_dir):
    node = _node(watch_dir)
    bam = watch_dir / "s17.bam"
    bam.write_text("reads\n")
    node.observe()
    with open(bam, "a") as f:
        f.write("more reads\n")
    node.observe()
    assert node.brought_in == []
    node.observe()
    assert node.brought_in == [str(bam)]


def test_hidden_files_and_other_names_are_not_watched(watch_dir):
    node = _node(watch_dir)
    (watch_dir / ".s17.bam.part").write_text("reads\n")
    (watch_dir / "s17.bai").write_text("index\n")
    (watch_dir / "sub.bam").mkdir()
    for _ in range(3):
        node.observe()
    assert node.brought_in == []


def test_a_file_can_be_complete_in_another_way(watch_dir):
    class WithMarker(_Watch):
        def is_complete(self, path, stable_observations):
            return os.path.exists(path + ".done")

    node = _node(watch_dir, WithMarker)
    (watch_dir / "s17.bam").write_text("reads\n")
    node.observe()
    node.observe()
    assert node.brought_in == []
    (watch_dir / "s17.bam.done").write_text("")
    node.observe()
    assert node.brought_in == [str(watch_dir / "s17.bam")]


def test_a_missing_directory_is_waited_for(watch_dir):
    node = _node(watch_dir / "later")
    node.observe()
    assert node.brought_in == []


# --- the requests ---------------------------------------------------------------


def test_a_file_brought_in_is_requested_once(watch_dir):
    node = _node(watch_dir)
    path = str(watch_dir / "s17.bam")

    node._run_process_data("arrivals", {"file": path})
    node._run_process_data("arrivals", {"file": path})

    assert _sent(node) == [{"opts": {"-infile": path}, "run": "s17"}]
    assert node.capture_node_state() == {"requested": [path]}


def test_the_requested_files_survive_a_restore(watch_dir):
    node = _node(watch_dir)
    path = str(watch_dir / "s17.bam")
    node.restore_node_state({"requested": [path]})

    node._run_process_data("arrivals", {"file": path})

    assert _sent(node) == []


def test_a_module_decides_what_request_a_file_makes(watch_dir):
    class Custom(_Watch):
        def request_for(self, path):
            return {"opts": {"-bam": path, "-outf": "counts.txt"}, "run": "sample/" + os.path.basename(path)}

    node = _node(watch_dir, Custom)
    path = str(watch_dir / "s17.bam")
    node._run_process_data("arrivals", {"file": path})

    assert _sent(node) == [{"opts": {"-bam": path, "-outf": "counts.txt"}, "run": "sample/s17.bam"}]
