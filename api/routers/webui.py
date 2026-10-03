import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/webui", tags=["webui"])

# Set to "no" where Claude Code cannot work on the programs that this web UI
# saves: the Docker image sets it, since the directories of the container are
# not those of the computer where debasher_claude would run.
CLAUDE_CODE_ENV_VAR = "DEBASHER_WEBUI_CLAUDE_CODE"


class WebuiInfoResponse(BaseModel):
    claudeCode: bool


@router.get("/info", response_model=WebuiInfoResponse)
def get_webui_info() -> WebuiInfoResponse:
    """
    What this web UI offers that depends on where it runs: whether the
    Help menu gives the command that starts Claude Code on a program.
    """
    return WebuiInfoResponse(claudeCode=os.environ.get(CLAUDE_CODE_ENV_VAR) != "no")
