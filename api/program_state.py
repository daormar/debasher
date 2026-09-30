"""
Whether the output directory of a resident program holds program state (see
"The directories of a resident program" in doc/design_doc_webui.md): what
its nodes keep across runs, from which the next launch resumes them.

The state is found by the names that the engine gives to it, the same that
debasher_reset_resident takes away, and has to change with them: in the
__exec__ directory of each process, the checkpoints, the input log and the
halted marker of each task (with the suffix _<idx> when the process has
more than one task), and what the process left in its output directory,
which the web UI never renames, so that it is <output directory>/<process>.
An empty output directory of a process is no state: the engine creates it
empty before a first run, and debasher_reset_resident leaves it so.
"""

import re
from pathlib import Path

_EXEC_DIRNAME = "__exec__"

_STATE_ENTRY_RE = re.compile(r"^(checkpoints|log|halted)(_\d+)?$")


def has_program_state(output_dir: str) -> bool:
    outdir = Path(output_dir).expanduser()
    exec_dir = outdir / _EXEC_DIRNAME

    if not exec_dir.is_dir():
        return False

    for process_exec_dir in exec_dir.iterdir():
        if not process_exec_dir.is_dir():
            continue
        process_outdir = outdir / process_exec_dir.name
        if process_outdir.is_dir() and any(process_outdir.iterdir()):
            return True
        if any(_STATE_ENTRY_RE.match(entry.name) for entry in process_exec_dir.iterdir()):
            return True

    return False
