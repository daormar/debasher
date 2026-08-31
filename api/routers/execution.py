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


def _run_debasher_dir_tool(workflow: Workflow, tool_name: str) -> str:
    """
    Run a DeBasher bin tool that just takes "-d <outputDir>" (e.g.
    debasher_status, debasher_stop).
    """
    tool = paths.find_bin_tool(tool_name)
    if tool is None:
        return f"Error: {tool_name} tool not found."

    command = [str(tool), "-d", workflow.outputDir]

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
    Get a workflow's status (debasher_status -d <outputDir>).
    """
    return WorkflowStatusResponse(output=_run_debasher_dir_tool(workflow, "debasher_status"))


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
    return StopWorkflowResponse(output=_run_debasher_dir_tool(workflow, "debasher_stop"))
