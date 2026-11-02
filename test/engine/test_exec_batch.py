"""
Tests that run a batch of runs for real with debasher_exec_batch, as
installed under bin/ by make install: one debasher_exec command per line,
at most a given number at the same time, each run moved to a final
directory and given to a hook once it completes. Like the other real runs,
they are skipped unless DEBASHER_RUN_CHAOS_TEST is set.
"""

import os
import shutil
import subprocess
import time

import pytest

from resident_run import DEBASHER_EXEC, REPO_ROOT, real_run

pytestmark = real_run

DEBASHER_EXEC_BATCH = REPO_ROOT / "bin" / "debasher_exec_batch"
DEBASHER_STATUS = REPO_ROOT / "bin" / "debasher_status"

# A process that sleeps PROBE_SLEEP seconds (1 by default)
SLOW_MODULE = """\
debasher_slow_shared_dirs()
{
    :
}

w_explain_opts()
{
    :
}

w_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

w()
{
    sleep "${PROBE_SLEEP:-1}"
}

debasher_slow_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:05:00"
}
"""

# A process that fails, so that its run under the built-in scheduler ends
# with 3
FAIL_MODULE = """\
debasher_fail_shared_dirs()
{
    :
}

w_explain_opts()
{
    :
}

w_define_opts()
{
    local optlist=""
    save_opt_list optlist
}

w()
{
    return 1
}

debasher_fail_program()
{
    add_debasher_process "w" "cpus=1 mem=32 time=00:01:00"
}
"""


def _modules(tmp_path):
    slow = tmp_path / "debasher_slow.sh"
    slow.write_text(SLOW_MODULE)
    fail = tmp_path / "debasher_fail.sh"
    fail.write_text(FAIL_MODULE)
    return slow, fail


def _command(pfile, outdir, sched="BUILTIN"):
    return f"{DEBASHER_EXEC} --pfile {pfile} --outdir {outdir} --sched {sched}"


def _run_batch(tmp_path, lines, *args, env=None):
    assert DEBASHER_EXEC_BATCH.exists(), "bin/debasher_exec_batch not built: run make install first"
    batch = tmp_path / "batch.txt"
    batch.write_text("".join(f"{line}\n" for line in lines))
    full_env = {**os.environ, "DEBASHER_EXEC_BATCH_POLL_SECS": "1", **(env or {})}
    return subprocess.run(
        [str(DEBASHER_EXEC_BATCH), "-f", str(batch), *args],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=300,
    )


def test_the_runs_of_a_batch_are_moved_given_to_the_hook_and_not_launched_again(tmp_path):
    slow, _ = _modules(tmp_path)
    runs = tmp_path / "runs"
    final = tmp_path / "final"
    final.mkdir()
    hook = tmp_path / "hook.sh"
    hook_log = tmp_path / "hook.log"
    hook.write_text(f'#!/bin/sh\necho "$DEBASHER_EXEC_BATCH_PRG_OUTD" >> {hook_log}\n')
    hook.chmod(0o755)
    lines = [_command(slow, runs / "a"), _command(slow, runs / "b")]

    result = _run_batch(tmp_path, lines, "-m", "1", "-o", str(final), "-k", str(hook))
    assert result.returncode == 0, result.stderr
    assert "All programs successfully completed execution" in result.stderr
    # Each run is moved once it completes, after the hook was given its
    # output directory
    assert sorted(p.name for p in final.iterdir()) == ["a", "b"]
    assert not (runs / "a").exists() and not (runs / "b").exists()
    assert sorted(hook_log.read_text().split()) == [str(runs / "a"), str(runs / "b")]

    # A new launch of the batch finds both runs in the final directory and
    # launches nothing
    again = _run_batch(tmp_path, lines, "-m", "1", "-o", str(final), "-k", str(hook))
    assert again.returncode == 0, again.stderr
    assert "** Execute program..." not in again.stderr
    assert len(hook_log.read_text().split()) == 2


def test_a_run_launched_again_gets_the_hook_again(tmp_path):
    # A process with force=yes runs again in every launch, so that a new
    # launch of the batch, without -o, launches its run again
    forced = tmp_path / "debasher_forced.sh"
    forced.write_text(
        SLOW_MODULE.replace("debasher_slow_", "debasher_forced_").replace(
            '"cpus=1 mem=32 time=00:05:00"', '"cpus=1 mem=32 time=00:05:00" "force=yes"'
        )
    )
    hook = tmp_path / "hook.sh"
    hook_log = tmp_path / "hook.log"
    hook.write_text(f'#!/bin/sh\necho "$DEBASHER_EXEC_BATCH_PRG_OUTD" >> {hook_log}\n')
    hook.chmod(0o755)
    lines = [_command(forced, tmp_path / "runs" / "a")]

    first = _run_batch(tmp_path, lines, "-m", "1", "-k", str(hook))
    assert first.returncode == 0, first.stderr
    again = _run_batch(tmp_path, lines, "-m", "1", "-k", str(hook))
    assert again.returncode == 0, again.stderr
    assert "** Execute program..." in again.stderr
    assert hook_log.read_text().split() == [str(tmp_path / "runs" / "a")] * 2


def test_a_line_without_an_output_directory_stops_the_batch(tmp_path):
    slow, _ = _modules(tmp_path)

    result = _run_batch(tmp_path, [f"{DEBASHER_EXEC} --pfile {slow} --sched BUILTIN"], "-m", "1")
    assert result.returncode == 1
    assert "program command does not contain --outdir option" in result.stderr


def test_a_run_in_progress_from_an_earlier_launch_is_waited_for_not_launched_again(tmp_path):
    slow, _ = _modules(tmp_path)
    outdir = tmp_path / "runs" / "s"
    command = _command(slow, outdir)
    env = {**os.environ, "PROBE_SLEEP": "8"}
    running = subprocess.Popen(command.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = subprocess.run([str(DEBASHER_STATUS), "-d", str(outdir)], capture_output=True)
            if status.returncode == 2:
                break
            time.sleep(0.5)
        assert status.returncode == 2, "the run did not get in progress"

        result = _run_batch(tmp_path, [command], "-m", "1")
    finally:
        running.wait(timeout=60)

    assert result.returncode == 0, result.stderr
    assert "still in progress from an earlier launch: waiting for it" in result.stderr
    assert "another debasher_exec is preparing or running" not in result.stderr
    assert "** Execute program..." not in result.stderr


def test_a_run_that_fails_under_the_builtin_scheduler_is_judged_by_the_tolerance(tmp_path):
    slow, fail = _modules(tmp_path)
    runs = tmp_path / "runs"
    lines = [_command(fail, runs / "f"), _command(slow, runs / "s")]

    # Its debasher_exec ends with 3, which does not stop the batch, and with
    # -u 100 its unfinished process is tolerated
    result = _run_batch(tmp_path, lines, "-m", "1", "-u", "100")
    assert result.returncode == 0, result.stderr
    assert (runs / "s" / "__exec__" / "w").is_dir()


def test_a_failed_run_frees_its_slot_and_is_listed_at_the_end(tmp_path):
    slow, fail = _modules(tmp_path)
    runs = tmp_path / "runs"
    final = tmp_path / "final"
    final.mkdir()
    lines = [_command(fail, runs / "f"), _command(slow, runs / "s")]

    result = _run_batch(tmp_path, lines, "-m", "1", "-o", str(final))
    assert result.returncode == 3, result.stderr
    # The run after it was launched in the slot that it freed, completed and
    # was moved; the failed one stays where it ran
    assert (final / "s").is_dir()
    assert (runs / "f").is_dir() and not (final / "f").exists()
    assert "Warning: 1 programs did not complete execution:" in result.stderr
    assert f"- {runs / 'f'}: more unfinished processes than -u allows" in result.stderr


def test_a_command_that_cannot_be_launched_is_a_failed_run_and_the_others_go_on(tmp_path):
    slow, _ = _modules(tmp_path)
    runs = tmp_path / "runs"
    lines = [_command(tmp_path / "no_such_module.sh", runs / "n"), _command(slow, runs / "s")]

    result = _run_batch(tmp_path, lines, "-m", "1")
    assert result.returncode == 3, result.stderr
    assert (runs / "s" / "__exec__" / "w").is_dir()
    assert f"- {runs / 'n'}: debasher_exec could not launch it (exit status 1)" in result.stderr


@pytest.mark.skipif(shutil.which("sbatch") is None, reason="Slurm is not installed")
def test_under_slurm_a_batch_waits_for_its_runs_and_moves_them(tmp_path):
    slow, _ = _modules(tmp_path)
    runs = tmp_path / "runs"
    final = tmp_path / "final"
    final.mkdir()
    lines = [_command(slow, runs / "a", "SLURM"), _command(slow, runs / "b", "SLURM")]

    # debasher_exec ends once the jobs are submitted; the batch then looks at
    # the runs until each completes
    result = _run_batch(tmp_path, lines, "-m", "1", "-o", str(final))
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in final.iterdir()) == ["a", "b"]
