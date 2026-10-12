import asyncio
import json
import os
import stat
import sys
import time

import pytest

# The routes under test import fastapi, which the system Python used by
# `make check` may not have (see test_fs_browse.py).
pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from starlette.websockets import WebSocket  # noqa: E402

from api import claude_sessions  # noqa: E402
from api.claude_sessions import (  # noqa: E402
    CLOSE_BAD_TICKET,
    CLOSE_TAKEN_OVER,
    Registry,
    SessionInUse,
    TerminalSession,
    claude_command,
    session_env,
)
from api.persistence import METADATA_DIRNAME, PROGRAM_FILENAME  # noqa: E402
from api.routers import claude  # noqa: E402
from api.routers.claude import SessionRequest, request_session, terminal  # noqa: E402
from api.routers.webui import (  # noqa: E402
    CLAUDE_CODE_ENV_VAR,
    CLAUDE_CODE_TERMINAL_ENV_VAR,
)
from api.token_auth import HOST_ENV_VAR, PORT_ENV_VAR, TOKEN_ENV_VAR  # noqa: E402

# How long a test waits for the session to answer before it fails.
WAIT = 10.0

# A launcher that stands in for debasher_claude, in Python rather than Bash,
# which takes a terminal on its standard input for its controlling one by
# itself: it writes down its arguments, its environment, whether it has a
# controlling terminal and its PID, and answers what it reads, a line at a
# time, until it is told to end or reads nothing for a while.
FAKE_LAUNCHER = r"""
import fcntl, os, select, struct, sys, termios

out = os.environ["FAKE_DIR"]
def note(name, text):
    with open(os.path.join(out, name), "w") as f:
        f.write(text)

note("args", "\n".join(sys.argv[1:]) + "\n")
note("env", "".join(f"{k}={v}\n" for k, v in os.environ.items()))
try:
    os.close(os.open("/dev/tty", os.O_RDWR))
    note("tty", "controlling")
except OSError:
    note("tty", "none")
note("pid", str(os.getpid()))

attrs = termios.tcgetattr(0)
attrs[3] &= ~termios.ECHO
termios.tcsetattr(0, termios.TCSANOW, attrs)
def say(text):
    os.write(1, (text + "\r\n").encode())

say("READY")
line = b""
while select.select([0], [], [], 20)[0]:
    data = os.read(0, 1024)
    if not data:
        break
    line += data
    while b"\n" in line:
        text, line = line.split(b"\n", 1)
        text = text.decode().strip()
        if text == "size":
            rows, cols = struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, bytes(8)))[:2]
            say(f"size:{rows} {cols}")
        elif text.startswith("exit"):
            sys.exit(int(text.split()[1]))
        else:
            say(f"got:{text}")
"""

@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A backend that offers sessions in the page, with the stand-in
    launcher, a fresh registry and a saved program."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    launcher = bin_dir / "debasher_claude"
    launcher.write_text(f"#!{sys.executable}\n{FAKE_LAUNCHER}")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    home_dir = tmp_path / "program"
    (home_dir / METADATA_DIRNAME).mkdir(parents=True)
    (home_dir / METADATA_DIRNAME / PROGRAM_FILENAME).write_text("{}")

    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()

    monkeypatch.setenv("DEBASHER_WEBUI_BIN_DIR", str(bin_dir))
    monkeypatch.setenv(PORT_ENV_VAR, "8000")
    monkeypatch.setenv(HOST_ENV_VAR, "127.0.0.1")
    monkeypatch.setenv(TOKEN_ENV_VAR, "s3cret")
    monkeypatch.setenv("FAKE_DIR", str(fake_dir))
    monkeypatch.delenv(CLAUDE_CODE_ENV_VAR, raising=False)
    monkeypatch.delenv(CLAUDE_CODE_TERMINAL_ENV_VAR, raising=False)
    monkeypatch.setattr(claude, "registry", Registry())

    class Fake:
        home = home_dir
        dir = fake_dir
        bin = launcher

        def args(self):
            return (fake_dir / "args").read_text().splitlines()

        def env(self):
            lines = (fake_dir / "env").read_text().splitlines()
            return dict(line.split("=", 1) for line in lines if "=" in line)

        def pid(self):
            return int((fake_dir / "pid").read_text())

    return Fake()


class Peer:
    """The page at the other end of the WebSocket of a session."""

    def __init__(self) -> None:
        self.to_app: asyncio.Queue = asyncio.Queue()
        self.from_app: asyncio.Queue = asyncio.Queue()
        self.to_app.put_nowait({"type": "websocket.connect"})
        self.output = b""

    def websocket(self, ticket: str) -> WebSocket:
        scope = {
            "type": "websocket",
            "path": claude.TERMINAL_PATH,
            "query_string": f"ticket={ticket}".encode(),
            "headers": [],
        }
        return WebSocket(scope, self.to_app.get, self.from_app.put)

    async def next(self) -> dict:
        return await asyncio.wait_for(self.from_app.get(), WAIT)

    async def read_until(self, marker: bytes) -> bytes:
        while marker not in self.output:
            message = await self.next()
            if message["type"] == "websocket.accept":
                continue
            assert message["type"] == "websocket.send", message
            self.output += message.get("bytes") or b""
        return self.output

    def type(self, text: str) -> None:
        self.to_app.put_nowait({"type": "websocket.receive", "bytes": text.encode()})

    def control(self, value: dict) -> None:
        self.to_app.put_nowait({"type": "websocket.receive", "text": json.dumps(value)})

    def disconnect(self) -> None:
        self.to_app.put_nowait({"type": "websocket.disconnect", "code": 1001})

    async def closing(self) -> dict:
        """The message that ends the session for the page: the exit status
        and the close, or the close alone."""
        ending = {}
        while True:
            message = await self.next()
            if message["type"] == "websocket.send" and message.get("text"):
                ending.update(json.loads(message["text"]))
            elif message["type"] == "websocket.close":
                ending["code"] = message.get("code", 1000)
                return ending


async def _open(home_dir, **request):
    """A session on `home_dir`: its page, and the task of its WebSocket,
    once the launcher is ready."""
    answer = await request_session(SessionRequest(homeDir=str(home_dir), **request))
    peer = Peer()
    task = asyncio.create_task(terminal(peer.websocket(answer.ticket), answer.ticket))
    await peer.read_until(b"READY")
    return peer, task


async def _gone(pid: int) -> bool:
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.05)
    return False


def test_the_command_is_debasher_claude_on_the_program_and_how_it_starts():
    base = ["claude_launcher", "--home-dir", "/p", "--url", "http://127.0.0.1:8000"]

    assert claude_command("claude_launcher", "/p", "http://127.0.0.1:8000", "new") == base
    assert claude_command("claude_launcher", "/p", "http://127.0.0.1:8000", "continue") == [
        *base, "--", "--continue"
    ]
    assert claude_command("claude_launcher", "/p", "http://127.0.0.1:8000", "resume") == [
        *base, "--", "--resume"
    ]


def test_the_session_has_the_environment_of_the_backend_without_the_token():
    env = session_env({"PATH": "/bin", TOKEN_ENV_VAR: "s3cret", "TERM": "dumb"})

    assert env == {"PATH": "/bin", "TERM": "xterm-256color"}


def test_a_ticket_opens_a_session_of_debasher_claude_in_a_terminal(fake):
    async def scenario():
        peer, task = await _open(fake.home, cols=100, rows=40)

        assert fake.args() == [
            "--home-dir", os.path.realpath(fake.home), "--url", "http://127.0.0.1:8000"
        ]
        # The terminal is the controlling one, so that the hangup of a backend
        # that dies reaches the process.
        assert (fake.dir / "tty").read_text() == "controlling"
        assert TOKEN_ENV_VAR not in fake.env()
        assert fake.env()["TERM"] == "xterm-256color"

        peer.type("size\n")
        assert b"size:40 100" in await peer.read_until(b"size:")

        peer.type("exit 0\n")
        await peer.closing()
        await task

    asyncio.run(scenario())


def test_what_is_typed_reaches_the_process_and_its_output_the_page(fake):
    async def scenario():
        peer, task = await _open(fake.home)

        peer.type("hello\n")
        assert b"got:hello" in await peer.read_until(b"got:hello")

        peer.type("exit 0\n")
        await peer.closing()
        await task

    asyncio.run(scenario())


def test_a_resize_reaches_the_terminal_and_bad_controls_are_ignored(fake):
    async def scenario():
        peer, task = await _open(fake.home)

        peer.control({"resize": [120, 30]})
        peer.control({"resize": ["wide", 30]})
        peer.control({"other": 1})
        peer.to_app.put_nowait({"type": "websocket.receive", "text": "not json"})
        peer.type("size\n")
        assert b"size:30 120" in await peer.read_until(b"size:")

        peer.type("exit 0\n")
        await peer.closing()
        await task

    asyncio.run(scenario())


def test_the_end_of_the_process_is_reported_and_frees_the_program(fake):
    async def scenario():
        peer, task = await _open(fake.home)

        peer.type("exit 3\n")
        assert await peer.closing() == {"exit": 3, "code": 1000}
        await task

        assert not claude.registry.holds(os.path.realpath(fake.home))

    asyncio.run(scenario())


def test_a_closed_websocket_ends_the_process_and_frees_the_program(fake):
    async def scenario():
        peer, task = await _open(fake.home)
        pid = fake.pid()

        peer.disconnect()
        await asyncio.wait_for(task, WAIT)

        assert await _gone(pid)
        assert not claude.registry.holds(os.path.realpath(fake.home))

    asyncio.run(scenario())


def test_a_ticket_serves_once(fake):
    async def scenario():
        answer = await request_session(SessionRequest(homeDir=str(fake.home)))
        peer = Peer()
        task = asyncio.create_task(terminal(peer.websocket(answer.ticket), answer.ticket))
        await peer.read_until(b"READY")

        again = Peer()
        await terminal(again.websocket(answer.ticket), answer.ticket)
        assert await again.next() == {"type": "websocket.close", "code": CLOSE_BAD_TICKET, "reason": ""}

        peer.type("exit 0\n")
        await peer.closing()
        await task

    asyncio.run(scenario())


def test_an_unknown_ticket_is_refused_before_the_websocket_opens(fake):
    async def scenario():
        peer = Peer()
        await terminal(peer.websocket("forged"), "forged")
        message = await peer.next()
        assert message["type"] == "websocket.close"
        assert message["code"] == CLOSE_BAD_TICKET

    asyncio.run(scenario())


def test_a_ticket_expires_and_frees_the_program():
    now = [100.0]
    registry = Registry(clock=lambda: now[0])

    async def scenario():
        ticket = await registry.reserve("/p", ["cmd"], 80, 24, take_over=False)
        assert registry.holds("/p")

        now[0] += claude_sessions.TICKET_SECONDS
        assert registry.redeem(ticket, TerminalSession()) is None
        assert not registry.holds("/p")

    asyncio.run(scenario())


def test_a_second_session_on_a_program_is_refused(fake):
    async def scenario():
        await request_session(SessionRequest(homeDir=str(fake.home)))
        with pytest.raises(HTTPException) as refused:
            await request_session(SessionRequest(homeDir=str(fake.home)))
        assert refused.value.status_code == 409

        # The first ticket is still pending: take its place over.
        peer, task = await _open(fake.home, takeOver=True)
        with pytest.raises(HTTPException) as refused:
            await request_session(SessionRequest(homeDir=str(fake.home)))
        assert refused.value.status_code == 409

        peer.type("exit 0\n")
        await peer.closing()
        await task

    asyncio.run(scenario())


def test_a_take_over_ends_the_other_session_and_continues_its_conversation(fake):
    async def scenario():
        first, first_task = await _open(fake.home)
        first_pid = fake.pid()

        second, second_task = await _open(fake.home, start="new", takeOver=True)

        assert await first.closing() == {"code": CLOSE_TAKEN_OVER}
        await first_task
        assert await _gone(first_pid)
        assert fake.args()[-2:] == ["--", "--continue"]

        second.type("exit 0\n")
        await second.closing()
        await second_task

    asyncio.run(scenario())


def test_reserving_a_held_place_without_taking_it_over_raises():
    registry = Registry()

    async def scenario():
        await registry.reserve("/p", ["cmd"], 80, 24, take_over=False)
        with pytest.raises(SessionInUse):
            await registry.reserve("/p", ["cmd"], 80, 24, take_over=False)
        await registry.reserve("/q", ["cmd"], 80, 24, take_over=False)

    asyncio.run(scenario())


def test_a_program_that_is_not_saved_gets_no_session(fake, tmp_path):
    async def scenario():
        with pytest.raises(HTTPException) as refused:
            await request_session(SessionRequest(homeDir=str(tmp_path / "nothing")))
        assert refused.value.status_code == 404

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "setting",
    [
        (CLAUDE_CODE_ENV_VAR, "no"),
        (CLAUDE_CODE_TERMINAL_ENV_VAR, "no"),
        (PORT_ENV_VAR, None),
        ("DEBASHER_WEBUI_BIN_DIR", "/nonexistent"),
    ],
)
def test_a_backend_that_offers_no_session_answers_503(fake, monkeypatch, setting):
    name, value = setting
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    if name == "DEBASHER_WEBUI_BIN_DIR":
        # The lookup falls back to the build and the local install.
        monkeypatch.setattr(claude, "find_bin_tool", lambda name: None)
        monkeypatch.setattr("api.routers.webui.find_bin_tool", lambda name: None)

    async def scenario():
        with pytest.raises(HTTPException) as refused:
            await request_session(SessionRequest(homeDir=str(fake.home)))
        assert refused.value.status_code == 503
        assert refused.value.detail

    asyncio.run(scenario())
