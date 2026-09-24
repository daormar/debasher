"""
Real debasher_exec runs of debasher_launcher_ref.sh, a resident program with
a launcher node: every request that arrives at launch starts a batch run of
debasher_launcher_batch.sh, which launch finds next to its own module, in a
run directory of its own, and sink gets a notice when each one ends.
Checks that the batch runs leave their results in their run directories,
and that a launch killed while a batch run is going on is relaunched,
leaves the batch run to end, and still tells sink, once. Every test runs
with the built-in scheduler for the batch runs, and with SLURM too where the
machine has it: there debasher_exec only submits the jobs and ends at once.
"""

import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from chaos_ref import SinkTailer
from resident_run import (
    find_fifo,
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_until,
    write_line,
)

pytestmark = real_run

ENGINE_TEST_DIR = Path(__file__).resolve().parent
PFILE = ENGINE_TEST_DIR / "debasher_launcher_ref.sh"


def _slurm_is_up():
    """Whether this machine can run SLURM jobs: sbatch is there and the
    controller answers. Both the exit code and the answer are checked, since
    older versions of scontrol exit with 0 even when the controller is down."""
    if not shutil.which("sbatch") or not shutil.which("scontrol"):
        return False
    try:
        result = subprocess.run(["scontrol", "ping"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "UP" in result.stdout


@pytest.fixture(
    autouse=True,
    params=[
        "BUILTIN",
        pytest.param(
            "SLURM",
            marks=pytest.mark.skipif(not _slurm_is_up(), reason="no SLURM controller up on this machine"),
        ),
    ],
)
def batch_sched(request, monkeypatch):
    monkeypatch.setenv("DEBASHER_LAUNCHER_REF_SCHED", request.param)
    return request.param


def _run_dir(outdir, run):
    return Path(outdir, "launch", run)


def _notices(tailer):
    return [env["payload"] for env in list(tailer.records) if env.get("type") == "DATA"]


def _request(outdir, run, text, secs):
    write_line(
        find_fifo(outdir, "launch_requests"),
        {"type": "DATA", "payload": {"opts": {"-text": text, "-secs": str(secs)}, "run": run}},
    )


def _start(outdir):
    launch(PFILE, outdir)
    assert wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", "launch", "control_ports")))
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    return tailer


def test_every_request_runs_the_batch_program_in_its_own_run_directory(outdir):
    tailer = _start(outdir)
    try:
        _request(outdir, "r1", "one", 0)
        _request(outdir, "s/r2", "two", 0)
        assert wait_until(lambda: len(_notices(tailer)) == 2, timeout=60.0)
    finally:
        tailer.stop_and_join()

    assert sorted(n["run"] for n in _notices(tailer)) == ["r1", "s/r2"]
    assert all(n["exit_code"] == 0 for n in _notices(tailer))
    for run, text in (("r1", "one"), ("s/r2", "two")):
        run_dir = _run_dir(outdir, run)
        assert (run_dir / "step" / "result.txt").read_text() == f"{text}\n"
        assert (run_dir / "exit_code").read_text().strip() == "0"


def test_a_batch_run_outlives_a_crash_of_its_launcher_and_is_announced_once(outdir):
    tailer = _start(outdir)
    try:
        _request(outdir, "slow", "late", 4)
        run_dir = _run_dir(outdir, "slow")
        result = run_dir / "step" / "result.txt"
        assert wait_until(lambda: (run_dir / "launcher.pid").exists(), timeout=30.0)

        id_path = id_file(outdir, "launch")
        old_pid = read_pid(id_path)
        os.killpg(int(old_pid), signal.SIGKILL)
        # Killed while the batch run was going on.
        assert not result.exists()
        assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)

        assert wait_until(lambda: len(_notices(tailer)) >= 1, timeout=60.0)
        # Time for a second notice to show up, if one were sent.
        assert not wait_until(lambda: len(_notices(tailer)) > 1, timeout=3.0)
    finally:
        tailer.stop_and_join()

    assert _notices(tailer) == [{"run": "slow", "status": "finished", "exit_code": 0}]
    assert (run_dir / "step" / "result.txt").read_text() == "late\n"
