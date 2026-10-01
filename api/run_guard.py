"""
The guard against changing a program under a run in progress, shared by
every endpoint that writes the program metadata and the generated script
or deletes what a run left.

The engine reads the generated script again each time it starts a process,
so writing it during a run would leave the processes already started on one
version and the rest on another, and deleting the output directory during a
run would take files from processes that still use them. The frontend
refuses these actions too, but a request may come from another tab or from
another client of the backend, so the backend checks again, with
debasher_status, which sees a run whoever launched it.
"""

import os
import subprocess

from fastapi import HTTPException

from . import paths, persistence
from .models import Program

# The exit code with which debasher_status reports a run in progress.
STATUS_IN_PROGRESS = 2


def run_in_progress(output_dir: str, debasher_mod_dir: str) -> bool:
    """
    Whether debasher_status reports a run in progress in `output_dir`. A
    blank directory, or no debasher_status to ask, holds none.
    """
    if not output_dir.strip():
        return False

    tool = paths.find_bin_tool("debasher_status")
    if tool is None:
        return False

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = debasher_mod_dir
    result = subprocess.run(
        [str(tool), "-d", output_dir], env=env, capture_output=True, text=True
    )
    return result.returncode == STATUS_IN_PROGRESS


def _saved_output_dir(home_dir: str) -> str:
    """
    The output directory that the program metadata in `home_dir` records,
    or "" when there is none.
    """
    return str((persistence.read_raw_metadata(home_dir) or {}).get("outputDir", "") or "")


def refuse_while_running(program: Program, action: str, home_dir: str | None = None) -> None:
    """
    Refuse `action` (in words, "save the program") with a conflict when a run
    is in progress in the program's output directory or, when `home_dir` is
    given, in the output directory that the program metadata there records:
    a save that changes the output directory still writes the script that a
    run in the old one reads.
    """
    debasher_mod_dir = program.envVars.get("DEBASHER_MOD_DIR", "")

    if run_in_progress(program.outputDir, debasher_mod_dir):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot {action} while a run is in progress for this output "
                f"directory. Wait for the run to finish, or stop it first."
            ),
        )

    if home_dir is None:
        return

    saved = _saved_output_dir(home_dir)
    if (
        saved.strip()
        and not persistence.same_dir(saved, program.outputDir)
        and run_in_progress(saved, debasher_mod_dir)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot {action} while a run is in progress in {saved}, the "
                f"output directory that the saved program names: that run "
                f"reads the script that this would write. Wait for the run to "
                f"finish, or stop it first."
            ),
        )
