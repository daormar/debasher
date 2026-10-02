import os
import stat
import sys
import traceback

import pytest

import debasher_runtime_testing as testing

# The heredoc of a node as script generation writes it: the line that runs
# the node comes last, with no condition
ACCUMULATE = '''from debasher_runtime_lib import FBPProcess


class Accumulate(FBPProcess):
    def __init__(self):
        super().__init__()
        self.total = 0

    def process_data(self, port_name, packet):
        self.total += packet
        self.send_data("outsum", self.total)

    def capture_node_state(self):
        return {"total": self.total}

    def restore_node_state(self, node_state):
        self.total = node_state["total"]

    def initialize_runtime(self):
        pass


Accumulate().run()
'''


def _node(source, process="Accumulate", opts=None, inputs=("numbers",), outputs=("outsum",)):
    node_class = testing._node_class(process, source)
    return testing.NodeUnderTest(node_class, opts or {}, list(inputs), list(outputs))


def test_a_node_run_by_a_bare_run_line_is_built_without_starting():
    node = _node(ACCUMULATE)
    node.feed("numbers", 3)
    node.feed("numbers", 4)
    assert node.sent("outsum") == [3, 7]
    assert node.node.total == 7


def test_a_node_run_under_the_main_guard_is_built_without_starting():
    source = ACCUMULATE.replace("Accumulate().run()", 'if __name__ == "__main__":\n    Accumulate().run()')
    node = _node(source)
    node.feed("numbers", 5)
    assert node.sent("outsum") == [5]


def test_a_node_started_in_another_form_is_refused():
    source = ACCUMULATE.replace("Accumulate().run()", "node = Accumulate()\nnode.run()")
    with pytest.raises(ValueError, match="form the harness does not recognize"):
        testing._node_class("Accumulate", source)


def test_a_call_to_run_with_arguments_in_the_preamble_is_not_refused():
    source = "import subprocess\n\nsubprocess.run([\"true\"])\n\n" + ACCUMULATE
    node = _node(source)
    node.feed("numbers", 1)
    assert node.sent("outsum") == [1]


@pytest.mark.parametrize("kind", ["Supervisor", "ProgramLauncher"])
def test_a_node_of_another_kind_is_refused(kind):
    source = f"from debasher_runtime_lib import {kind}\n\n\nclass Other({kind}):\n    pass\n\n\nOther().run()\n"
    with pytest.raises(ValueError, match=f"is a {kind}"):
        testing._node_class("Other", source)


def test_the_methods_see_the_preamble_and_a_dataclass_of_it_works():
    source = '''import dataclasses

from debasher_runtime_lib import FBPProcess

FACTOR = 10


@dataclasses.dataclass
class Scaled:
    value: int


def scale(value):
    return Scaled(value * FACTOR)


class Scale(FBPProcess):
    def process_data(self, port_name, packet):
        self.send_data("out", dataclasses.asdict(scale(packet)))

    def capture_node_state(self):
        return {}

    def restore_node_state(self, node_state):
        pass

    def initialize_runtime(self):
        pass


Scale().run()
'''
    node = _node(source, process="Scale", inputs=["inp"], outputs=["out"])
    node.feed("inp", 2)
    assert node.sent("out") == [{"value": 20}]


def test_a_packet_arrives_as_through_a_fifo():
    source = ACCUMULATE.replace("self.total += packet", "self.total = packet").replace(
        "self.send_data(\"outsum\", self.total)", "self.send_data(\"outsum\", type(packet).__name__)"
    )
    node = _node(source)
    node.feed("numbers", (1, 2))
    assert node.sent("outsum") == ["list"]


def test_feeding_a_port_that_is_not_an_input_is_refused():
    node = _node(ACCUMULATE)
    with pytest.raises(ValueError, match="neither an input port"):
        node.feed("other", 1)


def test_sending_on_a_port_that_is_not_an_output_fails():
    node = _node(ACCUMULATE, outputs=())
    with pytest.raises(Exception):
        node.feed("numbers", 1)


def test_what_was_sent_before_process_data_raised_is_kept():
    source = ACCUMULATE.replace(
        "self.send_data(\"outsum\", self.total)",
        "self.send_data(\"outsum\", self.total)\n        raise ValueError(\"after sending\")",
    )
    node = _node(source)
    with pytest.raises(ValueError, match="after sending"):
        node.feed("numbers", 1)
    assert node.sent("outsum") == [1]


def test_a_traceback_shows_the_line_of_the_heredoc():
    source = ACCUMULATE.replace("self.total += packet", "self.total += packet  # adds the packet")
    node = _node(source)
    with pytest.raises(TypeError) as excinfo:
        node.feed("numbers", "not a number")
    text = "".join(traceback.format_exception(excinfo.value))
    assert "<heredoc of Accumulate>" in text
    assert "self.total += packet  # adds the packet" in text


def test_the_options_reach_the_node_with_flags():
    source = ACCUMULATE.replace(
        "    def capture_node_state", "    FLAGS = (\"verbose\",)\n\n    def capture_node_state"
    )
    node = _node(source, opts={"-threshold": 3, "verbose": True, "absent": False})
    assert node.node.opts["threshold"] == "3"
    assert node.node.opts["verbose"] is True
    assert "absent" not in node.node.opts
    # The port options are there, with placeholders
    assert "numbers" in node.node.opts and "outsum" in node.node.opts


def test_restart_brings_the_node_state_back():
    node = _node(ACCUMULATE)
    node.feed("numbers", 3)
    restarted = node.restart()
    assert restarted.sent("outsum") == []
    restarted.feed("numbers", 4)
    assert restarted.sent("outsum") == [7]


def test_restart_fails_when_the_node_state_does_not_come_back():
    source = ACCUMULATE.replace('self.total = node_state["total"]', "pass")
    node = _node(source)
    node.feed("numbers", 3)
    with pytest.raises(AssertionError, match="restored the node state"):
        node.restart()


def test_sleep_does_not_wait():
    source = ACCUMULATE.replace("self.total += packet", "self.sleep(3600)\n        self.total += packet")
    node = _node(source)
    node.feed("numbers", 1)
    assert node.sent("outsum") == [1]


def test_many_messages_never_fill_the_outbound_backlog():
    source = ACCUMULATE.replace("    def capture_node_state", "    OUT_BACKLOG_FAIL_BYTES = 200\n\n    def capture_node_state")
    node = _node(source)
    for _ in range(100):
        node.feed("numbers", 1)
    assert node.sent("outsum")[-1] == 100


def test_the_environment_of_the_test_is_left_as_it_was(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_TASK_IDX", "4")
    monkeypatch.delenv("DEBASHER_PROCESS_PORTS", raising=False)
    argv = list(sys.argv)
    node = _node(ACCUMULATE)
    node.feed("numbers", 1)
    assert os.environ["DEBASHER_PROCESS_TASK_IDX"] == "4"
    assert "DEBASHER_PROCESS_PORTS" not in os.environ
    assert sys.argv == argv


def test_a_notice_goes_into_a_temporary_execdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = ACCUMULATE.replace("self.total += packet", "self.set_notice(\"busy\")\n        self.total += packet")
    node = _node(source)
    node.feed("numbers", 1)
    assert os.path.exists(os.path.join(node._tmpdir.name, "notice"))
    assert list(tmp_path.iterdir()) == []


def _fake_libexec(tmp_path, source):
    """A libexec directory whose debasher_get_node_source prints `source`,
    and counts its calls."""
    libexec = tmp_path / "libexec"
    libexec.mkdir()
    (tmp_path / "source.py").write_text(source)
    tool = libexec / "debasher_get_node_source"
    tool.write_text(f'#!/bin/sh\necho call >> "{tmp_path}/calls"\ncat "{tmp_path}/source.py"\n')
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return libexec


def test_load_node_builds_the_node_of_the_program_and_initializes_it(tmp_path, monkeypatch):
    source = ACCUMULATE.replace("    def initialize_runtime(self):\n        pass", "    def initialize_runtime(self):\n        self.ready = True")
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", str(_fake_libexec(tmp_path, source)))
    monkeypatch.setenv("DEBASHER_TEST_PFILE", str(tmp_path / "prg.sh"))
    monkeypatch.setattr(testing, "_source_cache", {})
    node = testing.load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
    assert node.node.ready is True
    node.feed("numbers", 2)
    assert node.sent("outsum") == [2]
    # The code of a process is taken once
    testing.load_node("Accumulate", inputs=["numbers"], outputs=["outsum"])
    assert (tmp_path / "calls").read_text().count("call") == 1


def test_load_node_needs_the_program_file(monkeypatch):
    monkeypatch.delenv("DEBASHER_TEST_PFILE", raising=False)
    with pytest.raises(RuntimeError, match="DEBASHER_TEST_PFILE is not set"):
        testing.load_node("Accumulate")


def test_load_node_reports_a_process_without_code(tmp_path, monkeypatch):
    libexec = tmp_path / "libexec"
    libexec.mkdir()
    tool = libexec / "debasher_get_node_source"
    tool.write_text("#!/bin/sh\necho 'Error: process X has no Python heredoc' >&2\nexit 1\n")
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", str(libexec))
    monkeypatch.setenv("DEBASHER_TEST_PFILE", str(tmp_path / "prg.sh"))
    monkeypatch.setattr(testing, "_source_cache", {})
    with pytest.raises(RuntimeError, match="has no Python heredoc"):
        testing.load_node("X")


# --- observe ---------------------------------------------------------------------

# A node that observes a list of its own, standing for the outside world
OBSERVER = """from debasher_runtime_lib import FBPProcess

SEEN = []


class Observer(FBPProcess):
    OBSERVE_PORT = "seen"

    def __init__(self):
        super().__init__()
        self.count = 0

    def observe(self):
        while SEEN:
            self.inject({"item": SEEN.pop(0)})

    def process_data(self, port_name, packet):
        self.count += 1
        self.send_data("out", f"{port_name}:{packet['item']}:{self.count}")

    def capture_node_state(self):
        return {"count": self.count}

    def restore_node_state(self, node_state):
        self.count = node_state["count"]

    def initialize_runtime(self):
        pass


Observer().run()
"""


def _observer():
    node = _node(OBSERVER, process="Observer", inputs=(), outputs=("out",))
    world = sys.modules[type(node.node).__module__].SEEN
    return node, world


def test_observe_brings_in_what_it_sees_and_processes_it_in_order():
    node, world = _observer()
    world.extend(["a", "b"])

    assert node.observe() == [{"item": "a"}, {"item": "b"}]
    assert node.sent("out") == ["seen:a:1", "seen:b:2"]
    assert node.observe() == []


def test_the_observe_port_can_be_fed_directly():
    node, _ = _observer()

    node.feed("seen", {"item": "x"})

    assert node.sent("out") == ["seen:x:1"]


def test_observe_needs_a_node_that_defines_it():
    with pytest.raises(ValueError, match="does not define observe"):
        _node(ACCUMULATE).observe()


def test_inject_keeps_its_own_checks():
    source = OBSERVER.replace('    OBSERVE_PORT = "seen"\n', "")
    node = _node(source, process="Observer", inputs=(), outputs=("out",))
    sys.modules[type(node.node).__module__].SEEN.append("a")

    with pytest.raises(RuntimeError, match="needs OBSERVE_PORT"):
        node.observe()


WATCHER = """from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    PATTERN = "*.txt"


Watch().run()
"""


def test_a_directory_watcher_requests_a_file_once_it_is_complete(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    node = _node(WATCHER, process="Watch", opts={"watchdir": str(inbox)}, inputs=(), outputs=("outrequests",))
    (inbox / "a.txt").write_text("data")
    (inbox / ".b.txt").write_text("still being written")
    (inbox / "c.csv").write_text("not matched")

    # Complete once its size and time stay the same for two observations
    assert node.observe() == []
    assert node.observe() == [{"file": str(inbox / "a.txt")}]
    assert node.sent("outrequests") == [{"opts": {"-infile": str(inbox / "a.txt")}, "run": "a"}]


def test_a_restarted_directory_watcher_requests_nothing_twice(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    node = _node(WATCHER, process="Watch", opts={"watchdir": str(inbox)}, inputs=(), outputs=("outrequests",))
    (inbox / "a.txt").write_text("data")
    node.observe()
    node.observe()

    restarted = node.restart()
    restarted.observe()

    # Brought in again, as after a crash, and dropped by process_data
    assert restarted.observe() == [{"file": str(inbox / "a.txt")}]
    assert restarted.sent("outrequests") == []


def test_a_relative_directory_is_the_one_beside_the_program(tmp_path, monkeypatch):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "a.txt").write_text("data")
    source = WATCHER.replace('PATTERN = "*.txt"', 'PATTERN = "*.txt"\n    WATCH_DIR = "inbox"')
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", str(_fake_libexec(tmp_path, source)))
    monkeypatch.setenv("DEBASHER_TEST_PFILE", str(tmp_path / "prg.sh"))
    monkeypatch.setattr(testing, "_source_cache", {})
    monkeypatch.delenv("DEBASHER_PROCESS_MODULE_DIR", raising=False)

    node = testing.load_node("Watch", outputs=["outrequests"])
    node.observe()

    assert node.observe() == [{"file": str(tmp_path / "inbox" / "a.txt")}]
    assert "DEBASHER_PROCESS_MODULE_DIR" not in os.environ
