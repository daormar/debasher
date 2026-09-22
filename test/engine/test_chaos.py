"""
Chaos test for the resident-program engine (see the design doc's "Acceptance:
how reliability is shown"). Drives a real debasher_exec run of
debasher_chaos_ref.sh, never mocks, so it is slow and, in later pieces,
disruptive on purpose (real kill -9 of real processes): skipped unless
DEBASHER_RUN_CHAOS_TEST is set, so it never runs as part of the ordinary
suite.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PFILE = Path(__file__).resolve().parent / "debasher_chaos_ref.sh"
_DEBASHER_EXEC = _REPO_ROOT / "bin" / "debasher_exec"
_DEBASHER_STOP = _REPO_ROOT / "bin" / "debasher_stop"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEBASHER_RUN_CHAOS_TEST"),
    reason="real debasher_exec chaos test, slow and disruptive: set DEBASHER_RUN_CHAOS_TEST=1 to run it",
)


def _write_line(fifo_path, obj):
    fd = os.open(fifo_path, os.O_WRONLY)
    try:
        os.write(fd, (json.dumps(obj) + "\n").encode())
    finally:
        os.close(fd)


def _find_fifo(outdir, name):
    matches = list(Path(outdir, "__fifos__").rglob(name))
    assert matches, f"fifo {name!r} not found under {outdir}"
    return str(matches[0])


def _wait_for(path, timeout=30.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(interval)
    return False


def _read_sink_trace(outdir):
    """
    sink's own input log, read directly: G5's dedup happens before a
    record is ever logged (see _on_arrival), so this is already the
    exact, ordered, once-only record of what fanin sent it, with no
    verification-side bookkeeping of its own needed.
    """
    log_dir = Path(outdir, "__exec__", "sink", "log")
    segments = sorted(log_dir.glob("*.log"), key=lambda p: int(p.stem))
    records = []
    for seg in segments:
        with open(seg) as f:
            for line in f:
                if not line.endswith("\n"):
                    # A torn tail left by a killed process: ignored on
                    # replay, same as the engine itself does.
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append(record["env"])
    return records


@pytest.fixture
def outdir(tmp_path):
    d = str(tmp_path / "chaos_out")
    yield d
    subprocess.run(
        [str(_DEBASHER_STOP), "-d", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def test_a_clean_run_produces_the_exact_trace_at_sink(outdir):
    """
    "Run once with no failures" (Acceptance): every value fanin forwards
    from ext, and every one it echoes back through the loop, reaches sink
    exactly once, in the order fanin actually processed it (G1 channel
    order, G2 no silent loss, G4 faithful replay across ports).
    """
    assert _DEBASHER_EXEC.exists(), "bin/debasher_exec not built: run make install first"

    k = 20
    log_path = os.path.join(os.path.dirname(outdir), "exec.log")
    # A resident program's processes are launched in the background and
    # keep running after debasher_exec itself returns, still holding
    # their inherited stdout/stderr: piping (capture_output=True) would
    # make subprocess.run wait for those too, not just for debasher_exec.
    with open(log_path, "w") as log_file:
        result = subprocess.run(
            [str(_DEBASHER_EXEC), "--pfile", str(_PFILE), "--outdir", outdir],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        pytest.fail(Path(log_path).read_text())

    ext_fifo = _find_fifo(outdir, "fanin_ext")
    manual_fifo = _find_fifo(outdir, "sup_manual")

    for i in range(1, k + 1):
        _write_line(ext_fifo, {"type": "DATA", "payload": i})
        time.sleep(0.02)

    time.sleep(0.5)
    _write_line(
        manual_fifo, {"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {}}}
    )
    time.sleep(0.5)
    _write_line(manual_fifo, {"type": "INTERACT", "payload": {"command": "shutdown", "args": {}}})

    assert _wait_for(os.path.join(outdir, "__exec__", "sup", "sup.finished"))

    records = _read_sink_trace(outdir)
    ext_seq = [
        r["payload"]["value"]
        for r in records
        if r.get("type") == "DATA" and r["payload"]["port"] == "ext"
    ]
    loop_seq = [
        r["payload"]["value"]
        for r in records
        if r.get("type") == "DATA" and r["payload"]["port"] == "loop_in"
    ]

    expected = list(range(1, k + 1))
    assert ext_seq == expected
    assert loop_seq == expected
