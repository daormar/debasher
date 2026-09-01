import os
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


def _debasher_env(program: Program) -> dict[str, str]:
    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = program.envVars.get("DEBASHER_MOD_DIR", "")
    return env


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

    for label, value in program.programOptions.items():
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
