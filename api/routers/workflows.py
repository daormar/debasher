import pydantic
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
    scriptPath: str


class LoadWorkflowRequest(BaseModel):
    inputDir: str


class ImportWorkflowRequest(BaseModel):
    scriptPath: str
    workflow: Workflow


@router.post("/save", response_model=SaveWorkflowResponse)
def save_workflow_to_dir(request: SaveWorkflowRequest) -> SaveWorkflowResponse:
    """
    Serialize the whole workflow into a hidden directory inside
    `request.outputDir`, creating the output directory if needed.
    """
    if not request.outputDir.strip():
        raise HTTPException(status_code=400, detail="outputDir must not be empty")

    workflow_path = persistence.save_workflow(request.outputDir, request.workflow)
    script_path = persistence.save_script(request.outputDir, request.workflow)
    return SaveWorkflowResponse(path=str(workflow_path), scriptPath=str(script_path))


@router.post("/load", response_model=Workflow)
def load_workflow_from_dir(request: LoadWorkflowRequest) -> Workflow:
    """
    Read a workflow previously saved into `request.inputDir` via `/save`.
    """
    if not request.inputDir.strip():
        raise HTTPException(status_code=400, detail="inputDir must not be empty")

    try:
        return persistence.load_workflow(request.inputDir)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except pydantic.ValidationError as err:
        raise HTTPException(
            status_code=400, detail=f"Invalid workflow data in {request.inputDir!r}: {err}"
        )


@router.post("/import", response_model=Workflow)
def import_workflow_from_script(request: ImportWorkflowRequest) -> Workflow:
    """
    Import a workflow from a Bash script.

    Stub: just echoes back the (empty) workflow the frontend sent,
    ignoring the script's contents.

    TODO: replace this with a real call into core/ that parses
    `request.scriptPath` into a Workflow, e.g.:
        return core.import_workflow(request.scriptPath)
    """
    if not request.scriptPath.strip():
        raise HTTPException(status_code=400, detail="scriptPath must not be empty")

    try:
        persistence.resolve_script_path(request.scriptPath)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))

    return request.workflow


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
