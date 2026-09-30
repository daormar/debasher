"""
The launch record of a resident program (see "The directories of a resident
program" in doc/design_doc_webui.md): what every launch from the web UI that
ends well leaves in the output directory, against which the next launch
compares the program before resuming the program state.

The record holds the generated script of the program with every description
left out (of the program, of its processes and of their options), so that a
change of a description asks nothing, and the program options as they were
given on the command line. The positions on the canvas are not in the
script. A change in a module that the preamble loads goes unseen.
"""

import json
import os
import tempfile
from pathlib import Path

from .models import Program
from .script_generation import generate_script

RECORD_NAME = ".debasher_webui_launch_record.json"


def compared_script(program: Program) -> str:
    """The generated script of `program` with every description left out."""
    stripped = program.model_copy(deep=True)
    stripped.description = ""
    for process in stripped.processes:
        process.description = ""
        for option in process.options:
            option.description = ""
    return generate_script(stripped)


def _record(program: Program, option_args: list[str]) -> dict:
    return {"script": compared_script(program), "programOptions": option_args}


def _record_path(output_dir: str) -> Path:
    return Path(output_dir).expanduser() / RECORD_NAME


def read(output_dir: str) -> dict | None:
    """The launch record of the output directory, or None when there is none
    or it cannot be read."""
    try:
        record = json.loads(_record_path(output_dir).read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def differs(record: dict, program: Program, option_args: list[str]) -> bool:
    """Whether `program`, launched with `option_args`, differs from the one
    that left `record`."""
    return record != _record(program, option_args)


def write(output_dir: str, program: Program, option_args: list[str]) -> None:
    """Write the launch record, replacing the previous one at once, so that a
    reader never sees half of it."""
    path = _record_path(output_dir)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{RECORD_NAME}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as tmp:
            json.dump(_record(program, option_args), tmp)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
