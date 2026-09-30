"""
Relaunching a node of a resident program without a Supervisor (see
"Running a resident program" in doc/design_doc_webui.md): each task of the process
that is down, and only those, is launched again with debasher_launch_process,
as the Supervisor would do, under the relaunch lock, so that two tabs never
relaunch the same task.

A task is down when it has no .finished file, the mark of a clean end, and
the PID in its .id file no longer exists: the test of the Supervisor, which
never relaunches a node that ended cleanly, as the nodes do in an orderly
stop. The files are read by the names that the engine gives to them, as the
Supervisor does: <process>.id and <process>.finished for a process that runs
as one task, <process>_<idx>.id and <process>_<idx>.finished for each task
of an array.
"""

import fcntl
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import paths, tool_sessions

RELAUNCH_LOCK_NAME = ".debasher_webui_relaunch.lock"

# How long to wait, after debasher_stop, for every task of a restarted
# process to be gone before relaunching it.
_DOWN_TIMEOUT_SECS = 10


@dataclass
class Task:
    # The file stem of the task, as the engine names its files: <process> or
    # <process>_<idx>.
    stem: str
    # The task index to give debasher_launch_process, None for a process
    # that runs as one task.
    index: int | None
    pid_file: Path


@dataclass
class RelaunchResult:
    # The tasks relaunched, as <process> or <process>:<idx>.
    relaunched: list[str]
    output: str
    # 0 when every relaunch succeeded, the first exit code that was not 0
    # otherwise.
    exit_code: int


def _tasks(output_dir: str, process_name: str) -> list[Task]:
    exec_dir = Path(output_dir).expanduser() / "__exec__" / process_name
    if not exec_dir.is_dir():
        return []

    index_re = re.compile(rf"^{re.escape(process_name)}_(\d+)\.id$")
    tasks = []
    for entry in sorted(exec_dir.iterdir()):
        if entry.name == f"{process_name}.id":
            tasks.append(Task(process_name, None, entry))
        else:
            match = index_re.match(entry.name)
            if match:
                tasks.append(Task(entry.name[: -len(".id")], int(match.group(1)), entry))
    return tasks


def _pid_exists(task: Task) -> bool | None:
    """Whether the PID of the task exists; None when its .id file gives no
    PID."""
    try:
        pid = int(task.pid_file.read_text().strip())
    except (OSError, ValueError):
        return None

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ended_cleanly(task: Task) -> bool:
    return (task.pid_file.parent / f"{task.stem}.finished").exists()


def _is_down(task: Task) -> bool:
    """True only when the task did not end cleanly and its PID is known and
    no longer exists."""
    return not _ended_cleanly(task) and _pid_exists(task) is False


def _task_label(process_name: str, task: Task) -> str:
    return process_name if task.index is None else f"{process_name}:{task.index}"


@contextmanager
def relaunch_lock(output_dir: str) -> Iterator[None]:
    """Hold the relaunch lock of the output directory."""
    lock_path = Path(output_dir).expanduser() / RELAUNCH_LOCK_NAME
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def relaunch_down_tasks(output_dir: str, process_name: str, env: dict[str, str]) -> RelaunchResult:
    """
    Relaunch each task of `process_name` that is down. The caller holds the
    relaunch lock.
    """
    tool = paths.find_libexec_tool("debasher_launch_process")
    if tool is None:
        return RelaunchResult([], "Error: debasher_launch_process tool not found.", 1)

    relaunched: list[str] = []
    outputs: list[str] = []
    exit_code = 0

    for task in _tasks(output_dir, process_name):
        if not _is_down(task):
            continue
        command = [str(tool), "-d", output_dir, "-p", process_name]
        if task.index is not None:
            command += ["-t", str(task.index)]
        output, task_exit_code = tool_sessions.run_with_temp_output(command, env)
        outputs.append(output)
        if task_exit_code == 0:
            relaunched.append(_task_label(process_name, task))
        elif exit_code == 0:
            exit_code = task_exit_code

    return RelaunchResult(relaunched, "".join(outputs), exit_code)


def wait_until_down(output_dir: str, process_name: str, timeout_secs: float = _DOWN_TIMEOUT_SECS) -> bool:
    """Wait until no task of `process_name` runs. Returns False if some task
    still runs once `timeout_secs` have passed."""
    deadline = time.monotonic() + timeout_secs
    while True:
        tasks = _tasks(output_dir, process_name)
        if not any(_pid_exists(task) for task in tasks):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
