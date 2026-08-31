import os
import subprocess

from fastapi import APIRouter
from pydantic import BaseModel

from .. import paths, persistence
from ..models import Workflow

router = APIRouter(prefix="/api/execution", tags=["execution"])


def _run_debasher_exec(workflow: Workflow, mode_flag: str) -> str:
    """
    Save `workflow` to its home directory (the same as pressing "Save"
    in the toolbar, generating its .sh file there) and run debasher_exec
    against that script with `mode_flag`, passing the scheduler, the run
    output directory, and the command line options set via "Set
    workflow options".
    """
    persistence.save_workflow(workflow.homeDir, workflow)
    script_path = persistence.save_script(workflow.homeDir, workflow)

    tool = paths.find_bin_tool("debasher_exec")
    if tool is None:
        return "Error: debasher_exec tool not found."

    command = [
        str(tool),
        "--pfile", str(script_path),
        "--outdir", workflow.outputDir,
        "--sched", workflow.executionOptions.scheduler,
        mode_flag,
    ]

    for label, value in workflow.workflowOptions.items():
        command += [label, value]

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = workflow.envVars.get("DEBASHER_MOD_DIR", "")

    result = subprocess.run(command, env=env, capture_output=True, text=True)

    return result.stdout + result.stderr


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
    status: str


@router.post("/run", response_model=RunWorkflowResponse)
def run_workflow(workflow: Workflow) -> RunWorkflowResponse:
    """
    Run a workflow.

    Stub: does not actually execute anything yet.

    TODO: replace this stub with a real call into core/, e.g.:
        core.run_workflow(workflow)
    """
    return RunWorkflowResponse(status="started")


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


@router.post("/status", response_model=WorkflowStatusResponse)
def get_workflow_status(workflow: Workflow) -> WorkflowStatusResponse:
    """
    Get a workflow's status by running a command.

    Stub: does not actually run anything yet.

    TODO: replace this stub with a real call into core/, e.g.:
        output = core.get_workflow_status(workflow)
    """
    return WorkflowStatusResponse(output="")


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
    status: str


@router.post("/stop", response_model=StopWorkflowResponse)
def stop_workflow(workflow: Workflow) -> StopWorkflowResponse:
    """
    Stop a running workflow.

    Stub: does not actually stop anything yet.

    TODO: replace this stub with a real call into core/, e.g.:
        core.stop_workflow(workflow)
    """
    return StopWorkflowResponse(status="stopped")
