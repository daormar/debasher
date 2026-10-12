import os

from fastapi import APIRouter
from pydantic import BaseModel

from ..paths import find_bin_tool
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

# Set to "no" to keep the command to copy and offer no session in the page,
# where the backend should not run Claude Code itself.
CLAUDE_CODE_TERMINAL_ENV_VAR = "DEBASHER_WEBUI_CLAUDE_CODE_TERMINAL"


class WebuiInfoResponse(BaseModel):
    claudeCode: bool
    claudeCodePrefix: str | None
    claudeCodeInstall: str | None
    backendUrl: str | None
    claudeCodeTerminal: bool


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


def claude_terminal_refusal() -> str | None:
    """
    Why this backend offers no session of Claude Code in the page, or None
    when it does. A backend that uvicorn started by hand knows no URL of its
    own and writes no token file, so the MCP server of a session would not
    reach it.
    """
    if os.environ.get(CLAUDE_CODE_ENV_VAR) == "no":
        return f"This web UI does not offer Claude Code ({CLAUDE_CODE_ENV_VAR} is no)"
    if os.environ.get(CLAUDE_CODE_TERMINAL_ENV_VAR) == "no":
        return (
            "This web UI does not run Claude Code in the page "
            f"({CLAUDE_CODE_TERMINAL_ENV_VAR} is no)"
        )
    if backend_url() is None:
        return (
            "This backend does not know its own address: start it with "
            "debasher_webui to run Claude Code in the page"
        )
    if find_bin_tool("debasher_claude") is None:
        return "debasher_claude is not installed with this backend"
    return None


@router.get("/info", response_model=WebuiInfoResponse)
def get_webui_info() -> WebuiInfoResponse:
    """
    What this web UI offers that depends on where it runs: whether the
    Help menu gives the command that starts Claude Code on a program, what
    that command is run through, the command that installs Claude Code
    there, the URL of the backend that the command names, and whether it
    runs Claude Code in the page.
    """
    return WebuiInfoResponse(
        claudeCode=os.environ.get(CLAUDE_CODE_ENV_VAR) != "no",
        claudeCodePrefix=os.environ.get(CLAUDE_CODE_PREFIX_ENV_VAR) or None,
        claudeCodeInstall=os.environ.get(CLAUDE_CODE_INSTALL_ENV_VAR) or None,
        backendUrl=backend_url(),
        claudeCodeTerminal=claude_terminal_refusal() is None,
    )
