import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel, Field

from .. import persistence
from ..claude_sessions import (
    CLOSE_BAD_TICKET,
    Registry,
    SessionInUse,
    Start,
    TerminalSession,
    claude_command,
    session_env,
)
from ..paths import find_bin_tool
from .webui import backend_url, claude_terminal_refusal

router = APIRouter(prefix="/api/claude", tags=["claude"])

# The WebSocket of a session, which carries a ticket instead of the token.
TERMINAL_PATH = "/api/claude/terminal"

registry = Registry()


class SessionRequest(BaseModel):
    homeDir: str
    start: Start = "new"
    cols: int = Field(default=80, gt=0, le=1000)
    rows: int = Field(default=24, gt=0, le=1000)
    takeOver: bool = False


class SessionTicket(BaseModel):
    ticket: str


@router.post("/session", response_model=SessionTicket)
async def request_session(request: SessionRequest) -> SessionTicket:
    """
    A ticket that opens a session of Claude Code in the page on the program
    saved in `homeDir` (see "Opening a session in the page" in
    doc/design_doc_webui.md). The command of the session is fixed here, from
    the program and the way its conversation starts; a takeover ends the
    session of another tab and always starts with the last conversation.
    """
    refusal = claude_terminal_refusal()
    url = backend_url()
    launcher = find_bin_tool("debasher_claude")
    if refusal is not None or url is None or launcher is None:
        raise HTTPException(status_code=503, detail=refusal)

    if not request.homeDir.strip():
        raise HTTPException(status_code=400, detail="homeDir must not be empty")
    home_dir = os.path.realpath(Path(request.homeDir).expanduser())
    if persistence.read_raw_metadata(home_dir) is None:
        raise HTTPException(
            status_code=404, detail=f"No program is saved in {request.homeDir!r}"
        )

    start = "continue" if request.takeOver else request.start
    command = claude_command(str(launcher), home_dir, url, start)
    try:
        ticket = await registry.reserve(
            home_dir, command, request.cols, request.rows, request.takeOver
        )
    except SessionInUse:
        raise HTTPException(
            status_code=409,
            detail="Claude Code is already open on this program in another page",
        )
    return SessionTicket(ticket=ticket)


@router.websocket("/terminal")
async def terminal(websocket: WebSocket, ticket: str = "") -> None:
    """
    The terminal of a session in the page, opened with a ticket of
    /session, which serves once: the bytes of the terminal both ways, and
    the control messages in JSON (see "The pseudo-terminal" in
    doc/design_doc_webui.md).
    """
    session = TerminalSession()
    granted = registry.redeem(ticket, session)
    if granted is None:
        await websocket.close(code=CLOSE_BAD_TICKET)
        return
    await session.run(
        websocket,
        granted,
        session_env(dict(os.environ)),
        on_end=lambda: registry.release(granted.home_dir, session),
    )
