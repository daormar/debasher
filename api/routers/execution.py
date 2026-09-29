import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import file_inspection, launch_record, node_relaunch, paths, persistence, program_state, tool_sessions
from ..models import Program
from ..resident_supervisor_wiring import NO_HOLD_FIFOS_LABEL

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


def _cap_lines(text: str, max_lines: int = file_inspection.MAX_INSPECT_LINES) -> str:
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text

    return (
        f"Warning: output has more than {max_lines} lines, "
        f"showing only the first {max_lines}.\n\n"
    ) + "".join(lines[:max_lines])


def _debasher_env(program: Program) -> dict[str, str]:
    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = program.envVars.get("DEBASHER_MOD_DIR", "")
    return env


def _is_resident(program: Program) -> bool:
    return program.programType == "resident"


def _command_line_option_types(program: Program) -> dict[str, str]:
    types: dict[str, str] = {}
    for process in program.processes:
        for option in process.options:
            if option.commandLine and option.label not in types:
                types[option.label] = option.dataType
    # The flag of the Supervisor is not in the program model: script
    # generation writes it with the rest of the Supervisor.
    if _is_resident(program) and any(p.nodeKind == "Supervisor" for p in program.processes):
        types.setdefault(NO_HOLD_FIFOS_LABEL, "None")
    return types


def _execution_option_flags(program: Program) -> list[str]:
    """
    The debasher_exec flags of the execution options. The engine forces the
    built-in scheduler in oneshot mode on a resident program, and refuses
    any other scheduler, so a resident program is given only the limits of
    the built-in scheduler: every other flag is either meant for the Slurm
    scheduler or for general programs, or would keep some task of a node
    from running at once.
    """
    exec_opts = program.executionOptions

    if _is_resident(program):
        flags = ["--sched", "BUILTIN"]
    else:
        flags = ["--sched", exec_opts.scheduler]

    if exec_opts.builtinSchedCpus:
        flags += ["--builtinsched-cpus", exec_opts.builtinSchedCpus]
    if exec_opts.builtinSchedMem:
        flags += ["--builtinsched-mem", exec_opts.builtinSchedMem]

    if _is_resident(program):
        return flags

    if exec_opts.dfltNodes:
        flags += ["--dflt-nodes", exec_opts.dfltNodes]
    if exec_opts.dfltThrottle:
        flags += ["--dflt-throttle", exec_opts.dfltThrottle]
    if exec_opts.rerunOutdatedProcs:
        flags.append("--rerun-outdated-procs")
    if exec_opts.condaSupport:
        flags.append("--conda-support")
    if exec_opts.dockerSupport:
        flags.append("--docker-support")

    return flags


def _prepare_debasher_exec_command(program: Program, mode_flag: str | None) -> list[str] | None:
    """
    Save `program` to its home directory (the same as pressing "Save"
    in the toolbar, generating its .sh file there) and build the
    debasher_exec command line for it, passing the scheduler, the run
    output directory, the other execution options, `mode_flag` when
    given, and the command line options set via "Set program options".

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
        *_execution_option_flags(program),
    ]

    if mode_flag is not None:
        command.append(mode_flag)

    return command + _program_option_args(program)


def _program_option_args(program: Program) -> list[str]:
    """The program options as debasher_exec is given them: each label
    followed by its value, except a flag, which is given alone when its value
    is not empty and left out otherwise."""
    args: list[str] = []
    option_types = _command_line_option_types(program)
    for label, value in program.programOptions.items():
        if option_types.get(label) == "None":
            if value:
                args.append(label)
        else:
            args += [label, value]
    return args


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


def _run_debasher_dir_tool_in_own_session(
    program: Program, tool_name: str, extra_args: list[str] | None = None
) -> tuple[str, int]:
    """
    Run a DeBasher bin tool that takes "-d <outputDir>" and acts on a live
    resident program (debasher_stop_resident, debasher_stop,
    debasher_snapshot_resident), in a session
    of its own and with its output in a temporary file, so that the backend
    going away cannot cut it in the middle. `extra_args` follow "-d
    <outputDir>". Returns (output, exit code).
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found.", 1

    output, exit_code = tool_sessions.run_with_temp_output(
        [str(tool), "-d", program.outputDir, *(extra_args or [])], _debasher_env(program)
    )
    return _cap_lines(output), exit_code


def _get_program_state(program: Program) -> tuple[ProgramState, str]:
    output, returncode = _run_debasher_dir_tool(program, "debasher_status")
    return _STATE_BY_EXIT_CODE.get(returncode, "unfinished"), output


def _run_debasher_process_tool(
    program: Program,
    tool_name: str,
    process_name: str,
    task_index: int | None = None,
    extra_args: list[str] | None = None,
) -> str:
    """
    Run a DeBasher bin tool that takes "-d <outputDir> -p <processName>
    [-t <taskIndex>]" (debasher_get_stdout, debasher_get_sched_out,
    debasher_get_fifo_mirror). `task_index` selects one task's file for
    an array/generator/manual process that ran as more than one task
    (see get_process_tasks); omit it for a "standard" one-file process.
    `extra_args` appends any further flags a specific tool needs (e.g.
    debasher_get_fifo_mirror's "-f <fifoName>") after "-t". Returns the
    combined output, including the tool's own "file could not be
    found" error, e.g. for a process that hasn't produced one yet, capped at _MAX_INSPECT_LINES lines.
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found."

    command = [str(tool), "-d", program.outputDir, "-p", process_name]
    if task_index is not None:
        command += ["-t", str(task_index)]
    if extra_args:
        command += extra_args

    result = subprocess.run(command, env=_debasher_env(program), capture_output=True, text=True)

    return _cap_lines(result.stdout + result.stderr)


# Matches "<processName>_<idx>.stdout" / "<processName>_<idx>.sched_out" /
# "<processName>_<idx>.opts" (see engine/debasher_lib_processes.sh's
# _get_process_stdout_filename/_get_process_schedout_filename/
# _get_process_opts_filename), the per-task files an array/generator/
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
    # files a large task array can leave behind, unlike shelling out
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
    # Only for a resident program, whose launch /run waits for: the exit
    # code of debasher_exec and what it printed, capped at
    # MAX_INSPECT_LINES lines.
    exitCode: int | None = None
    output: str | None = None


_RUN_LOG_NAME = ".debasher_webui_run.log"

_SNAPSHOT_LOG_NAME = ".debasher_webui_snapshots.log"


def _run_log_path(program: Program) -> Path:
    log_path = Path(program.outputDir).expanduser() / _RUN_LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def _snapshot_period(program: Program) -> str | None:
    """The period of the periodic snapshots of a resident program, or None
    for none; a period that is not a positive number of seconds is refused
    before anything is launched."""
    period = program.executionOptions.snapshotEverySecs.strip()
    if not period:
        return None
    if not period.isdigit() or int(period) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"The snapshot period must be a positive number of seconds, not '{period}'.",
        )
    return period


def _start_periodic_snapshots(program: Program, period: str) -> None:
    """
    Start debasher_snapshot_resident --every <period> on the output
    directory, detached, in a session of its own and with its output in the
    snapshot log. The tool ends by itself once no node of the program runs,
    whatever stopped the program, so nothing has to stop it.
    """
    tool = paths.find_bin_tool("debasher_snapshot_resident")
    if tool is None:
        raise HTTPException(status_code=500, detail="debasher_snapshot_resident tool not found.")

    tool_sessions.start_detached(
        [str(tool), "-d", program.outputDir, "--every", period],
        _debasher_env(program),
        Path(program.outputDir).expanduser() / _SNAPSHOT_LOG_NAME,
    )


def _launch_resident_program(command: list[str], program: Program) -> RunProgramResponse:
    """
    Run debasher_exec on a resident program to its end, which comes as soon
    as every process is launched, so that a launch that the engine refuses
    is reported at once. It runs in a session of its own and writes into the
    run log, which is read once it ends: a pipe would be inherited by the
    processes it launches, and waiting for its end would mean waiting for
    theirs. Once it has ended with 0, the periodic snapshots start, when the
    program has a period for them.
    """
    period = _snapshot_period(program)

    log_path = _run_log_path(program)
    exit_code = tool_sessions.run_in_own_session(command, _debasher_env(program), log_path)
    output = _cap_lines(log_path.read_text(errors="replace"))

    if exit_code == 0:
        # Only a launch that ended well leaves its record: after a failed
        # one, the program state may still be that of the previous record,
        # which has to stay so that the next launch asks again.
        launch_record.write(program.outputDir, program, _program_option_args(program))
        if period is not None:
            _start_periodic_snapshots(program, period)

    return RunProgramResponse(started=exit_code == 0, exitCode=exit_code, output=output)


class LaunchCheckResponse(BaseModel):
    hasProgramState: bool
    hasLaunchRecord: bool
    # Whether the launch has to ask first: there is program state, and no
    # launch record or one that differs from the program.
    needsConfirmation: bool


def _launch_check(program: Program) -> LaunchCheckResponse:
    has_state = program_state.has_program_state(program.outputDir)
    record = launch_record.read(program.outputDir)
    needs_confirmation = has_state and (
        record is None or launch_record.differs(record, program, _program_option_args(program))
    )
    return LaunchCheckResponse(
        hasProgramState=has_state,
        hasLaunchRecord=record is not None,
        needsConfirmation=needs_confirmation,
    )


@router.post("/launch-check", response_model=LaunchCheckResponse)
def launch_check(program: Program) -> LaunchCheckResponse:
    """
    Whether "Run program" on a resident program has to ask before launching:
    the output directory holds program state, and the program differs from
    the launch record (its descriptions left out), or there is no record, as
    when the state comes from a run launched outside the web UI.
    """
    return _launch_check(program)


# The code of the conflict with which /run answers when a resident program
# would resume program state that a different program produced.
LAUNCH_RECORD_CONFLICT = "launch-record"


@router.post("/run", response_model=RunProgramResponse)
def run_program(program: Program, resumeChangedProgram: bool = False) -> RunProgramResponse:
    """
    Launch a program run. A general program runs with debasher_exec
    --wait in the background, and this returns immediately: poll /status
    to find out when it's done. A resident program is launched with
    debasher_exec in oneshot mode, and this returns once it has ended,
    with its exit code and output.

    A resident program whose output directory holds program state, and that
    differs from the launch record or has none, is refused with a conflict
    whose detail has the code "launch-record", unless `resumeChangedProgram`
    says that the user chose to resume with the changed program. The
    frontend asks before sending the request; this checks again, since
    another tab may have launched the program in between.
    """
    state, _ = _get_program_state(program)
    if state == "in-progress":
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress for this output directory.",
        )

    if _is_resident(program) and not resumeChangedProgram:
        check = _launch_check(program)
        if check.needsConfirmation:
            raise HTTPException(
                status_code=409,
                detail={"code": LAUNCH_RECORD_CONFLICT, "hasLaunchRecord": check.hasLaunchRecord},
            )

    command = _prepare_debasher_exec_command(
        program, None if _is_resident(program) else "--wait"
    )
    if command is None:
        raise HTTPException(status_code=500, detail="debasher_exec tool not found.")

    if _is_resident(program):
        return _launch_resident_program(command, program)

    log_path = _run_log_path(program)

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
    # Only for a resident program: whether its output directory holds
    # program state, which the next launch resumes; false otherwise.
    hasProgramState: bool = False


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
    return ProcessStatusesResponse(
        statuses=_parse_process_statuses(output),
        hasProgramState=_is_resident(program) and program_state.has_program_state(program.outputDir),
    )


class ProcessTasksRequest(BaseModel):
    program: Program
    processName: str


class ProcessTasksResponse(BaseModel):
    # Empty for a "standard" one-task process; the list of task
    # indices found (not necessarily contiguous, a task still
    # running, or that never produced output, leaves a gap) otherwise.
    taskIndices: list[int]


@router.post("/process-tasks", response_model=ProcessTasksResponse)
def get_process_tasks(request: ProcessTasksRequest) -> ProcessTasksResponse:
    """
    List the task indices that have a stdout or scheduler-output file
    for `processName`, for the "Inspect execution" menu's task picker
    (skipped when this comes back empty, a "standard" process's
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


class FifoMirrorRequest(BaseModel):
    program: Program
    processName: str
    # The fifo's name as given to define_fifo_opt (a mirrored option's
    # own `value`, per ProgramOption.mirror), not the option's label.
    fifoName: str
    taskIndex: int | None = None


@router.post("/fifo-mirror", response_model=ProcessOutputResponse)
def get_fifo_mirror(request: FifoMirrorRequest) -> ProcessOutputResponse:
    """
    Get a mirrored output fifo's captured content (debasher_get_fifo_mirror
    -d <outputDir> -p <processName> -f <fifoName> [-t <taskIndex>]), for
    the canvas's right-click "Watch FIFO" action.
    """
    output = _run_debasher_process_tool(
        request.program,
        "debasher_get_fifo_mirror",
        request.processName,
        request.taskIndex,
        extra_args=["-f", request.fifoName],
    )
    return ProcessOutputResponse(output=output)


# Bounded so a stuck write (no reader ever connects) or an empty read
# (nothing produced yet) can't hang a request forever, the frontend's
# "Talk to FIFOs" action just calls /fifo-read again on a timeout, so a
# short-ish bound here just controls the retry cadence, not correctness.
_FIFO_WRITE_TIMEOUT_SECS = 8
_FIFO_READ_TIMEOUT_SECS = 8


def _resolve_fifo_path(program: Program, process_name: str, fifo_name: str) -> Path:
    """
    A fifo's real path is a fixed convention (see engine/debasher_lib_
    opts.sh's debasher::_get_absolute_fifoname), no ".opts"/resolved-
    value lookup needed, the same way _task_indices_for_process (above)
    reads the "__exec__" convention directly instead of shelling out to
    a tool.
    """
    return Path(program.outputDir).expanduser() / "__fifos__" / process_name / fifo_name


class FifoIORequest(BaseModel):
    program: Program
    processName: str
    # The fifo's name as given to define_fifo_opt, not the option's label.
    fifoName: str


class FifoWriteRequest(FifoIORequest):
    text: str


class FifoWriteResponse(BaseModel):
    ok: bool
    error: str | None = None


@router.post("/fifo-write", response_model=FifoWriteResponse)
def write_fifo(request: FifoWriteRequest) -> FifoWriteResponse:
    """
    Write one line to an (unconnected) input fifo, for the "Talk to
    FIFOs" action. Opening a fifo for writing blocks until a reader
    connects, so this is bounded by _FIFO_WRITE_TIMEOUT_SECS, a
    timeout here means no process is currently reading that fifo.
    """
    path = _resolve_fifo_path(request.program, request.processName, request.fifoName)
    if not path.exists():
        return FifoWriteResponse(
            ok=False,
            error=f"Fifo not found: {path} (has the owning process started yet?)",
        )

    try:
        result = subprocess.run(
            ["bash", "-c", 'printf "%s\n" "$1" > "$2"', "_", request.text, str(path)],
            capture_output=True,
            text=True,
            timeout=_FIFO_WRITE_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return FifoWriteResponse(
            ok=False, error="Timed out waiting for a reader on the input fifo."
        )

    if result.returncode != 0:
        return FifoWriteResponse(ok=False, error=result.stderr.strip() or "Write failed.")

    return FifoWriteResponse(ok=True)


class FifoReadResponse(BaseModel):
    line: str | None = None
    # A timeout here is the expected, common case (nothing produced yet
    # by the owning process), the frontend just calls again, not an
    # error.
    timedOut: bool = False
    error: str | None = None


@router.post("/fifo-read", response_model=FifoReadResponse)
def read_fifo(request: FifoIORequest) -> FifoReadResponse:
    """
    Read one line from an (unconnected) output fifo, for the "Talk to
    FIFOs" action. Bounded by _FIFO_READ_TIMEOUT_SECS; the frontend
    calls this repeatedly until it gets a line or a real error.
    """
    path = _resolve_fifo_path(request.program, request.processName, request.fifoName)
    if not path.exists():
        return FifoReadResponse(
            error=f"Fifo not found: {path} (has the owning process started yet?)"
        )

    try:
        result = subprocess.run(
            ["bash", "-c", 'IFS= read -r line < "$1" && printf "%s" "$line"', "_", str(path)],
            capture_output=True,
            text=True,
            timeout=_FIFO_READ_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        return FifoReadResponse(timedOut=True)

    if result.returncode != 0:
        return FifoReadResponse(error=result.stderr.strip() or "Read failed.")

    return FifoReadResponse(line=result.stdout)


# There's no "debasher_get_opts" bin tool (unlike stdout/sched-out), the
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
    canvas's right-click "Inspect execution" menu's "See options", capped at _MAX_INSPECT_LINES lines.
    """
    opts_path = _get_process_opts_path(
        request.program.outputDir, request.processName, request.taskIndex
    )
    try:
        output = file_inspection.read_text_capped(opts_path)
    except OSError:
        output = f"Error: options file for process {request.processName} could not be found!"

    return ProcessOutputResponse(output=output)


# Each ".opts" line is one option, `printf '%q'`-escaped and (when it
# has a value) shell-word-split from its value, e.g. `-i input\ file`
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
    # file, empty when the program hasn't produced one yet (e.g. it
    # hasn't been run).
    values: dict[str, str]


@router.post("/process-resolved-options", response_model=ProcessResolvedOptionsResponse)
def get_process_resolved_options(request: ProcessOutputRequest) -> ProcessResolvedOptionsResponse:
    """
    Parse a process's ".opts" file into a {label: value} map, for the
    canvas's right-click "Inspect execution" menu's "Show inputs and
    outputs", this is how a fifo/shared-dir/value-descriptor option's
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
        if len(entries) > file_inspection.MAX_INSPECT_LINES:
            total = len(entries)
            entries = entries[: file_inspection.MAX_INSPECT_LINES]
            entries.insert(
                0,
                f"Warning: directory has {total} entries, "
                f"showing only the first {file_inspection.MAX_INSPECT_LINES}.",
            )
        return InspectPathResponse(kind="directory", entries=entries)

    if resolved.is_file():
        if file_inspection.looks_binary(resolved):
            return InspectPathResponse(kind="binary")

        try:
            content = file_inspection.read_text_capped(resolved)
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
    # Only for a resident program: the exit code of the tool, which tells an
    # orderly stop from one that fell back to the hard kill.
    exitCode: int | None = None


@router.post("/stop", response_model=StopProgramResponse)
def stop_program(program: Program) -> StopProgramResponse:
    """
    Stop a running program. A general program is stopped with debasher_stop
    -d <outputDir>, and a resident one in order, with debasher_stop_resident
    -d <outputDir> and its default timeout, which this waits for: it halts
    every node in one round and then stops them, the Supervisor first, and
    falls back to the hard kill of debasher_stop when the round does not
    close in time (exit code 2).
    """
    if _is_resident(program):
        output, exit_code = _run_debasher_dir_tool_in_own_session(program, "debasher_stop_resident")
        return StopProgramResponse(output=output, exitCode=exit_code)

    output, _ = _run_debasher_dir_tool(program, "debasher_stop")
    return StopProgramResponse(output=output)


@router.post("/kill", response_model=StopProgramResponse)
def kill_program(program: Program) -> StopProgramResponse:
    """
    Kill a resident program at once with debasher_stop -d <outputDir>, the
    hard kill, for a program known to be stuck, whose orderly stop would
    only reach the hard kill after its timeout.
    """
    output, exit_code = _run_debasher_dir_tool_in_own_session(program, "debasher_stop")
    return StopProgramResponse(output=output, exitCode=exit_code)


class StopProcessRequest(BaseModel):
    program: Program
    processName: str


@router.post("/stop-process", response_model=ProcessOutputResponse)
def stop_process(request: StopProcessRequest) -> ProcessOutputResponse:
    """
    Stop a single process (debasher_stop -d <outputDir> -p <processName>),
    for the canvas's right-click "Stop process" action.
    """
    output = _run_debasher_process_tool(
        request.program, "debasher_stop", request.processName
    )
    return ProcessOutputResponse(output=output)


def _has_supervisor(program: Program) -> bool:
    return any(p.nodeKind == "Supervisor" for p in program.processes)


class RelaunchNodeResponse(BaseModel):
    output: str
    exitCode: int
    # The tasks that the web UI relaunched, as <process> or <process>:<idx>;
    # empty when none was down, and for a restart that the Supervisor
    # relaunches.
    relaunched: list[str] = []


@router.post("/restart-node", response_model=RelaunchNodeResponse)
def restart_node(request: StopProcessRequest) -> RelaunchNodeResponse:
    """
    "Restart node" on a node of a resident program: debasher_stop -d
    <outputDir> -p <processName> kills every task of the process at once, a
    crash of the node, which resumes from its last checkpoint and its input
    log once it is launched again. With a Supervisor, the Supervisor
    relaunches it. Without one, the backend does, once every task is down,
    holding the relaunch lock from the stop to the relaunch.
    """
    program = request.program

    if _has_supervisor(program):
        output, exit_code = _run_debasher_dir_tool_in_own_session(
            program, "debasher_stop", ["-p", request.processName]
        )
        return RelaunchNodeResponse(output=output, exitCode=exit_code)

    with node_relaunch.relaunch_lock(program.outputDir):
        output, exit_code = _run_debasher_dir_tool_in_own_session(
            program, "debasher_stop", ["-p", request.processName]
        )
        if exit_code != 0:
            return RelaunchNodeResponse(output=output, exitCode=exit_code)

        if not node_relaunch.wait_until_down(program.outputDir, request.processName):
            return RelaunchNodeResponse(
                output=output + f"Error: some task of {request.processName} still runs after the stop.\n",
                exitCode=1,
            )

        result = node_relaunch.relaunch_down_tasks(
            program.outputDir, request.processName, _debasher_env(program)
        )

    return RelaunchNodeResponse(
        output=_cap_lines(output + result.output),
        exitCode=result.exit_code,
        relaunched=result.relaunched,
    )


@router.post("/relaunch-node", response_model=RelaunchNodeResponse)
def relaunch_node(request: StopProcessRequest) -> RelaunchNodeResponse:
    """
    "Relaunch node" on a node of a resident program without a Supervisor:
    relaunch each task of the process that is down, and only those, with
    debasher_launch_process, under the relaunch lock.
    """
    program = request.program

    if program.programType != "resident" or _has_supervisor(program):
        raise HTTPException(
            status_code=400,
            detail="A node is relaunched by hand only in a resident program without a Supervisor.",
        )

    with node_relaunch.relaunch_lock(program.outputDir):
        result = node_relaunch.relaunch_down_tasks(
            program.outputDir, request.processName, _debasher_env(program)
        )

    return RelaunchNodeResponse(
        output=_cap_lines(result.output),
        exitCode=result.exit_code,
        relaunched=result.relaunched,
    )


class SnapshotResponse(BaseModel):
    output: str
    # 0 for a round that closed at every node, 2 for one that did not close
    # at some node, 1 for an error of usage or setup.
    exitCode: int
    # The epoch of the round, when the tool started one.
    epoch: int | None = None
    # With exit code 2, the nodes at which the round did not close, when the
    # tool names them.
    pendingNodes: list[str] = []


# What debasher_snapshot_resident prints of a round: "Round <epoch> closed
# at every node ...", or "Warning: round <epoch> did not close ...", and,
# before the latter, "Error: no checkpoint of round <epoch> or of a newer
# one at <node> <node> ...".
_ROUND_EPOCH_RE = re.compile(r"\b[Rr]ound (\d+)\b")
_PENDING_NODES_RE = re.compile(r"^Error: no checkpoint of round \d+ or of a newer one at (.+)$", re.MULTILINE)


@router.post("/snapshot", response_model=SnapshotResponse)
def take_snapshot(program: Program) -> SnapshotResponse:
    """
    "Take snapshot" on a live resident program: debasher_snapshot_resident
    -d <outputDir> with its default timeout, which starts one round and
    waits until it closes at every node or the timeout passes.
    """
    output, exit_code = _run_debasher_dir_tool_in_own_session(program, "debasher_snapshot_resident")

    epoch_match = _ROUND_EPOCH_RE.search(output)
    pending_match = _PENDING_NODES_RE.search(output)

    return SnapshotResponse(
        output=output,
        exitCode=exit_code,
        epoch=int(epoch_match.group(1)) if epoch_match else None,
        pendingNodes=pending_match.group(1).split() if pending_match else [],
    )


class NoHoldFifosResponse(BaseModel):
    # Whether the Supervisor of the live program was launched with
    # -no-hold-fifos, as its own ".opts" file says; false when it has none.
    launchedWithNoHoldFifos: bool


@router.post("/launched-with-no-hold-fifos", response_model=NoHoldFifosResponse)
def launched_with_no_hold_fifos(program: Program) -> NoHoldFifosResponse:
    """
    Whether the Supervisor of a resident program was launched with
    -no-hold-fifos, read from the options it was given, so that it is the
    launch that counts, whoever made it, and not the program options as the
    tab holds them now. "Restart node" warns with it that a channel whose
    two ends are restarted together may lose what it held.
    """
    supervisor = next((p for p in program.processes if p.nodeKind == "Supervisor"), None)
    if supervisor is None:
        return NoHoldFifosResponse(launchedWithNoHoldFifos=False)

    opts = _parse_opts_file(_get_process_opts_path(program.outputDir, supervisor.name, None))
    return NoHoldFifosResponse(launchedWithNoHoldFifos=NO_HOLD_FIFOS_LABEL in opts)


class ResetProgramStateRequest(BaseModel):
    program: Program
    # Delete the program state instead of setting it aside.
    delete: bool = False


class ResetProgramStateResponse(BaseModel):
    output: str
    exitCode: int


@router.post("/reset-program-state", response_model=ResetProgramStateResponse)
def reset_program_state(request: ResetProgramStateRequest) -> ResetProgramStateResponse:
    """
    "Reset program state" on a resident program: debasher_reset_resident -d
    <outputDir>, which takes the program state away, for every task of every
    process, so that the next launch starts every node afresh. It sets the
    state aside under __reset__/<timestamp>/ in the output directory, or
    deletes it with `delete` (--delete). Refused while there is a run in
    progress, which the tool refuses too.
    """
    program = request.program

    if not _is_resident(program):
        raise HTTPException(status_code=400, detail="Only a resident program has program state.")

    state, _ = _get_program_state(program)
    if state == "in-progress":
        raise HTTPException(
            status_code=409,
            detail="Cannot reset the program state while a run is in progress.",
        )

    output, exit_code = _run_debasher_dir_tool_in_own_session(
        program, "debasher_reset_resident", ["--delete"] if request.delete else []
    )
    return ResetProgramStateResponse(output=output, exitCode=exit_code)


class ResetOutputDirResponse(BaseModel):
    # False whenever a guard below made this a no-op, the caller can
    # tell the user there was nothing to reset.
    cleared: bool


@router.post("/reset-output-dir", response_model=ResetOutputDirResponse)
def reset_output_dir(program: Program) -> ResetOutputDirResponse:
    """
    Delete everything inside program.outputDir (the directory itself is
    kept), for the Run menu's "Reset output directory" action.

    Guards against a mistaken mass deletion: a no-op (cleared=False,
    nothing raised) whenever outputDir is blank (an empty string would
    otherwise resolve to the server's current directory, not "nowhere"),
    doesn't resolve to an existing directory, resolves to the
    filesystem root or the server user's home directory (the two paths
    a corrupted/mistaken outputDir would do the most damage at), or
    equals the program's own homeDir: that's where the generated .sh
    and .debasher/program.json live, and any files added through the
    program-files panel, none of which "resetting the output directory"
    should ever be able to wipe out.
    """
    outdir = program.outputDir.strip()
    if not outdir:
        return ResetOutputDirResponse(cleared=False)

    resolved = Path(outdir).expanduser().resolve()

    if not resolved.is_dir():
        return ResetOutputDirResponse(cleared=False)

    if resolved == Path(resolved.root) or resolved == Path.home():
        return ResetOutputDirResponse(cleared=False)

    if persistence.same_dir(program.outputDir, program.homeDir):
        return ResetOutputDirResponse(cleared=False)

    try:
        for entry in resolved.iterdir():
            # A symlink is removed as itself, never followed, so a
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
