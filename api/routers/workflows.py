from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import persistence
from ..models import Workflow

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class SaveWorkflowRequest(BaseModel):
    outputDir: str
    workflow: Workflow


class SaveWorkflowResponse(BaseModel):
    path: str


@router.post("/save", response_model=SaveWorkflowResponse)
def save_workflow_to_dir(request: SaveWorkflowRequest) -> SaveWorkflowResponse:
    """
    Serialize the whole workflow into a hidden directory inside
    `request.outputDir`, creating the output directory if needed.
    """
    if not request.outputDir.strip():
        raise HTTPException(status_code=400, detail="outputDir must not be empty")

    workflow_path = persistence.save_workflow(request.outputDir, request.workflow)
    return SaveWorkflowResponse(path=str(workflow_path))


@router.get("/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: str) -> Workflow:
    """
    Load a workflow by id.

    TODO: replace this stub with a real call into core/, e.g.:
        return core.load_workflow(workflow_id)
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.put("/{workflow_id}")
def save_workflow(workflow_id: str, workflow: Workflow) -> dict[str, str]:
    """
    Persist a workflow.

    TODO: replace this stub with a real call into core/, e.g.:
        core.save_workflow(workflow_id, workflow)
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")
