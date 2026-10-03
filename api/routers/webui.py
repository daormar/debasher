import os

from fastapi import APIRouter
from pydantic import BaseModel

from ..token_auth import HOST_ENV_VAR, PORT_ENV_VAR, is_every_address, url_host

router = APIRouter(prefix="/api/webui", tags=["webui"])

# Set to "no" where Claude Code cannot work on the programs that this web UI
# saves, as where the directories of the backend are not those of the machine
# where debasher_claude would run.
CLAUDE_CODE_ENV_VAR = "DEBASHER_WEBUI_CLAUDE_CODE"

# What the command that starts Claude Code is run through, to run it where the
# backend runs: the Docker image sets it to the `docker compose exec` of its
# container, since the directories and the token file of the backend are
# there.
CLAUDE_CODE_PREFIX_ENV_VAR = "DEBASHER_WEBUI_CLAUDE_CODE_PREFIX"

# The command that installs Claude Code there, where it is not installed with
# the rest: the Docker image gives the one of its install-claude-code.
CLAUDE_CODE_INSTALL_ENV_VAR = "DEBASHER_WEBUI_CLAUDE_CODE_INSTALL"


class WebuiInfoResponse(BaseModel):
    claudeCode: bool
    claudeCodePrefix: str | None
    claudeCodeInstall: str | None
    backendUrl: str | None


def backend_url() -> str | None:
    """
    The URL of the backend from its own machine, where debasher_claude runs:
    the address and port that it listens on, the local machine when it
    listens on every address. None for a backend that uvicorn started by
    hand, whose port it does not know.
    """
    port = os.environ.get(PORT_ENV_VAR)
    if not port:
        return None
    host = os.environ.get(HOST_ENV_VAR, "")
    return f"http://{'127.0.0.1' if is_every_address(host) else url_host(host)}:{port}"


@router.get("/info", response_model=WebuiInfoResponse)
def get_webui_info() -> WebuiInfoResponse:
    """
    What this web UI offers that depends on where it runs: whether the
    Help menu gives the command that starts Claude Code on a program, what
    that command is run through, the command that installs Claude Code
    there, and the URL of the backend that the command names.
    """
    return WebuiInfoResponse(
        claudeCode=os.environ.get(CLAUDE_CODE_ENV_VAR) != "no",
        claudeCodePrefix=os.environ.get(CLAUDE_CODE_PREFIX_ENV_VAR) or None,
        claudeCodeInstall=os.environ.get(CLAUDE_CODE_INSTALL_ENV_VAR) or None,
        backendUrl=backend_url(),
    )
