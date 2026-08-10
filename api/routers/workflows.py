from fastapi import APIRouter, HTTPException

from ..models import Workflow

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


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
