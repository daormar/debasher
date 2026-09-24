"""
Real debasher_exec runs of debasher_resume_ref.sh, a resident program with
no fifo from outside: solo is triggered only by the Supervisor. Checks that
debasher_exec on the same output directory after a halt launches every node
again, which resumes from its checkpoint, and that a node keeps its output
directory when it is launched again, by the Supervisor after a crash or by
a new run after a halt.
"""

import os
import signal
import subprocess
import time
from pathlib import Path

from resident_run import (
    DEBASHER_STOP_RESIDENT,
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    sched_out_file,
    wait_for_text,
    wait_until,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_resume_ref.sh"


def _wait_until_solo_started(outdir):
    assert wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", "solo", "control_ports")))


def _halt(outdir):
    result = subprocess.run(
        [str(DEBASHER_STOP_RESIDENT), "-d", outdir, "--timeout", "30"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _put_result(outdir):
    """A file in solo's own output directory, as a node that writes its
    results there leaves one."""
    path = os.path.join(outdir, "solo", "result.txt")
    with open(path, "w") as f:
        f.write("kept\n")
    return path


def test_a_new_run_after_a_halt_resumes_every_node(outdir):
    launch(PFILE, outdir)
    _wait_until_solo_started(outdir)
    result = _put_result(outdir)
    _halt(outdir)
    old_pids = {name: read_pid(id_file(outdir, name)) for name in ("solo", "sup")}

    launch(PFILE, outdir)

    for name, old_pid in old_pids.items():
        assert wait_until(lambda: read_pid(id_file(outdir, name)) not in (None, old_pid)), (
            f"{name} was not launched again"
        )
    assert wait_for_text(sched_out_file(outdir, "solo"), "restored checkpoint for epoch")
    assert os.path.exists(result)


def test_a_node_relaunched_by_the_supervisor_keeps_its_output_directory(outdir):
    launch(PFILE, outdir)
    _wait_until_solo_started(outdir)
    result = _put_result(outdir)

    id_path = id_file(outdir, "solo")
    old_pid = read_pid(id_path)
    killed_at = time.time()
    os.killpg(int(old_pid), signal.SIGKILL)
    assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)

    # The new incarnation has got as far as running solo, past the point
    # where the output directory of a general process is emptied.
    sched_out = sched_out_file(outdir, "solo")

    def relaunch_started():
        if os.path.getmtime(sched_out) <= killed_at:
            return False
        with open(sched_out) as f:
            return "starting with default values" in f.read()

    assert wait_until(relaunch_started)
    assert os.path.exists(result)
