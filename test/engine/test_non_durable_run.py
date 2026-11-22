"""
Real debasher_exec runs of debasher_non_durable_ref.sh, the reference program
of the non-durable mode (see "The non-durable mode" in
doc/design_doc_resident.md): what a crash loses and what it does not (N1),
what a stop gives (N2), the tools that refuse the mode, and the refusals of
debasher_exec around the declaration of the mode.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from resident_run import (
    DEBASHER_EXEC,
    DEBASHER_SNAPSHOT_RESIDENT,
    DEBASHER_STOP_RESIDENT,
    DEBASHER_RESET_RESIDENT,
    REPO_ROOT,
    find_fifo,
    kill_node,
    launch,
    outdir,
    read_pid,
    id_file,
    real_run,
    wait_for,
    wait_for_relaunch,
    wait_until,
    write_line,
)

pytestmark = real_run

PFILE = Path(__file__).resolve().parent / "debasher_non_durable_ref.sh"
DEBASHER_INSPECT_RESIDENT = REPO_ROOT / "bin" / "debasher_inspect_resident"
NODES = ("count", "sink")


def _trace(outdir):
    path = os.path.join(outdir, "sink", "trace.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _wait_for_trace(outdir, length, timeout=30.0):
    assert wait_until(lambda: len(_trace(outdir)) >= length, timeout=timeout), _trace(outdir)
    return _trace(outdir)


def _every_node_finished(outdir):
    return all(
        os.path.exists(os.path.join(outdir, "__exec__", name, f"{name}.finished"))
        for name in (*NODES, "sup")
    )


def _run(tool, *args):
    return subprocess.run([str(tool), *args], capture_output=True, text=True)


def test_a_crash_loses_the_state_of_the_node_and_nothing_that_a_fifo_held(outdir):
    """
    N1: a relaunched node starts with its initial state, so its count
    begins at 1 again; what the external fifo held while the node was
    down reaches the new incarnation; and no node keeps a log or a
    checkpoint on disk.
    """
    launch(PFILE, outdir)
    ext = find_fifo(outdir, "count_ext")
    assert wait_for(id_file(outdir, "count"))
    # The writer keeps the fifo open, as a source does, so that what it
    # writes while count is down waits in the fifo
    fd = os.open(ext, os.O_WRONLY)
    try:
        for value in (1, 2, 3):
            os.write(fd, (json.dumps({"type": "DATA", "payload": value}) + "\n").encode())
        trace = _wait_for_trace(outdir, 3)
        assert [(r["value"], r["count"]) for r in trace] == [(1, 1), (2, 2), (3, 3)]

        old_pid = kill_node(outdir, "count")
        # Written while count is down: the fifo holds it for the relaunch
        for value in (4, 5):
            os.write(fd, (json.dumps({"type": "DATA", "payload": value}) + "\n").encode())
        assert wait_for_relaunch(outdir, "count", old_pid) is not None

        trace = _wait_for_trace(outdir, 5)
    finally:
        os.close(fd)
    assert [(r["value"], r["count"]) for r in trace] == [(1, 1), (2, 2), (3, 3), (4, 1), (5, 2)]

    for name in NODES:
        execdir = Path(outdir, "__exec__", name)
        assert not (execdir / "log").exists()
        assert not (execdir / "checkpoints").exists()
        assert not (execdir / "halted").exists()
        with open(execdir / "node_info") as f:
            assert json.load(f)["durability"] == "non-durable"


def test_a_stop_ends_every_node_without_a_halt_and_the_next_launch_starts_afresh(outdir):
    """
    N2: debasher_stop_resident stops the Supervisor and then every node,
    with no halt and no halted marker, and exits 0; the next launch starts
    every node with its initial state.
    """
    launch(PFILE, outdir)
    ext = find_fifo(outdir, "count_ext")
    assert wait_for(id_file(outdir, "sink"))
    for value in (1, 2):
        write_line(ext, {"type": "DATA", "payload": value})
    _wait_for_trace(outdir, 2)

    result = _run(DEBASHER_STOP_RESIDENT, "-d", outdir)
    assert result.returncode == 0, result.stderr
    assert "non-durable" in result.stderr
    assert "without a halt" in result.stderr
    assert _every_node_finished(outdir)
    for name in NODES:
        assert not os.path.exists(os.path.join(outdir, "__exec__", name, "halted"))

    launch(PFILE, outdir)
    ext = find_fifo(outdir, "count_ext")
    assert wait_until(lambda: read_pid(id_file(outdir, "count")) is not None)
    write_line(ext, {"type": "DATA", "payload": 3})
    trace = _wait_for_trace(outdir, 3)
    assert [(r["value"], r["count"]) for r in trace] == [(1, 1), (2, 2), (3, 1)]


def test_the_tools_of_the_durable_mode_refuse_the_program(outdir):
    launch(PFILE, outdir)
    assert wait_for(id_file(outdir, "count"))

    result = _run(DEBASHER_SNAPSHOT_RESIDENT, "-d", outdir)
    assert result.returncode == 1
    assert "non-durable" in result.stderr and "no snapshots" in result.stderr

    assert wait_for(os.path.join(outdir, "__exec__", "count", "node_info"))
    result = _run(DEBASHER_INSPECT_RESIDENT, "-d", outdir, "-p", "count", "summary")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["durability"] == "non-durable"
    assert summary["checkpoints"] == []
    assert summary["input_log"]["segments"] == 0

    for command in (("checkpoint", "1"), ("log",)):
        result = _run(DEBASHER_INSPECT_RESIDENT, "-d", outdir, "-p", "count", *command)
        assert result.returncode == 1
        assert "non-durable" in result.stderr


def test_debasher_exec_keeps_the_mode_of_the_declaration_and_of_the_state(outdir, tmp_path):
    """
    --durability has to agree with the declaration of the module, the saved
    command line records the mode, and a launch in the other mode over the
    state of a run is refused until the program is reset.
    """
    result = _run(DEBASHER_EXEC, "--pfile", str(PFILE), "--outdir", outdir, "--durability", "durable")
    assert result.returncode == 1
    assert "does not agree with the program" in result.stderr

    launch(PFILE, outdir)
    ext = find_fifo(outdir, "count_ext")
    assert wait_for(id_file(outdir, "sink"))
    write_line(ext, {"type": "DATA", "payload": 1})
    _wait_for_trace(outdir, 1)
    with open(os.path.join(outdir, "command_line.sh")) as f:
        assert "--durability non-durable" in f.read()
    result = _run(DEBASHER_STOP_RESIDENT, "-d", outdir)
    assert result.returncode == 0, result.stderr

    # The same program declared durable, under the same name, so that only
    # the mode changes
    durable_dir = tmp_path / "durable"
    durable_dir.mkdir()
    durable_pfile = durable_dir / PFILE.name
    durable_pfile.write_text(
        PFILE.read_text().replace('program_type "resident" "non-durable"', 'program_type "resident"')
    )
    result = _run(DEBASHER_EXEC, "--pfile", str(durable_pfile), "--outdir", outdir, "--validate")
    assert result.returncode == 1
    assert "does not change its durability mode" in result.stderr
    assert "debasher_reset_resident" in result.stderr

    result = _run(DEBASHER_RESET_RESIDENT, "-d", outdir)
    assert result.returncode == 0, result.stderr
    result = _run(DEBASHER_EXEC, "--pfile", str(durable_pfile), "--outdir", outdir, "--validate")
    assert result.returncode == 0, result.stderr
