"""
Unit tests of ProgramLauncher (engine/debasher_runtime_launcher.py), with no
engine: requests registered by process_data, the ownership of a run
directory, the launcher thread's pass over the registered batch runs (run
here by hand, with a fake debasher_exec), and the end of a batch run
reported through the node's own port and announced once.
"""

import json
import os
import signal
import stat
import subprocess
import time

import pytest

import debasher_runtime_lib as lib


class _Launcher(lib.ProgramLauncher):
    PFILE = "pipeline.sh"


class _NotifyingLauncher(_Launcher):
    INPUT_PORTS = ["requests"]
    OUTPUT_PORTS = ["outdone"]


# A stand-in for debasher_exec: records its launch and its arguments in the
# run directory, takes FAKE_SLEEP seconds, leaves FAKE_STATUS (0 by default)
# as what debasher_status will say of the program, and exits with FAKE_EXIT.
_FAKE_DEBASHER_EXEC = """#!/bin/bash
args="$*"
outdir=""
while [ $# -gt 0 ]; do
    if [ "$1" = "--outdir" ]; then outdir=$2; fi
    shift
done
echo "$$" >> "${outdir}/fake_launches"
echo "${args}" > "${outdir}/fake_args"
sleep "${FAKE_SLEEP:-0}"
echo "${FAKE_STATUS:-0}" > "${outdir}/fake_status"
exit "${FAKE_EXIT:-0}"
"""

# A stand-in for debasher_exec_process, run from the run directory: records
# its launch and its arguments there, takes FAKE_SLEEP seconds and exits with
# FAKE_EXIT.
_FAKE_DEBASHER_EXEC_PROCESS = """#!/bin/bash
echo "$$" >> fake_launches
echo "$*" > fake_args
sleep "${FAKE_SLEEP:-0}"
exit "${FAKE_EXIT:-0}"
"""

# A stand-in for debasher_status: exits with what the run directory's
# fake_status says, or 1, as for a directory with no program yet.
_FAKE_DEBASHER_STATUS = """#!/bin/bash
[ -f "$2/fake_status" ] || exit 1
exit "$(cat "$2/fake_status")"
"""


@pytest.fixture
def outdir(tmp_path, monkeypatch):
    d = tmp_path / "out" / "launch"
    d.mkdir(parents=True)
    monkeypatch.setenv("DEBASHER_PROCESS_OUTDIR", str(d))
    monkeypatch.setenv("DEBASHER_PROCESS_EXECDIR", str(tmp_path / "out" / "__exec__" / "launch"))
    monkeypatch.delenv("DEBASHER_PROCESS_TASK_IDX", raising=False)
    monkeypatch.delenv("DEBASHER_PROCESS_PORTS", raising=False)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, text in (
        ("debasher_exec", _FAKE_DEBASHER_EXEC),
        ("debasher_exec_process", _FAKE_DEBASHER_EXEC_PROCESS),
        ("debasher_status", _FAKE_DEBASHER_STATUS),
    ):
        fake = bindir / name
        fake.write_text(text)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("DEBASHER_BINDIR", str(bindir))
    # The directory of the module that declares the node, where the general
    # program lives too
    module_dir = tmp_path / "program"
    module_dir.mkdir()
    (module_dir / "pipeline.sh").write_text("# a general program\n")
    monkeypatch.setenv("DEBASHER_PROCESS_MODULE_DIR", str(module_dir))
    return d


@pytest.fixture(autouse=True)
def _node_log(caplog):
    """The node logger does not propagate: this hands what it logs to
    caplog."""
    import logging

    logger = logging.getLogger(_Launcher.__name__)
    logger.addHandler(caplog.handler)
    yield
    logger.removeHandler(caplog.handler)


def _node(cls=_Launcher, opts=None):
    node = cls(opts=opts or {"requests": "/dev/null"})
    node.STATUS_CHECK_INTERVAL_SECS = 0
    node.initialize_runtime()
    return node


def _request(node, pos, packet, port="requests"):
    node._current_pos = pos
    node._run_process_data(port, packet)


def _launch_record(outdir, run):
    with open(outdir / run / "launch.json") as f:
        return json.load(f)


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# --- the life of a launcher node -------------------------------------------


def test_the_life_id_is_created_once_and_kept(outdir):
    first = _node()._life_id
    assert first
    assert _node()._life_id == first


def test_a_new_life_begins_once_the_output_directory_is_emptied(outdir):
    first = _node()._life_id
    os.remove(outdir / ".launcher" / "life_id")
    assert _node()._life_id != first


def test_a_launcher_node_needs_its_program():
    with pytest.raises(ValueError, match="PFILE"):
        lib.ProgramLauncher(opts={"requests": "/dev/null"})


def test_a_relative_program_is_found_in_the_directory_of_the_module(outdir, tmp_path):
    assert _node()._pfile == str((tmp_path / "program" / "pipeline.sh").resolve())


def test_an_absolute_program_is_accepted_with_a_warning(outdir, tmp_path, caplog):
    class Absolute(lib.ProgramLauncher):
        PFILE = str(tmp_path / "program" / "pipeline.sh")

    import logging

    logger = logging.getLogger(Absolute.__name__)
    logger.addHandler(caplog.handler)
    try:
        node = Absolute(opts={"requests": "/dev/null"})
    finally:
        logger.removeHandler(caplog.handler)
    assert node._pfile == str((tmp_path / "program" / "pipeline.sh").resolve())
    assert "not portable across machines" in caplog.text


def test_a_program_that_is_not_there_stops_the_node(outdir):
    class Lost(lib.ProgramLauncher):
        PFILE = "nowhere.sh"

    with pytest.raises(ValueError, match="is not a file"):
        Lost(opts={"requests": "/dev/null"})


# --- registering requests ----------------------------------------------------


def test_a_request_registers_its_batch_run(outdir):
    node = _node()
    _request(node, 3, {"opts": {"-bam": "/data/s17.bam"}, "run": "s17"})

    assert _launch_record(outdir, "s17") == {
        "life_id": node._life_id,
        "pos": 3,
        "opts": {"-bam": "/data/s17.bam"},
    }
    with open(outdir / ".launcher" / "registrations" / "3.json") as f:
        assert json.load(f) == {"run": "s17"}


def test_a_request_without_run_is_named_after_its_position(outdir):
    node = _node()
    _request(node, 7, {"opts": {}})
    assert _launch_record(outdir, "7")["pos"] == 7


def test_a_nested_run_name_makes_nested_directories(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "s17/v2"})
    assert _launch_record(outdir, "s17/v2")["pos"] == 1


def test_a_replayed_request_registers_the_same_again(outdir):
    node = _node()
    _request(node, 3, {"opts": {"-a": "x"}, "run": "s17"})
    replayed = _node()
    _request(replayed, 3, {"opts": {"-a": "x"}, "run": "s17"})
    assert _launch_record(outdir, "s17")["pos"] == 3


def test_a_run_directory_belongs_to_the_request_that_registered_it(outdir, caplog):
    node = _node()
    _request(node, 3, {"opts": {"-a": "x"}, "run": "s17"})
    _request(node, 4, {"opts": {"-a": "y"}, "run": "s17"})

    assert _launch_record(outdir, "s17")["opts"] == {"-a": "x"}
    assert not (outdir / ".launcher" / "registrations" / "4.json").exists()
    assert "belongs to another request" in caplog.text


def test_a_request_of_a_new_life_does_not_take_a_directory_of_the_old_one(outdir, caplog):
    old = _node()
    _request(old, 3, {"opts": {}, "run": "s17"})
    os.remove(outdir / ".launcher" / "life_id")
    new = _node()
    _request(new, 3, {"opts": {}, "run": "s17"})

    assert _launch_record(outdir, "s17")["life_id"] == old._life_id
    assert "belongs to another request" in caplog.text


@pytest.mark.parametrize(
    "packet, reason",
    [
        ("s17", "JSON object"),
        ({"opts": ["-a", "x"]}, "opts"),
        ({"opts": {"a": "x"}}, "dash"),
        ({"opts": {"-a": 3}}, "string"),
        ({"opts": {}, "run": "/abs/s17"}, "relative"),
        ({"opts": {}, "run": "s17/../x"}, "relative"),
        ({"opts": {}, "run": ".hidden"}, "dot"),
        ({"opts": {}, "run": ""}, "non-empty"),
    ],
)
def test_a_malformed_request_is_dropped(outdir, caplog, packet, reason):
    node = _node()
    _request(node, 5, packet)
    assert reason in caplog.text
    assert os.listdir(outdir / ".launcher" / "registrations") == []


# --- the launcher thread's pass over the batch runs -------------------------


def _launches(outdir, run):
    path = outdir / run / "fake_launches"
    return path.read_text().split() if path.exists() else []


def _check_until_ended(node, outdir, runs, timeout=10.0):
    def ended():
        node._check_runs()
        return all((outdir / run / "exit_code").exists() for run in runs)

    assert _wait_until(ended, timeout)


def test_the_batch_runs_are_launched_in_order_up_to_the_limit(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "1")
    node = _node()
    for pos, run in ((1, "a"), (2, "b"), (3, "c")):
        _request(node, pos, {"opts": {}, "run": run})
    node.MAX_CONCURRENT_RUNS = 2

    node._check_runs()

    assert _wait_until(lambda: _launches(outdir, "a") and _launches(outdir, "b"))
    assert _launches(outdir, "c") == []
    _check_until_ended(node, outdir, "abc")
    assert [len(_launches(outdir, run)) for run in "abc"] == [1, 1, 1]


def test_a_batch_run_that_ended_keeps_its_exit_code_and_is_not_launched_again(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_EXIT", "3")
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")
    node._check_runs()

    assert (outdir / "a" / "exit_code").read_text().strip() == "3"
    assert len(_launches(outdir, "a")) == 1


def test_a_program_that_fails_after_debasher_exec_ended_well_ends_failed(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_STATUS", "3")
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "3"


def test_a_batch_run_goes_on_after_debasher_exec_ends_until_its_program_does(outdir, monkeypatch):
    # As with SLURM, where debasher_exec only submits the jobs.
    monkeypatch.setenv("FAKE_STATUS", "2")
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})

    def submitted():
        node._check_runs()
        return (outdir / "a" / "submitted").exists()

    assert _wait_until(submitted)

    node._check_runs()
    assert not (outdir / "a" / "exit_code").exists()

    (outdir / "a" / "fake_status").write_text("0\n")
    _check_until_ended(node, outdir, "a")
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"
    assert len(_launches(outdir, "a")) == 1


def test_the_scheduler_of_the_batch_runs_reaches_debasher_exec(outdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; batch_sched=SLURM")
    node = _node()
    assert node.BATCH_SCHED == "SLURM"
    _request(node, 1, {"opts": {"-a": "x"}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    assert "--sched SLURM" in (outdir / "a" / "fake_args").read_text()
    assert "-a x" in (outdir / "a" / "fake_args").read_text()


def test_without_a_scheduler_the_batch_runs_use_the_builtin_one(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    assert "--sched BUILTIN" in (outdir / "a" / "fake_args").read_text()


def test_the_options_of_the_request_reach_debasher_exec(outdir, monkeypatch):
    node = _node()
    _request(node, 1, {"opts": {"-bam": "/data/s17.bam"}, "run": "a"})
    calls = []
    monkeypatch.setattr(lib.ProgramLauncher, "_launch", lambda self, run_dir: calls.append(run_dir))

    node._check_runs()

    assert calls == [str(outdir / "a")]


def test_a_batch_run_whose_debasher_exec_is_gone_is_launched_again(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    dead = subprocess.Popen(["true"])
    dead.wait()
    (outdir / "a" / "launcher.pid").write_text(f"{dead.pid}\n")

    relaunched = _node()
    _check_until_ended(relaunched, outdir, "a")

    assert len(_launches(outdir, "a")) == 1


def _orphan(outdir, run, status=None):
    """A batch run whose debasher_exec is gone before it ended, as a crash of
    the node leaves it, with what debasher_status says of it."""
    dead = subprocess.Popen(["true"])
    dead.wait()
    (outdir / run / "launcher.pid").write_text(f"{dead.pid}\n")
    if status is not None:
        (outdir / run / "fake_status").write_text(f"{status}\n")


def test_a_batch_run_with_something_still_in_progress_is_left_to_end(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _orphan(outdir, "a", status=2)

    node._check_runs()

    assert _launches(outdir, "a") == []
    assert not (outdir / "a" / "exit_code").exists()


def test_a_batch_run_that_finished_without_its_debasher_exec_is_not_launched_again(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _orphan(outdir, "a", status=0)

    node._check_runs()

    assert _launches(outdir, "a") == []
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


# --- the end of a batch run --------------------------------------------------


def test_the_end_of_a_batch_run_is_brought_in_once_and_then_marked(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})
    brought_in = []

    def inject(payload):
        # The run directory is marked only once inject() has returned.
        assert not (outdir / "a" / "notified").exists()
        brought_in.append(payload)

    node.inject = inject
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")
    node._check_runs()

    assert brought_in == [{"run": "a", "exit_code": 0}]
    assert (outdir / "a" / "notified").exists()


def test_a_node_without_the_port_reports_nothing(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    node._check_runs()
    assert not (outdir / "a" / "notified").exists()


def _sent(node, tag):
    return [lib.decode_envelope(line).payload for line in list(node._outbound_queues[tag].queue)]


def test_an_end_is_announced_once_even_if_reported_twice(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})

    _request(node, 5, {"run": "a", "exit_code": 0}, port="runs_done")
    _request(node, 6, {"run": "a", "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == [{"run": "a", "status": "finished", "exit_code": 0}]
    assert node.capture_node_state() == {"announced": ["a"]}


def test_the_end_of_a_failed_batch_run_is_announced_as_failed(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})

    _request(node, 5, {"run": "a", "exit_code": 3}, port="runs_done")

    assert _sent(node, "outdone") == [{"run": "a", "status": "failed", "exit_code": 3}]


def test_the_announced_runs_survive_a_restore(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})
    node.restore_node_state({"announced": ["a"]})

    _request(node, 5, {"run": "a", "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == []


# --- the computational specifications ----------------------------------------


def test_the_computational_specs_set_the_batch_runs_at_a_time(outdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; mem=32; max_concurrent_runs=4")
    node = _node()
    assert node.MAX_CONCURRENT_RUNS == 4


# --- a single process instead of a program -----------------------------------


class _ProcessLauncher(_Launcher):
    PROCESS = "align"


def test_a_process_launcher_runs_the_process_alone_from_the_run_directory(outdir, tmp_path):
    node = _node(_ProcessLauncher)
    _request(node, 1, {"opts": {"-bam": "/data/s17.bam", "-outf": "out.txt"}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    pfile = (tmp_path / "program" / "pipeline.sh").resolve()
    assert (outdir / "a" / "fake_args").read_text().split() == [
        str(pfile), "align", "--", "-bam", "/data/s17.bam", "-outf", "out.txt"
    ]
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


def test_a_process_writes_its_own_exit_code(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_EXIT", "4")
    node = _node(_ProcessLauncher)
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "4"


def test_the_exit_code_of_a_process_outlives_a_crash_of_its_launcher(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "1")
    node = _node(_ProcessLauncher)
    _request(node, 1, {"opts": {}, "run": "a"})
    node._check_runs()
    assert _wait_until(lambda: _launches(outdir, "a"))

    # A new incarnation, which did not launch it: the process is still
    # running, and then writes its exit code on its own.
    relaunched = _node(_ProcessLauncher)
    relaunched._check_runs()
    assert not (outdir / "a" / "exit_code").exists()
    _check_until_ended(relaunched, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "0"
    assert len(_launches(outdir, "a")) == 1


def test_a_process_stopped_before_it_ended_is_launched_again(outdir):
    node = _node(_ProcessLauncher)
    _request(node, 1, {"opts": {}, "run": "a"})
    _orphan(outdir, "a")

    _check_until_ended(node, outdir, "a")

    assert len(_launches(outdir, "a")) == 1
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


def test_process_is_the_name_of_a_process(outdir):
    class Nameless(_Launcher):
        PROCESS = ""

    with pytest.raises(ValueError, match="PROCESS"):
        Nameless(opts={"requests": "/dev/null"})
