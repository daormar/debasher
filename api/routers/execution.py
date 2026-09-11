import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import paths, persistence
from ..models import Program

router = APIRouter(prefix="/api/execution", tags=["execution"])

# debasher_status's own exit codes (see engine/debasher_lib.sh /
# engine/debasher_status.sh): 0 once every process has finished, 2 while
# at least one is still running, 3 otherwise (not all processes finished
# correctly).
ProgramState = Literal["finished", "in-progress", "unfinished"]

_STATE_BY_EXIT_CODE: dict[int, ProgramState] = {
    0: "finished",
    2: "in-progress",
}


# Applies everywhere the "Inspect execution" context menu shows a
# file's worth of text — stdout, scheduler output, options, and a "Show
# inputs and outputs" > "View" path (see _read_text_capped, which caps
# the same way but streams a path instead of an in-memory string) —
# so none of them can ship an arbitrarily large response to the
# browser.
_MAX_INSPECT_LINES = 10_000


def _cap_lines(text: str, max_lines: int = _MAX_INSPECT_LINES) -> str:
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text

    return (
        f"Warning: output has more than {max_lines} lines — "
        f"showing only the first {max_lines}.\n\n"
    ) + "".join(lines[:max_lines])


def _debasher_env(program: Program) -> dict[str, str]:
    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = program.envVars.get("DEBASHER_MOD_DIR", "")
    return env


def _command_line_option_types(program: Program) -> dict[str, str]:
    types: dict[str, str] = {}
    for process in program.processes:
        for option in process.options:
            if option.commandLine and option.label not in types:
                types[option.label] = option.dataType
    return types


def _prepare_debasher_exec_command(program: Program, mode_flag: str) -> list[str] | None:
    """
    Save `program` to its home directory (the same as pressing "Save"
    in the toolbar, generating its .sh file there) and build the
    debasher_exec command line for it, passing the scheduler, the run
    output directory, and the command line options set via "Set
    program options".

    Returns None if debasher_exec isn't found.
    """
    persistence.save_program(program.homeDir, program)
    script_path = persistence.save_script(program.homeDir, program)

    tool = paths.find_bin_tool("debasher_exec")
    if tool is None:
        return None

    command = [
        str(tool),
        "--pfile", str(script_path),
        "--outdir", program.outputDir,
        "--sched", program.executionOptions.scheduler,
        mode_flag,
    ]

    option_types = _command_line_option_types(program)
    for label, value in program.programOptions.items():
        if option_types.get(label) == "None":
            if value:
                command.append(label)
        else:
            command += [label, value]

    return command


def _run_debasher_exec(program: Program, mode_flag: str) -> str:
    command = _prepare_debasher_exec_command(program, mode_flag)
    if command is None:
        return "Error: debasher_exec tool not found."

    result = subprocess.run(command, env=_debasher_env(program), capture_output=True, text=True)

    return result.stdout + result.stderr


def _run_debasher_dir_tool(program: Program, tool_name: str) -> tuple[str, int]:
    """
    Run a DeBasher bin tool that just takes "-d <outputDir>" (e.g.
    debasher_status, debasher_stop). Returns (combined output, exit code).
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found.", 1

    command = [str(tool), "-d", program.outputDir]

    result = subprocess.run(command, env=_debasher_env(program), capture_output=True, text=True)

    return result.stdout + result.stderr, result.returncode


def _get_program_state(program: Program) -> tuple[ProgramState, str]:
    output, returncode = _run_debasher_dir_tool(program, "debasher_status")
    return _STATE_BY_EXIT_CODE.get(returncode, "unfinished"), output


def _run_debasher_process_tool(
    program: Program,
    tool_name: str,
    process_name: str,
    task_index: int | None = None,
) -> str:
    """
    Run a DeBasher bin tool that takes "-d <outputDir> -p <processName>
    [-t <taskIndex>]" (debasher_get_stdout, debasher_get_sched_out).
    `task_index` selects one task's file for an array/generator/manual
    process that ran as more than one task (see get_process_tasks);
    omit it for a "standard" one-file process. Returns the combined
    output — including the tool's own "file could not be found" error,
    e.g. for a process that hasn't produced one yet — capped at
    _MAX_INSPECT_LINES lines.
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found."

    command = [str(tool), "-d", program.outputDir, "-p", process_name]
    if task_index is not None:
        command += ["-t", str(task_index)]

    result = subprocess.run(command, env=_debasher_env(program), capture_output=True, text=True)

    return _cap_lines(result.stdout + result.stderr)


# Matches "<processName>_<idx>.stdout" / "<processName>_<idx>.sched_out" /
# "<processName>_<idx>.opts" (see engine/debasher_lib_processes.sh's
# _get_process_stdout_filename/_get_process_schedout_filename/
# _get_process_opts_filename) — the per-task files an array/generator/
# manual process produces when it runs as more than one task, as
# opposed to a "standard" process's single
# "<processName>.stdout"/"<processName>.sched_out"/"<processName>.opts".
def _task_indices_for_process(outdir: str, process_name: str) -> list[int]:
    exec_dir = Path(outdir).expanduser() / "__exec__" / process_name

    if not exec_dir.is_dir():
        return []

    prefix = f"{process_name}_"
    indices: set[int] = set()

    # A directory listing stays cheap even for the many thousands of
    # files a large task array can leave behind — unlike shelling out
    # to a DeBasher tool per task, which is what makes listing them
    # this way (rather than, say, probing task indices one by one)
    # the right approach at that scale.
    for entry in exec_dir.iterdir():
        name = entry.name
        if not name.startswith(prefix):
            continue

        suffix = name[len(prefix):]
        for ext in (".stdout", ".sched_out", ".opts"):
            if suffix.endswith(ext):
                idx_str = suffix[: -len(ext)]
                if idx_str.isdigit():
                    indices.add(int(idx_str))
                break

    return sorted(indices)


# Matches debasher_status's per-process lines (see
# engine/debasher_status.sh's process_status_for_pfile): "PROCESS: <name>
# ; STATUS: <status>", optionally followed by "; SCHED_IDS: ..." (not
# requested here, but tolerated).
_PROCESS_STATUS_LINE_RE = re.compile(r"^PROCESS:\s*(\S+)\s*;\s*STATUS:\s*(\S+)")


def _parse_process_statuses(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        match = _PROCESS_STATUS_LINE_RE.match(line.strip())
        if match:
            statuses[match.group(1)] = match.group(2)
    return statuses


class ListSchedulersResponse(BaseModel):
    schedulers: list[str]


@router.get("/schedulers", response_model=ListSchedulersResponse)
def list_schedulers() -> ListSchedulersResponse:
    """
    List the schedulers a program can be executed with.

    Stub: always returns the two schedulers DeBasher supports.

    TODO: replace with real logic, e.g. checking which scheduler
    binaries (sbatch, ...) are actually available on the host.
    """
    return ListSchedulersResponse(schedulers=["SLURM", "BUILTIN"])


class RunProgramResponse(BaseModel):
    started: bool


@router.post("/run", response_model=RunProgramResponse)
def run_program(program: Program) -> RunProgramResponse:
    """
    Launch a program run (debasher_exec --wait) in the background and
    return immediately. Poll /status to find out when it's done.
    """
    state, _ = _get_program_state(program)
    if state == "in-progress":
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress for this output directory.",
        )

    command = _prepare_debasher_exec_command(program, "--wait")
    if command is None:
        raise HTTPException(status_code=500, detail="debasher_exec tool not found.")

    log_path = Path(program.outputDir).expanduser() / ".debasher_webui_run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log_file:
        subprocess.Popen(
            command,
            env=_debasher_env(program),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    return RunProgramResponse(started=True)


class RunProgramDebugResponse(BaseModel):
    output: str


@router.post("/run-debug", response_model=RunProgramDebugResponse)
def run_program_debug(program: Program) -> RunProgramDebugResponse:
    """
    Run a program in debug mode (debasher_exec --debug).
    """
    return RunProgramDebugResponse(output=_run_debasher_exec(program, "--debug"))


class ProgramStatusResponse(BaseModel):
    output: str
    state: ProgramState


@router.post("/status", response_model=ProgramStatusResponse)
def get_program_status(program: Program) -> ProgramStatusResponse:
    """
    Get a program's status (debasher_status -d <outputDir>).
    """
    state, output = _get_program_state(program)
    return ProgramStatusResponse(output=output, state=state)


class ProcessStatusesResponse(BaseModel):
    statuses: dict[str, str]


@router.post("/process-statuses", response_model=ProcessStatusesResponse)
def get_process_statuses(program: Program) -> ProcessStatusesResponse:
    """
    Get each process's individual status (debasher_status -d
    <outputDir>, parsed per-process), used to color nodes in the canvas.

    Returns an empty map whenever debasher_status has nothing to report
    (e.g. the output directory hasn't been initialized by a run yet, or
    the tool isn't found) rather than raising, so the frontend can poll
    this unconditionally and simply show no color in that case.
    """
    output, _ = _run_debasher_dir_tool(program, "debasher_status")
    return ProcessStatusesResponse(statuses=_parse_process_statuses(output))


class ProcessTasksRequest(BaseModel):
    program: Program
    processName: str


class ProcessTasksResponse(BaseModel):
    # Empty for a "standard" one-task process; the list of task
    # indices found (not necessarily contiguous — a task still
    # running, or that never produced output, leaves a gap) otherwise.
    taskIndices: list[int]


@router.post("/process-tasks", response_model=ProcessTasksResponse)
def get_process_tasks(request: ProcessTasksRequest) -> ProcessTasksResponse:
    """
    List the task indices that have a stdout or scheduler-output file
    for `processName`, for the "Inspect execution" menu's task picker
    (skipped when this comes back empty — a "standard" process's
    single file needs no index).
    """
    return ProcessTasksResponse(
        taskIndices=_task_indices_for_process(request.program.outputDir, request.processName)
    )


class ProcessOutputRequest(BaseModel):
    program: Program
    processName: str
    # Selects one task's file for an array/generator/manual process
    # that ran as more than one task (see /process-tasks); omit for a
    # "standard" one-file process.
    taskIndex: int | None = None


class ProcessOutputResponse(BaseModel):
    output: str


@router.post("/process-stdout", response_model=ProcessOutputResponse)
def get_process_stdout(request: ProcessOutputRequest) -> ProcessOutputResponse:
    """
    Get a process's captured stdout (debasher_get_stdout -d <outputDir>
    -p <processName> [-t <taskIndex>]), for the canvas's right-click
    "Inspect execution" menu.
    """
    output = _run_debasher_process_tool(
        request.program, "debasher_get_stdout", request.processName, request.taskIndex
    )
    return ProcessOutputResponse(output=output)


@router.post("/process-sched-out", response_model=ProcessOutputResponse)
def get_process_sched_out(request: ProcessOutputRequest) -> ProcessOutputResponse:
    """
    Get a process's scheduler output (debasher_get_sched_out -d
    <outputDir> -p <processName> [-t <taskIndex>]), for the canvas's
    right-click "Inspect execution" menu.
    """
    output = _run_debasher_process_tool(
        request.program, "debasher_get_sched_out", request.processName, request.taskIndex
    )
    return ProcessOutputResponse(output=output)


# There's no "debasher_get_opts" bin tool (unlike stdout/sched-out) — the
# ".opts" file (see engine/debasher_lib_processes.sh's
# _get_process_opts_filename and debasher_lib_opts.sh's
# _print_opts_as_qstrings) is read directly, the same way
# _task_indices_for_process already reads __exec__ directly.
def _get_process_opts_path(outdir: str, process_name: str, task_index: int | None) -> Path:
    exec_dir = Path(outdir).expanduser() / "__exec__" / process_name
    if task_index is None:
        return exec_dir / f"{process_name}.opts"
    return exec_dir / f"{process_name}_{task_index}.opts"


@router.post("/process-opts", response_model=ProcessOutputResponse)
def get_process_opts(request: ProcessOutputRequest) -> ProcessOutputResponse:
    """
    Get a process's resolved command-line options, one `printf '%q'`
    escaped option/value per line, from its ".opts" file, for the
    canvas's right-click "Inspect execution" menu's "See options" —
    capped at _MAX_INSPECT_LINES lines.
    """
    opts_path = _get_process_opts_path(
        request.program.outputDir, request.processName, request.taskIndex
    )
    try:
        output = _read_text_capped(opts_path)
    except OSError:
        output = f"Error: options file for process {request.processName} could not be found!"

    return ProcessOutputResponse(output=output)


# Each ".opts" line is one option, `printf '%q'`-escaped and (when it
# has a value) shell-word-split from its value — e.g. `-i input\ file`
# or `--flag`. shlex.split undoes that quoting, giving back the actual
# flag/value strings the process ran with.
def _parse_opts_file(opts_path: Path) -> dict[str, str]:
    if not opts_path.is_file():
        return {}

    values: dict[str, str] = {}
    for line in opts_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if tokens:
            values[tokens[0]] = tokens[1] if len(tokens) > 1 else ""

    return values


class ProcessResolvedOptionsResponse(BaseModel):
    # {option label: resolved value} from the process's own ".opts"
    # file — empty when the program hasn't produced one yet (e.g. it
    # hasn't been run).
    values: dict[str, str]


@router.post("/process-resolved-options", response_model=ProcessResolvedOptionsResponse)
def get_process_resolved_options(request: ProcessOutputRequest) -> ProcessResolvedOptionsResponse:
    """
    Parse a process's ".opts" file into a {label: value} map, for the
    canvas's right-click "Inspect execution" menu's "Show inputs and
    outputs" — this is how a fifo/shared-dir/value-descriptor option's
    actual resolved value (rather than the program model's own
    possibly-unresolved `value` field) gets shown.
    """
    opts_path = _get_process_opts_path(
        request.program.outputDir, request.processName, request.taskIndex
    )
    return ProcessResolvedOptionsResponse(values=_parse_opts_file(opts_path))


class InspectPathRequest(BaseModel):
    path: str


class InspectPathResponse(BaseModel):
    kind: Literal["file", "binary", "directory", "missing"]
    content: str | None = None
    # Directory listing entries, each name suffixed with "/" when it is
    # itself a subdirectory.
    entries: list[str] | None = None


# Sniffs the first chunk of a file the same way `file`/git do: a NUL
# byte, or a decode failure, means it isn't text worth dumping into the
# "Show inputs and outputs" modal.
def _looks_binary(path: Path, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
    except OSError:
        return False

    if b"\x00" in chunk:
        return True

    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True

    return False


# Reads at most `max_lines` lines, without loading a much larger file
# into memory first just to find out it's too big — same cap and
# warning wording as _cap_lines, just streamed from a path instead of
# an in-memory string.
def _read_text_capped(path: Path, max_lines: int = _MAX_INSPECT_LINES) -> str:
    lines: list[str] = []
    truncated = False

    with path.open("r", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                truncated = True
                break
            lines.append(line)

    content = "".join(lines)
    if truncated:
        content = (
            f"Warning: file has more than {max_lines} lines — "
            f"showing only the first {max_lines}.\n\n"
        ) + content

    return content


@router.post("/inspect-path", response_model=InspectPathResponse)
def inspect_path(request: InspectPathRequest) -> InspectPathResponse:
    """
    Inspect a resolved option's value as a filesystem path, for the
    "Show inputs and outputs" modal's per-option "View" button: a file's
    content (kind="binary" and no content when it doesn't look like
    text; truncated with a leading warning past _MAX_INSPECT_LINES
    lines), or a directory's listing (likewise truncated).
    """
    resolved = Path(request.path).expanduser()

    if resolved.is_dir():
        entries = sorted(
            f"{entry.name}/" if entry.is_dir() else entry.name
            for entry in resolved.iterdir()
        )
        if len(entries) > _MAX_INSPECT_LINES:
            total = len(entries)
            entries = entries[:_MAX_INSPECT_LINES]
            entries.insert(
                0,
                f"Warning: directory has {total} entries — "
                f"showing only the first {_MAX_INSPECT_LINES}.",
            )
        return InspectPathResponse(kind="directory", entries=entries)

    if resolved.is_file():
        if _looks_binary(resolved):
            return InspectPathResponse(kind="binary")

        try:
            content = _read_text_capped(resolved)
        except OSError as e:
            content = f"Error: could not read file: {e}"
        return InspectPathResponse(kind="file", content=content)

    return InspectPathResponse(kind="missing")


class CheckProgramOptionsResponse(BaseModel):
    output: str


@router.post("/check-program-options", response_model=CheckProgramOptionsResponse)
def check_program_options(program: Program) -> CheckProgramOptionsResponse:
    """
    Check a program's command line options (debasher_exec --check-proc-opts).
    """
    return CheckProgramOptionsResponse(
        output=_run_debasher_exec(program, "--check-proc-opts")
    )


class StopProgramResponse(BaseModel):
    output: str


@router.post("/stop", response_model=StopProgramResponse)
def stop_program(program: Program) -> StopProgramResponse:
    """
    Stop a running program (debasher_stop -d <outputDir>).
    """
    output, _ = _run_debasher_dir_tool(program, "debasher_stop")
    return StopProgramResponse(output=output)


class ResetOutputDirResponse(BaseModel):
    # False whenever a guard below made this a no-op — the caller can
    # tell the user there was nothing to reset.
    cleared: bool


@router.post("/reset-output-dir", response_model=ResetOutputDirResponse)
def reset_output_dir(program: Program) -> ResetOutputDirResponse:
    """
    Delete everything inside program.outputDir (the directory itself is
    kept), for the Run menu's "Reset output directory" action.

    Guards against a mistaken mass deletion: a no-op (cleared=False,
    nothing raised) whenever outputDir is blank — an empty string would
    otherwise resolve to the server's current directory, not "nowhere"
    — doesn't resolve to an existing directory, or resolves to the
    filesystem root or the server user's home directory (the two paths
    a corrupted/mistaken outputDir would do the most damage at).
    """
    outdir = program.outputDir.strip()
    if not outdir:
        return ResetOutputDirResponse(cleared=False)

    resolved = Path(outdir).expanduser().resolve()

    if not resolved.is_dir():
        return ResetOutputDirResponse(cleared=False)

    if resolved == Path(resolved.root) or resolved == Path.home():
        return ResetOutputDirResponse(cleared=False)

    try:
        for entry in resolved.iterdir():
            # A symlink is removed as itself, never followed — so a
            # symlink into another directory can't cause this to
            # recurse and delete outside outputDir.
            if entry.is_symlink() or not entry.is_dir():
                entry.unlink()
            else:
                shutil.rmtree(entry)
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reset output directory: {e}"
        ) from e

    return ResetOutputDirResponse(cleared=True)
