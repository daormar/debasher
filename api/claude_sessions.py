"""
The sessions of Claude Code that the backend runs for the terminal panel of
the editor (see "Claude Code in the page" in doc/design_doc_webui.md): the
registry of sessions, which gives a home directory one session at most, the
tickets that open them, and the pseudo-terminal that carries each one between
`debasher_claude` and the WebSocket of its tab.
"""

import asyncio
import fcntl
import json
import os
import pty
import secrets
import signal
import struct
import sys
import termios
import time
from dataclasses import dataclass
from typing import Callable, Literal

from starlette.websockets import WebSocket

from .token_auth import TOKEN_ENV_VAR

Start = Literal["new", "continue", "resume"]

# How long a ticket waits for its WebSocket.
TICKET_SECONDS = 30.0

# How long a session that is hung up has to end before it is killed.
HANG_UP_SECONDS = 3.0

# How long the output of a process that ended may take to reach the page.
DRAIN_SECONDS = 0.5

# The terminal that the terminal panel emulates (xterm.js).
TERM = "xterm-256color"

# The color theme of Claude Code in the page, for the light terminal of the
# panel; the user's own setting, for their own terminal, stays as it is.
THEME = "light"

# Closing codes of the WebSocket: a ticket that is unknown or expired, and a
# session that another tab took over.
CLOSE_BAD_TICKET = 1008
CLOSE_TAKEN_OVER = 4001

# What follows the options of debasher_claude for each way of starting the
# conversation: Claude Code takes them after `--`.
START_ARGS: dict[str, list[str]] = {
    "new": [],
    "continue": ["--", "--continue"],
    "resume": ["--", "--resume"],
}

# Makes the pseudo-terminal on its standard input the controlling terminal of
# the new process session, then runs the command. A terminal that a process
# only inherits as a file descriptor is not its controlling terminal, and the
# hangup of a backend that dies would never reach it.
_ACQUIRE_TERMINAL = (
    "import fcntl, os, sys, termios; "
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0); "
    "os.execvp(sys.argv[1], sys.argv[1:])"
)


def claude_command(launcher: str, home_dir: str, url: str, start: Start) -> list[str]:
    """The command of a session: debasher_claude on the program, in the theme
    of the panel, and nothing that the page could choose but the way the
    conversation starts."""
    return [launcher, "--home-dir", home_dir, "--url", url, "--theme", THEME, *START_ARGS[start]]


def session_env(base: dict[str, str]) -> dict[str, str]:
    """
    The environment of a session: the backend's own, with the terminal that
    the terminal panel emulates and without the token, which the MCP server
    reads from the token file.
    """
    env = {name: value for name, value in base.items() if name != TOKEN_ENV_VAR}
    env["TERM"] = TERM
    return env


def set_terminal_size(fd: int, cols: int, rows: int) -> None:
    """Give the pseudo-terminal a size, which the kernel tells the process of
    the session about (SIGWINCH)."""
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


@dataclass
class Ticket:
    value: str
    home_dir: str
    command: list[str]
    cols: int
    rows: int
    expires: float


class SessionInUse(Exception):
    """The program has a session in the page, in another tab."""


class TerminalSession:
    """
    One session in the page: the process of debasher_claude in a
    pseudo-terminal, carried by the WebSocket of one tab, from its start to
    its end, whichever ends first.
    """

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._ended = asyncio.Event()
        self._taken_over = False

    async def take_over(self) -> None:
        """End the session for another tab, and wait until its process is
        gone, so that its conversation is complete on disk."""
        self._taken_over = True
        self._stop.set()
        await self._ended.wait()

    async def run(
        self,
        websocket: WebSocket,
        ticket: Ticket,
        env: dict[str, str],
        on_end: Callable[[], None],
    ) -> None:
        """
        Accept `websocket`, run the command of the ticket in a
        pseudo-terminal and carry it over the WebSocket until the process
        ends, the WebSocket closes or another tab takes the session over;
        `on_end` frees the place of the program.
        """
        master = None
        process = None
        tasks: list[asyncio.Task] = []
        try:
            await websocket.accept()
            master, slave = pty.openpty()
            set_terminal_size(master, ticket.cols, ticket.rows)
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", _ACQUIRE_TERMINAL, *ticket.command,
                    stdin=slave, stdout=slave, stderr=slave,
                    env=env, start_new_session=True,
                )
            finally:
                os.close(slave)
            os.set_blocking(master, False)

            output = asyncio.create_task(_pump_output(master, websocket))
            typed = asyncio.create_task(_pump_input(master, websocket))
            exited = asyncio.create_task(process.wait())
            stopped = asyncio.create_task(self._stop.wait())
            tasks = [output, typed, exited, stopped]
            done, _ = await asyncio.wait(
                {typed, exited, stopped}, return_when=asyncio.FIRST_COMPLETED
            )

            if exited in done:
                await asyncio.wait({output}, timeout=DRAIN_SECONDS)
                typed.cancel()
                await _close(websocket, json.dumps({"exit": process.returncode}), 1000)
            elif stopped in done and self._taken_over:
                typed.cancel()
                await _close(websocket, None, CLOSE_TAKEN_OVER)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if process is not None:
                await _hang_up(process)
            if master is not None:
                os.close(master)
            on_end()
            self._ended.set()


class Registry:
    """
    The registry of sessions: the place of each home directory, held by a
    ticket until it is used or expires, then by its session until it ends.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._tickets: dict[str, Ticket] = {}
        self._places: dict[str, Ticket | TerminalSession] = {}

    def _drop_expired(self) -> None:
        now = self._clock()
        for ticket in list(self._tickets.values()):
            if ticket.expires <= now:
                self._forget(ticket)

    def _forget(self, ticket: Ticket) -> None:
        self._tickets.pop(ticket.value, None)
        if self._places.get(ticket.home_dir) is ticket:
            del self._places[ticket.home_dir]

    async def reserve(
        self, home_dir: str, command: list[str], cols: int, rows: int, take_over: bool
    ) -> str:
        """
        A ticket for a session on `home_dir`, which holds the place of the
        program. A place already held raises SessionInUse, unless the
        request takes it over: then its ticket is dropped, or its session
        ended, before the new ticket is given.
        """
        while True:
            self._drop_expired()
            place = self._places.get(home_dir)
            if place is None:
                break
            if not take_over:
                raise SessionInUse(home_dir)
            if isinstance(place, Ticket):
                self._forget(place)
            else:
                # Another tab may ask while this one waits: look again.
                await place.take_over()

        ticket = Ticket(
            value=secrets.token_urlsafe(32),
            home_dir=home_dir,
            command=command,
            cols=cols,
            rows=rows,
            expires=self._clock() + TICKET_SECONDS,
        )
        self._tickets[ticket.value] = ticket
        self._places[home_dir] = ticket
        return ticket.value

    def redeem(self, value: str, session: TerminalSession) -> Ticket | None:
        """The ticket of `value`, which serves once, with its place given to
        `session`; None for a ticket that is unknown or expired."""
        self._drop_expired()
        ticket = self._tickets.pop(value, None)
        if ticket is None:
            return None
        self._places[ticket.home_dir] = session
        return ticket

    def release(self, home_dir: str, session: TerminalSession) -> None:
        """Free the place of a session that ended, unless another holds it."""
        if self._places.get(home_dir) is session:
            del self._places[home_dir]

    def holds(self, home_dir: str) -> bool:
        self._drop_expired()
        return home_dir in self._places


async def _wait_ready(fd: int, writing: bool) -> None:
    loop = asyncio.get_running_loop()
    ready = loop.create_future()

    def wake() -> None:
        if not ready.done():
            ready.set_result(None)

    if writing:
        loop.add_writer(fd, wake)
    else:
        loop.add_reader(fd, wake)
    try:
        await ready
    finally:
        if writing:
            loop.remove_writer(fd)
        else:
            loop.remove_reader(fd)


async def _pump_output(master: int, websocket: WebSocket) -> None:
    """What the process writes, to the page. The next read waits for the
    send, so a slow page slows the process down."""
    while True:
        try:
            data = os.read(master, 65536)
        except BlockingIOError:
            await _wait_ready(master, writing=False)
            continue
        except OSError:
            # EIO: no process holds the pseudo-terminal any longer.
            return
        if not data:
            return
        await websocket.send_bytes(data)


async def _pump_input(master: int, websocket: WebSocket) -> None:
    """What the user types, to the process, and the control messages of the
    page; ends when the WebSocket closes."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes"):
            await _write_all(master, message["bytes"])
        elif message.get("text"):
            _control(master, message["text"])


def _control(master: int, text: str) -> None:
    """A control message of the page; one that is not understood is
    ignored."""
    try:
        cols, rows = json.loads(text)["resize"]
        if isinstance(cols, int) and isinstance(rows, int) and cols > 0 and rows > 0:
            set_terminal_size(master, cols, rows)
    except (ValueError, TypeError, KeyError, struct.error):
        pass


async def _write_all(fd: int, data: bytes) -> None:
    while data:
        try:
            written = os.write(fd, data)
        except BlockingIOError:
            await _wait_ready(fd, writing=True)
            continue
        data = data[written:]


async def _close(websocket: WebSocket, last_text: str | None, code: int) -> None:
    """Close a WebSocket that the page may have closed already."""
    try:
        if last_text is not None:
            await websocket.send_text(last_text)
        await websocket.close(code=code)
    except (RuntimeError, OSError):
        pass


def _signal_group(pgid: int, signum: int) -> None:
    try:
        os.killpg(pgid, signum)
    except (ProcessLookupError, PermissionError):
        pass


async def _hang_up(process: asyncio.subprocess.Process) -> None:
    """
    End the process session of a session in the page, as a closed terminal
    does: SIGHUP to its group, then SIGKILL if it still lives a few seconds
    later. A process that already ended may leave others of its group
    behind, which get the hangup too.
    """
    _signal_group(process.pid, signal.SIGHUP)
    if process.returncode is not None:
        return
    try:
        await asyncio.wait_for(process.wait(), HANG_UP_SECONDS)
    except asyncio.TimeoutError:
        _signal_group(process.pid, signal.SIGKILL)
        await process.wait()
