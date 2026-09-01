import os
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import paths, persistence
from ..models import Workflow

router = APIRouter(prefix="/api/execution", tags=["execution"])

# debasher_status's own exit codes (see engine/debasher_lib.sh /
# engine/debasher_status.sh): 0 once every process has finished, 2 while
# at least one is still running, 3 otherwise (not all processes finished
# correctly).
WorkflowState = Literal["finished", "in-progress", "unfinished"]

_STATE_BY_EXIT_CODE: dict[int, WorkflowState] = {
    0: "finished",
    2: "in-progress",
}


def _debasher_env(workflow: Workflow) -> dict[str, str]:
    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = workflow.envVars.get("DEBASHER_MOD_DIR", "")
    return env


def _prepare_debasher_exec_command(workflow: Workflow, mode_flag: str) -> list[str] | None:
    """
    Save `workflow` to its home directory (the same as pressing "Save"
    in the toolbar, generating its .sh file there) and build the
    debasher_exec command line for it, passing the scheduler, the run
    output directory, and the command line options set via "Set
    workflow options".

    Returns None if debasher_exec isn't found.
    """
    persistence.save_workflow(workflow.homeDir, workflow)
    script_path = persistence.save_script(workflow.homeDir, workflow)

    tool = paths.find_bin_tool("debasher_exec")
    if tool is None:
        return None

    command = [
        str(tool),
        "--pfile", str(script_path),
        "--outdir", workflow.outputDir,
        "--sched", workflow.executionOptions.scheduler,
        mode_flag,
    ]

    for label, value in workflow.workflowOptions.items():
        command += [label, value]

    return command


def _run_debasher_exec(workflow: Workflow, mode_flag: str) -> str:
    command = _prepare_debasher_exec_command(workflow, mode_flag)
    if command is None:
        return "Error: debasher_exec tool not found."

    result = subprocess.run(command, env=_debasher_env(workflow), capture_output=True, text=True)

    return result.stdout + result.stderr


def _run_debasher_dir_tool(workflow: Workflow, tool_name: str) -> tuple[str, int]:
    """
    Run a DeBasher bin tool that just takes "-d <outputDir>" (e.g.
    debasher_status, debasher_stop). Returns (combined output, exit code).
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found.", 1

    command = [str(tool), "-d", workflow.outputDir]

    result = subprocess.run(command, env=_debasher_env(workflow), capture_output=True, text=True)

    return result.stdout + result.stderr, result.returncode


def _get_workflow_state(workflow: Workflow) -> tuple[WorkflowState, str]:
    output, returncode = _run_debasher_dir_tool(workflow, "debasher_status")
    return _STATE_BY_EXIT_CODE.get(returncode, "unfinished"), output


class ListSchedulersResponse(BaseModel):
    schedulers: list[str]


@router.get("/schedulers", response_model=ListSchedulersResponse)
def list_schedulers() -> ListSchedulersResponse:
    """
    List the schedulers a workflow can be executed with.

    Stub: always returns the two schedulers DeBasher supports.

    TODO: replace with real logic, e.g. checking which scheduler
    binaries (sbatch, ...) are actually available on the host.
    """
    return ListSchedulersResponse(schedulers=["SLURM", "BUILTIN"])


class RunWorkflowResponse(BaseModel):
    started: bool


@router.post("/run", response_model=RunWorkflowResponse)
def run_workflow(workflow: Workflow) -> RunWorkflowResponse:
    """
    Launch a workflow run (debasher_exec --wait) in the background and
    return immediately. Poll /status to find out when it's done.
    """
    state, _ = _get_workflow_state(workflow)
    if state == "in-progress":
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress for this output directory.",
        )

    command = _prepare_debasher_exec_command(workflow, "--wait")
    if command is None:
        raise HTTPException(status_code=500, detail="debasher_exec tool not found.")

    log_path = Path(workflow.outputDir).expanduser() / ".debasher_webui_run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log_file:
        subprocess.Popen(
            command,
            env=_debasher_env(workflow),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    return RunWorkflowResponse(started=True)


class RunWorkflowDebugResponse(BaseModel):
    output: str


@router.post("/run-debug", response_model=RunWorkflowDebugResponse)
def run_workflow_debug(workflow: Workflow) -> RunWorkflowDebugResponse:
    """
    Run a workflow in debug mode (debasher_exec --debug).
    """
    return RunWorkflowDebugResponse(output=_run_debasher_exec(workflow, "--debug"))


class WorkflowStatusResponse(BaseModel):
    output: str
    state: WorkflowState


@router.post("/status", response_model=WorkflowStatusResponse)
def get_workflow_status(workflow: Workflow) -> WorkflowStatusResponse:
    """
    Get a workflow's status (debasher_status -d <outputDir>).
    """
    state, output = _get_workflow_state(workflow)
    return WorkflowStatusResponse(output=output, state=state)


class CheckWorkflowOptionsResponse(BaseModel):
    output: str


@router.post("/check-workflow-options", response_model=CheckWorkflowOptionsResponse)
def check_workflow_options(workflow: Workflow) -> CheckWorkflowOptionsResponse:
    """
    Check a workflow's command line options (debasher_exec --check-proc-opts).
    """
    return CheckWorkflowOptionsResponse(
        output=_run_debasher_exec(workflow, "--check-proc-opts")
    )


class StopWorkflowResponse(BaseModel):
    output: str


@router.post("/stop", response_model=StopWorkflowResponse)
def stop_workflow(workflow: Workflow) -> StopWorkflowResponse:
    """
    Stop a running workflow (debasher_stop -d <outputDir>).
    """
    output, _ = _run_debasher_dir_tool(workflow, "debasher_stop")
    return StopWorkflowResponse(output=output)
