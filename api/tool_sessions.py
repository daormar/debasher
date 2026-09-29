"""
Running an engine tool that acts on a live resident program (see "A program
that outlives the tab" in doc/design_doc_webui.md), so that nothing that
happens to the backend stops the program or cuts the tool in the middle.

The tool runs in a session of its own: a signal meant for the server, such
as the interrupt of its terminal, reaches neither the tool nor what the tool
launches, which inherits its session. And it writes into a file, never into
a pipe: a tool whose output goes into a pipe read by the backend dies of
SIGPIPE at its next line once the backend is gone, and a pipe would also be
inherited by the processes that the tool launches, so that waiting for its
end would mean waiting for theirs.
"""

import os
import subprocess
import tempfile
from pathlib import Path


def run_in_own_session(command: list[str], env: dict[str, str], output_path: Path) -> int:
    """
    Run `command` in a session of its own, with its standard output and
    error written into `output_path`, and wait for it to end. Returns its
    exit code; what it printed is left in `output_path` for the caller to
    read.
    """
    with open(output_path, "w") as output:
        result = subprocess.run(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    return result.returncode


def start_detached(command: list[str], env: dict[str, str], output_path: Path) -> None:
    """
    Start `command` in a session of its own, with its standard output and
    error written into `output_path`, and return without waiting for it:
    the backend keeps nothing of it.
    """
    with open(output_path, "w") as output:
        subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def run_with_temp_output(command: list[str], env: dict[str, str]) -> tuple[str, int]:
    """
    Run `command` as run_in_own_session does, with its output in a
    temporary file of its own, since two tabs may run the same tool at the
    same time. Returns what it printed and its exit code, and deletes the
    file. A file that is not deleted, because the backend went away before
    the tool ended, stays in the temporary directory of the system, with no
    other effect.
    """
    fd, name = tempfile.mkstemp(prefix="debasher_webui_", suffix=".log")
    os.close(fd)
    output_path = Path(name)

    try:
        exit_code = run_in_own_session(command, env, output_path)
        return output_path.read_text(errors="replace"), exit_code
    finally:
        output_path.unlink(missing_ok=True)
