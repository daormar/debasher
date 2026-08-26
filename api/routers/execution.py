from fastapi import APIRouter
from pydantic import BaseModel

from ..models import Workflow

router = APIRouter(prefix="/api/execution", tags=["execution"])


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
