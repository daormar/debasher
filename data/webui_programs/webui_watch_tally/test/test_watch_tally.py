"""
Node tests of webui_watch_tally: the business logic of its nodes Watch, a
DirectoryWatcher, and Tally, built without the engine with the node harness,
run with debasher_test.
"""

from debasher_runtime_testing import load_node


def watch(watchdir):
    return load_node("Watch", opts={"watchdir": str(watchdir)}, outputs=["outrequests"])


def tally():
    return load_node("Tally", inputs=["inrequests"], outputs=["outtally"])


def test_watch_requests_a_text_file_once_it_is_complete(tmp_path):
    node = watch(tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / ".b.txt").write_text("still being written")
    (tmp_path / "c.csv").write_text("not text")

    # A file is complete once it stays the same for two observations
    assert node.observe() == []
    assert node.observe() == [{"file": str(tmp_path / "a.txt")}]
    assert node.sent("outrequests") == [{"opts": {"-infile": str(tmp_path / "a.txt")}, "run": "a"}]


def test_a_restarted_watch_requests_no_file_twice(tmp_path):
    node = watch(tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    node.observe()
    node.observe()

    node = node.restart()
    node.observe()

    # Brought in again, as after a crash, and dropped
    assert node.observe() == [{"file": str(tmp_path / "a.txt")}]
    assert node.sent("outrequests") == []


def test_tally_counts_the_files_requested_so_far():
    node = tally()
    node.feed("inrequests", {"opts": {"-infile": "/in/a.txt"}, "run": "a"})
    node.feed("inrequests", {"opts": {"-infile": "/in/c.txt"}, "run": "c"})

    assert node.sent("outtally") == [{"run": "a", "seen": 1}, {"run": "c", "seen": 2}]


def test_a_restarted_tally_goes_on_counting():
    node = tally()
    node.feed("inrequests", {"opts": {"-infile": "/in/a.txt"}, "run": "a"})

    node = node.restart()
    node.feed("inrequests", {"opts": {"-infile": "/in/c.txt"}, "run": "c"})

    assert node.sent("outtally") == [{"run": "c", "seen": 2}]
