"""
Real debasher_exec runs of debasher_watch_ref.sh, a resident program that
observes the outside world: watch watches a directory and sends launch a
request for each .bam file once it is complete, launch runs count_lines,
alone, for each one, and sink gets a notice when each batch run ends.
Checks that every file that arrives is processed once, a file still being
written only once it is complete, and that a watch killed and relaunched,
which brings the files it had seen in again, makes no request twice.
"""

import os
import signal
import time
from pathlib import Path

from chaos_ref import SinkTailer
from resident_run import (
    id_file,
    launch,
    outdir,
    read_pid,
    real_run,
    wait_until,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_watch_ref.sh"


def _notices(tailer):
    return [env["payload"] for env in list(tailer.records) if env.get("type") == "DATA"]


def _lines_counted(outdir, run):
    path = Path(outdir, "launch", run, "lines.txt")
    return int(path.read_text()) if path.exists() else None


def _registrations(outdir):
    registrations_dir = Path(outdir, "launch", ".launcher", "registrations")
    return sorted(os.listdir(registrations_dir)) if registrations_dir.is_dir() else []


def test_every_file_that_arrives_is_processed_once(outdir, tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    launch(PFILE, outdir, "-watchdir", str(incoming))
    assert wait_until(lambda: os.path.exists(os.path.join(outdir, "__exec__", "watch", "control_ports")))
    tailer = SinkTailer(os.path.join(outdir, "__exec__", "sink", "log"))
    tailer.start()
    try:
        (incoming / "a.bam").write_text("r1\nr2\nr3\n")
        # b.bam is written in two steps, a while apart, as a copy in progress
        # is: it is processed whole, once it no longer changes.
        with open(incoming / "b.bam", "w") as f:
            f.write("r1\n")
            f.flush()
            time.sleep(0.1)
            f.write("r2\n")
        # Neither a hidden file nor another name is a file to process.
        (incoming / ".c.bam.part").write_text("r1\n")
        (incoming / "c.bai").write_text("index\n")

        assert wait_until(lambda: len(_notices(tailer)) == 2, timeout=60.0)
        assert _lines_counted(outdir, "a") == 3
        assert _lines_counted(outdir, "b") == 2

        # watch, killed and relaunched, sees a.bam and b.bam again and brings
        # them in again; its node state keeps it from requesting them twice.
        id_path = id_file(outdir, "watch")
        old_pid = read_pid(id_path)
        os.killpg(int(old_pid), signal.SIGKILL)
        assert wait_until(lambda: read_pid(id_path) not in (None, old_pid), timeout=15.0)
        (incoming / "d.bam").write_text("r1\n")
        assert wait_until(lambda: len(_notices(tailer)) == 3, timeout=60.0)
        assert not wait_until(lambda: len(_notices(tailer)) > 3, timeout=3.0)
    finally:
        tailer.stop_and_join()

    assert sorted(n["run"] for n in _notices(tailer)) == ["a", "b", "d"]
    assert all(n["status"] == "finished" for n in _notices(tailer))
    assert _lines_counted(outdir, "d") == 1
    assert len(_registrations(outdir)) == 3
