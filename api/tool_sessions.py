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

import subprocess
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
