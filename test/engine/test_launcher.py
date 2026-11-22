"""
Unit tests of ProgramLauncher (engine/debasher_runtime_launcher.py), with no
engine: requests registered by process_data, the ownership of a run
directory, the launcher thread's pass over the registered batch runs (run
here by hand, with a fake debasher_exec), and the end of a batch run
reported through the node's own port and announced once.
"""

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

import debasher_runtime_launcher as launcher_mod
import debasher_runtime_lib as lib


# The sources of the engine, in the repository
ENGINE_SOURCE_DIR = Path(__file__).resolve().parents[2] / "engine"


class _Launcher(lib.ProgramLauncher):
    pass


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

# A stand-in for debasher_resolve_pfile: looks for the program in the
# current directory and then in the directories of DEBASHER_MOD_DIR, as the
# engine's search for a module does, and prints its absolute path.
_FAKE_DEBASHER_RESOLVE_PFILE = """#!/bin/bash
IFS=: read -r -a dirs <<< "${DEBASHER_MOD_DIR}"
for dir in . "${dirs[@]}"; do
    if [ -f "${dir}/$1" ]; then
        realpath "${dir}/$1"
        exit 0
    fi
done
echo "File not found: $1" >&2
exit 1
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
    libexecdir = tmp_path / "libexec"
    libexecdir.mkdir()
    fake = libexecdir / "debasher_resolve_pfile"
    fake.write_text(_FAKE_DEBASHER_RESOLVE_PFILE)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("DEBASHER_LIBEXECDIR", str(libexecdir))
    monkeypatch.delenv("DEBASHER_MOD_DIR", raising=False)
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


# The options of a node of the tests, to which those of each test are added
_OPTS = {"requests": "/dev/null", "pfile": "pipeline.sh"}


def _node(cls=_Launcher, opts=None):
    node = cls(opts={**_OPTS, **(opts or {})})
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
    with pytest.raises(ValueError, match="the process has no option -pfile"):
        lib.ProgramLauncher(opts={"requests": "/dev/null"})


def test_a_relative_program_is_found_in_the_directory_of_the_module(outdir, tmp_path):
    node = _node()
    assert node._pfile == str((tmp_path / "program" / "pipeline.sh").resolve())
    assert node._process is None


def test_a_relative_program_is_found_through_debasher_mod_dir(outdir, tmp_path, monkeypatch):
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "shared.sh").write_text("# a general program of another module\n")
    monkeypatch.setenv("DEBASHER_MOD_DIR", str(shared_dir))
    node = _node(opts={"pfile": "shared.sh"})
    assert node._pfile == str((shared_dir / "shared.sh").resolve())


def test_an_absolute_program_is_accepted_with_a_warning(outdir, tmp_path, caplog):
    node = _node(opts={"pfile": str(tmp_path / "program" / "pipeline.sh")})
    assert node._pfile == str(tmp_path / "program" / "pipeline.sh")
    assert "not portable across machines" in caplog.text


def test_a_program_that_is_not_there_stops_the_node(outdir):
    with pytest.raises(ValueError, match="the general program nowhere.sh is not a file"):
        _node(opts={"pfile": "nowhere.sh"})


def test_the_process_option_names_the_process_to_launch_alone(outdir):
    node = _node(opts={"process": "align"})
    assert node._process == "align"
    assert node._get_node_info_extra()["launcher"]["process"] == "align"


def test_a_launcher_node_cannot_be_a_task_of_an_array(outdir, monkeypatch):
    monkeypatch.setattr(_Launcher, "_get_task_idx", lambda self: 0)
    with pytest.raises(ValueError, match="cannot be a task of an array process"):
        _node()


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
        ({"opts": {}, "run": 7}, "non-empty"),
        ({"opts": {}, "run": "s17//x"}, "relative"),
        ({"opts": {}, "run": "s17/"}, "relative"),
        ({"opts": {"--outdir": "/elsewhere"}}, "option of debasher_exec"),
        ({"opts": {"--builtinsched-oneshot": ""}}, "option of debasher_exec"),
        ({"opts": {"-x": "--wait"}}, "is an option of debasher_exec"),
    ],
)
def test_a_malformed_request_is_dropped(outdir, caplog, packet, reason):
    node = _node()
    _request(node, 5, packet)
    assert reason in caplog.text
    assert os.listdir(outdir / ".launcher" / "registrations") == []


def test_a_request_without_opts_launches_the_program_with_none(outdir):
    node = _node()
    _request(node, 5, {"run": "a", "ignored": "field"})
    assert _launch_record(outdir, "a")["opts"] == {}


def test_the_options_refused_are_those_that_debasher_exec_reads():
    # The labels of the case of read_pars in engine/debasher_exec.sh
    source = (ENGINE_SOURCE_DIR / "debasher_exec.sh").read_text()
    read_pars = source[source.index("\nread_pars()"):source.index("\ncheck_pars()")]
    labels = set(re.findall(r'^\s*"(--[a-z-]+)"\)', read_pars, re.MULTILINE))
    assert labels == launcher_mod._DEBASHER_EXEC_OPTIONS


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


@pytest.mark.parametrize("sched", ["BUILTIN", "SLURM"])
def test_the_exit_code_of_debasher_exec_is_the_end_of_the_batch_run(outdir, monkeypatch, sched):
    # debasher_exec waits for the program: its 0 is final, and
    # debasher_status, which would say 3 here, is never asked
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", f"cpus=1; batch_sched={sched}")
    monkeypatch.setenv("FAKE_STATUS", "3")
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


def test_the_scheduler_of_the_batch_runs_reaches_debasher_exec(outdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; batch_sched=SLURM")
    node = _node()
    assert node.BATCH_SCHED == "SLURM"
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    # Under Slurm debasher_exec waits for the program only with --wait
    assert "--sched SLURM --wait" in (outdir / "a" / "fake_args").read_text()


def test_the_shell_of_a_batch_run_is_kept_with_its_start_time(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    pid, at, start = (outdir / "a" / "launcher.pid").read_text().strip().partition("@")
    assert pid.isdigit() and at == "@"
    assert " " not in start


def test_without_a_scheduler_the_batch_runs_use_the_builtin_one(outdir):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    assert "--sched BUILTIN" in (outdir / "a" / "fake_args").read_text()


def test_the_options_of_the_request_reach_debasher_exec(outdir, tmp_path):
    node = _node()
    _request(node, 1, {"opts": {"-bam": "/data/s17.bam", "-k": "3"}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    pfile = (tmp_path / "program" / "pipeline.sh").resolve()
    assert (outdir / "a" / "fake_args").read_text().split() == [
        "--pfile", str(pfile), "--outdir", str(outdir / "a"), "--sched", "BUILTIN",
        "-bam", "/data/s17.bam", "-k", "3",
    ]


def test_debasher_status_is_asked_at_most_once_every_interval(outdir, monkeypatch):
    node = _node()
    node.STATUS_CHECK_INTERVAL_SECS = 5.0
    asked = []
    monkeypatch.setattr(launcher_mod, "ask_program_status", lambda tool, run_dir: asked.append(run_dir) or 0)
    now = [100.0]
    monkeypatch.setattr(launcher_mod.time, "monotonic", lambda: now[0])

    assert node._ask_program_status("a") == 0
    now[0] += 4.9
    # Not asked again yet: counts as in progress
    assert node._ask_program_status("a") is None
    assert node._ask_program_status("b") == 0
    now[0] += 0.2
    assert node._ask_program_status("a") == 0
    assert asked == ["a", "b", "a"]


def test_a_run_directory_removed_by_hand_is_skipped_and_logged_once(outdir, caplog):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _request(node, 2, {"opts": {}, "run": "b"})
    shutil.rmtree(outdir / "a")

    _check_until_ended(node, outdir, "b")
    node._check_runs()

    assert not (outdir / "a").exists()
    assert caplog.text.count("skipping the batch run a") == 1


def test_a_removed_run_directory_named_again_is_the_batch_run_of_the_new_request(outdir, caplog):
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    shutil.rmtree(outdir / "a")

    _request(node, 2, {"opts": {"-k": "2"}, "run": "a"})
    _check_until_ended(node, outdir, "a")
    node._check_runs()

    # The old registration is skipped, and the new one launched once
    assert len(_launches(outdir, "a")) == 1
    assert "-k 2" in (outdir / "a" / "fake_args").read_text()
    assert "skipping the batch run" not in caplog.text


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


def test_the_exit_code_of_debasher_exec_outlives_a_crash_of_its_launcher(outdir, monkeypatch):
    # debasher_exec refuses the options of the request while the node that
    # launched it is gone: its shell leaves the exit code in the run
    # directory, and the new incarnation ends the batch run as failed
    # instead of launching it again.
    monkeypatch.setenv("FAKE_SLEEP", "1")
    monkeypatch.setenv("FAKE_EXIT", "3")
    node = _node()
    _request(node, 1, {"opts": {}, "run": "a"})
    node._check_runs()
    assert _wait_until(lambda: _launches(outdir, "a"))

    relaunched = _node()
    _check_until_ended(relaunched, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "3"
    assert len(_launches(outdir, "a")) == 1


# --- the state of a batch run, from its run directory alone ----------------


def _dead_pid():
    dead = subprocess.Popen(["true"])
    dead.wait()
    return dead.pid


def _state(run_dir, single_process=False, status=None):
    asked = []

    def ask_program_status(d):
        asked.append(d)
        return status

    return launcher_mod._get_batch_run_state(str(run_dir), single_process, ask_program_status), asked


def test_a_run_with_no_pid_is_registered(tmp_path):
    assert _state(tmp_path) == (("registered", None), [])


def test_a_run_with_an_exit_code_has_ended(tmp_path):
    (tmp_path / "exit_code").write_text("0\n")
    assert _state(tmp_path)[0] == ("finished", 0)
    (tmp_path / "exit_code").write_text("3\n")
    assert _state(tmp_path)[0] == ("failed", 3)
    assert _state(tmp_path, single_process=True)[0] == ("failed", 3)


def test_a_run_whose_shell_is_alive_is_running(tmp_path):
    shell = subprocess.Popen(["sleep", "10"])
    try:
        (tmp_path / "launcher.pid").write_text(f"{shell.pid}\n")
        assert _state(tmp_path) == (("running", None), [])
    finally:
        shell.kill()
        shell.wait()


def test_a_run_whose_shell_is_alive_since_its_start_time_is_running(tmp_path):
    shell = subprocess.Popen(["sleep", "10"])
    try:
        (tmp_path / "launcher.pid").write_text(f"{launcher_mod._get_launch_id(shell.pid)}\n")
        assert "@" in (tmp_path / "launcher.pid").read_text()
        assert _state(tmp_path) == (("running", None), [])
    finally:
        shell.kill()
        shell.wait()


def test_a_process_that_got_the_pid_of_the_shell_is_not_taken_for_it(tmp_path):
    # The shell ended with no file, as after a reboot, and its process id now
    # belongs to a process that started at another time
    other = subprocess.Popen(["sleep", "10"])
    try:
        (tmp_path / "launcher.pid").write_text(f"{other.pid}@Mon_Jan__1_00:00:00_2001\n")
        assert _state(tmp_path, single_process=True) == (("stopped", None), [])
        # A shell that ended before its start time could be read
        (tmp_path / "launcher.pid").write_text(f"{other.pid}@\n")
        assert _state(tmp_path, single_process=True) == (("stopped", None), [])
    finally:
        other.kill()
        other.wait()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can signal every process")
def test_a_process_of_another_user_is_never_the_shell(tmp_path):
    # Process 1 belongs to root, as the first process ids after a reboot do
    (tmp_path / "launcher.pid").write_text("1\n")
    assert _state(tmp_path, single_process=True) == (("stopped", None), [])


def test_a_shell_that_ended_is_told_by_its_file_even_before_it_is_waited_for(tmp_path):
    # A zombie: the shell has ended, and its PID still shows as alive until
    # its parent waits for it.
    shell = subprocess.Popen(["sh", "-c", f"echo 4 > {tmp_path}/exit_code"])
    try:
        (tmp_path / "launcher.pid").write_text(f"{shell.pid}\n")
        assert _wait_until(lambda: (tmp_path / "exit_code").exists())
        time.sleep(0.1)
        assert _state(tmp_path)[0] == ("failed", 4)
    finally:
        shell.wait()


@pytest.mark.parametrize(
    "status, state",
    [
        (None, ("running", None)),
        (2, ("running", None)),
        (0, ("finished", 0)),
        (3, ("stopped", None)),
        (1, ("stopped", None)),
    ],
)
def test_a_run_whose_shell_is_gone_with_no_file_was_stopped(tmp_path, status, state):
    (tmp_path / "launcher.pid").write_text(f"{_dead_pid()}\n")
    assert _state(tmp_path, status=status) == (state, [str(tmp_path)])


def test_a_single_process_whose_shell_is_gone_with_no_exit_code_was_stopped(tmp_path):
    (tmp_path / "launcher.pid").write_text(f"{_dead_pid()}\n")
    assert _state(tmp_path, single_process=True) == (("stopped", None), [])


def test_the_node_info_of_a_launcher_node_names_its_batch_runs(outdir, tmp_path):
    node = _node(opts={"process": "align", "runsdir": str(tmp_path / "runs")})
    assert node._get_node_info_extra() == {
        "launcher": {"runs_root": str(tmp_path / "runs"), "process": "align"}
    }
    assert _node()._get_node_info_extra() == {"launcher": {"runs_root": str(outdir), "process": None}}
    assert node._RUNTIME_CLASS == "ProgramLauncher"


def test_the_runsdir_option_gives_the_runs_root(outdir, tmp_path):
    runs = tmp_path / "runs"
    node = _node(opts={"runsdir": str(runs)})
    _request(node, 1, {"opts": {}, "run": "a"})

    assert (runs / "a" / "launch.json").exists()
    assert not (outdir / "a").exists()
    assert node._get_node_info_extra()["launcher"]["runs_root"] == str(runs)


def test_without_the_runsdir_option_the_runs_root_is_the_output_directory(outdir):
    node = _node()
    _request(node, 2, {"opts": {}, "run": "b"})
    assert (outdir / "b" / "launch.json").exists()


def test_a_relative_runsdir_option_stops_the_node(outdir):
    with pytest.raises(ValueError, match="not an absolute path"):
        _node(opts={"runsdir": "runs"})


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

    assert brought_in == [{"run": "a", "pos": 1, "exit_code": 0}]
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

    _request(node, 5, {"run": "a", "pos": 1, "exit_code": 0}, port="runs_done")
    _request(node, 6, {"run": "a", "pos": 1, "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == [
        {"run": "a", "run_dir": str(outdir / "a"), "status": "finished", "exit_code": 0}
    ]
    assert node.capture_node_state() == {"announced": [1]}


def test_the_end_of_a_failed_batch_run_is_announced_as_failed(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})

    _request(node, 5, {"run": "a", "pos": 1, "exit_code": 3}, port="runs_done")

    assert _sent(node, "outdone") == [
        {"run": "a", "run_dir": str(outdir / "a"), "status": "failed", "exit_code": 3}
    ]


def test_the_end_of_a_batch_run_names_its_run_directory_under_the_runsdir_option(outdir, tmp_path):
    runs = tmp_path / "runs"
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null", "runsdir": str(runs)})

    _request(node, 5, {"run": "s17/v2", "pos": 1, "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == [
        {"run": "s17/v2", "run_dir": str(runs / "s17" / "v2"), "status": "finished", "exit_code": 0}
    ]


def test_the_announced_runs_survive_a_restore(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})
    node.restore_node_state({"announced": [1]})

    _request(node, 5, {"run": "a", "pos": 1, "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == []


def test_the_end_of_a_run_directory_named_again_is_announced_too(outdir):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})

    # The run directory a, removed by hand and named again by the request
    # at position 9
    _request(node, 5, {"run": "a", "pos": 1, "exit_code": 0}, port="runs_done")
    _request(node, 10, {"run": "a", "pos": 9, "exit_code": 3}, port="runs_done")

    assert [m["exit_code"] for m in _sent(node, "outdone")] == [0, 3]


def test_an_end_with_no_position_is_dropped(outdir, caplog):
    node = _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})

    _request(node, 5, {"run": "a", "exit_code": 0}, port="runs_done")

    assert _sent(node, "outdone") == []
    assert "no run or position" in caplog.text


# --- the computational specifications ----------------------------------------


def test_the_computational_specs_set_the_batch_runs_at_a_time(outdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; mem=32; max_concurrent_runs=4")
    node = _node()
    assert node.MAX_CONCURRENT_RUNS == 4


def test_a_count_of_batch_runs_that_is_not_whole_stops_the_node(outdir, monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; max_concurrent_runs=0.5")
    with pytest.raises(ValueError, match="not a positive whole number"):
        _node()


# --- a single process instead of a program -----------------------------------


def _process_node():
    return _node(opts={"process": "align"})


def test_a_process_launcher_runs_the_process_alone_from_the_run_directory(outdir, tmp_path):
    node = _process_node()
    _request(node, 1, {"opts": {"-bam": "/data/s17.bam", "-outf": "out.txt"}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    pfile = (tmp_path / "program" / "pipeline.sh").resolve()
    assert (outdir / "a" / "fake_args").read_text().split() == [
        str(pfile), "align", "--", "-bam", "/data/s17.bam", "-outf", "out.txt"
    ]
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


def test_a_process_writes_its_own_exit_code(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_EXIT", "4")
    node = _process_node()
    _request(node, 1, {"opts": {}, "run": "a"})

    _check_until_ended(node, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "4"


def test_the_exit_code_of_a_process_outlives_a_crash_of_its_launcher(outdir, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "1")
    node = _process_node()
    _request(node, 1, {"opts": {}, "run": "a"})
    node._check_runs()
    assert _wait_until(lambda: _launches(outdir, "a"))

    # A new incarnation, which did not launch it: the process is still
    # running, and then writes its exit code on its own.
    relaunched = _process_node()
    relaunched._check_runs()
    assert not (outdir / "a" / "exit_code").exists()
    _check_until_ended(relaunched, outdir, "a")

    assert (outdir / "a" / "exit_code").read_text().strip() == "0"
    assert len(_launches(outdir, "a")) == 1


def test_a_process_stopped_before_it_ended_is_launched_again(outdir):
    node = _process_node()
    _request(node, 1, {"opts": {}, "run": "a"})
    _orphan(outdir, "a")

    _check_until_ended(node, outdir, "a")

    assert len(_launches(outdir, "a")) == 1
    assert (outdir / "a" / "exit_code").read_text().strip() == "0"


# --- its ports ------------------------------------------------------------------


def test_a_launcher_without_an_input_port_says_so(outdir):
    class Unwired(_Launcher):
        INPUT_PORTS = []

    assert _node(_NotifyingLauncher, {"requests": "/dev/null", "outdone": "/dev/null"})._find_wiring_problem() is None
    assert Unwired(opts={"pfile": "pipeline.sh"})._find_wiring_problem().startswith("no input port")


# --- registrations that cannot be read ------------------------------------------


def _write_registration(outdir, name, text):
    registrations = outdir / ".launcher" / "registrations"
    registrations.mkdir(parents=True, exist_ok=True)
    (registrations / name).write_text(text)


def test_a_registration_that_cannot_be_read_is_skipped_with_one_warning(outdir, caplog):
    # Written atomically, so only a crash of the machine or a hand edit
    # leaves one: its batch run is unknown to the node and to the reset
    _write_registration(outdir, "x.json", '{"run": "a"}')
    _write_registration(outdir, "5.json", "not json")
    node = _node()

    for _ in range(3):
        assert node._list_registrations() == []

    assert caplog.text.count("cannot read the registration") == 2
    assert "x.json" in caplog.text and "5.json" in caplog.text


@pytest.mark.parametrize("text", ["[1]", '"x"', "5", '{"run": null}', '{"run": 5}', '{"run": ""}'])
def test_a_registration_whose_content_is_not_one_is_skipped(outdir, caplog, text):
    # JSON, but not an object with the run directory of a batch run
    _write_registration(outdir, "5.json", text)
    node = _node()

    assert node._list_registrations() == []
    assert "cannot read the registration" in caplog.text


def test_a_registration_left_half_written_by_a_crash_is_not_one(outdir, caplog):
    _write_registration(outdir, "5.json.tmp", '{"ru')
    node = _node()

    assert node._list_registrations() == []
    assert "cannot read the registration" not in caplog.text


def test_the_registrations_that_cannot_be_read_are_given_apart():
    # debasher_inspect_node ignores them, as the node does
    import debasher_runtime_launcher as launcher_mod

    registrations, unreadable = launcher_mod._read_registrations("/nonexistent")
    assert (registrations, unreadable) == ([], [])


# --- a launcher node of a non-durable program --------------------------------------


@pytest.fixture
def non_durable(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROGRAM_DURABILITY", "non-durable")


def test_in_a_non_durable_program_the_request_number_comes_from_a_counter_on_disk(outdir, non_durable):
    node = _node()
    _request(node, 1, {"opts": {"-a": "x"}})
    _request(node, 2, {"opts": {"-a": "y"}})
    with open(outdir / ".launcher" / "request_counter") as f:
        assert f.read().strip() == "2"

    # A relaunched node, whose positions start at 1 again, goes on counting
    relaunched = _node()
    _request(relaunched, 1, {"opts": {"-a": "z"}})

    assert _launch_record(outdir, "3") == {"life_id": node._life_id, "pos": 3, "opts": {"-a": "z"}}
    for number in (1, 2, 3):
        assert (outdir / ".launcher" / "registrations" / f"{number}.json").exists()


def test_in_a_non_durable_program_a_run_directory_with_a_batch_run_is_not_registered_again(
    outdir, non_durable, caplog
):
    node = _node()
    _request(node, 1, {"opts": {"-a": "x"}, "run": "s17"})
    # The same request again, as from a relaunched DirectoryWatcher, with
    # the same life and the same request number as a replay would have
    relaunched = _node()
    _request(relaunched, 1, {"opts": {"-a": "x"}, "run": "s17"})

    assert _launch_record(outdir, "s17") == {"life_id": node._life_id, "pos": 1, "opts": {"-a": "x"}}
    assert not (outdir / ".launcher" / "registrations" / "2.json").exists()
    assert "already has a batch run" in caplog.text
    assert "belongs to another request" not in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


def test_in_a_durable_program_the_request_number_is_the_position(outdir, monkeypatch):
    monkeypatch.delenv("DEBASHER_PROGRAM_DURABILITY", raising=False)
    node = _node()
    _request(node, 7, {"opts": {}})
    assert _launch_record(outdir, "7")["pos"] == 7
    assert not (outdir / ".launcher" / "request_counter").exists()
