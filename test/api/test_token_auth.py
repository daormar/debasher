import asyncio

import pytest

# The middleware answers with a response of starlette, which comes with
# fastapi (see test_fs_browse.py).
pytest.importorskip("fastapi")

from api import token_auth  # noqa: E402
from api.token_auth import TokenAuthMiddleware  # noqa: E402

TOKEN = "s3cret"
PAGES = frozenset({"/", "/index.html"})


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _request(path="/api/webui/info", method="GET", headers=None,
             hosts=token_auth.LOOPBACK_NAMES):
    """The status that the middleware answers a request with."""
    if headers is None:
        headers = {"host": "127.0.0.1:8000"}
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = TokenAuthMiddleware(_ok_app, token=TOKEN, hosts=hosts, pages=PAGES)
    asyncio.run(middleware(scope, receive, send))
    return sent[0]["status"]


def _with_token(token=TOKEN, host="127.0.0.1:8000"):
    return {"host": host, "authorization": f"Bearer {token}"}


def test_the_api_answers_a_request_with_the_token():
    assert _request(headers=_with_token()) == 200


def test_the_api_refuses_a_request_without_the_token_or_with_another():
    assert _request() == 401
    assert _request(headers=_with_token("other")) == 401
    assert _request(headers={"host": "127.0.0.1:8000", "authorization": TOKEN}) == 401


def test_the_page_is_served_without_the_token_but_nothing_else():
    assert _request(path="/") == 200
    assert _request(path="/index.html", method="HEAD") == 200
    assert _request(path="/", method="POST") == 401
    assert _request(path="/docs") == 401


def test_a_host_that_is_not_the_backend_is_refused_even_with_the_token():
    assert _request(headers=_with_token(host="malo.com:8000")) == 400
    assert _request(path="/", headers={"host": "malo.com:8000"}) == 400
    assert _request(headers={"authorization": f"Bearer {TOKEN}"}) == 400


def test_every_loopback_name_is_a_host_of_a_loopback_backend():
    for host in ("localhost:5173", "127.0.0.1", "[::1]:8000"):
        assert _request(headers=_with_token(host=host)) == 200


def test_a_backend_on_every_address_checks_no_host():
    assert _request(headers=_with_token(host="lab-server:8000"), hosts=None) == 200


def test_allowed_hosts_follow_the_address_listened_on():
    assert token_auth.allowed_hosts("127.0.0.1") == token_auth.LOOPBACK_NAMES
    assert token_auth.allowed_hosts("localhost") == token_auth.LOOPBACK_NAMES
    assert token_auth.allowed_hosts("0.0.0.0") is None
    assert token_auth.allowed_hosts("::") is None
    assert "192.168.1.20" in token_auth.allowed_hosts("192.168.1.20")
    assert "[fe80::1]" in token_auth.allowed_hosts("fe80::1")


def test_page_paths_are_the_files_of_the_built_frontend(tmp_path):
    (tmp_path / "index.html").write_text("")
    (tmp_path / "favicon.svg").write_text("")
    (tmp_path / "assets").mkdir()

    assert token_auth.page_paths(tmp_path) == {"/", "/index.html", "/favicon.svg"}
    assert token_auth.page_paths(None) == {"/"}


def test_the_backend_does_not_start_without_a_token(monkeypatch):
    monkeypatch.delenv(token_auth.TOKEN_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError):
        token_auth.token_from_env()

    monkeypatch.setenv(token_auth.TOKEN_ENV_VAR, "")
    with pytest.raises(RuntimeError):
        token_auth.token_from_env()


TICKETED = frozenset({"/api/claude/terminal"})


async def _ok_websocket_app(scope, receive, send):
    await send({"type": "websocket.accept"})


def _open_websocket(path="/api/claude/terminal", headers=None):
    """Whether the middleware lets a WebSocket through to its route."""
    if headers is None:
        headers = {"host": "127.0.0.1:8000"}
    scope = {
        "type": "websocket",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    middleware = TokenAuthMiddleware(
        _ok_websocket_app, token=TOKEN, hosts=token_auth.LOOPBACK_NAMES,
        pages=PAGES, ticketed=TICKETED,
    )
    asyncio.run(middleware(scope, receive, send))
    return sent[0]["type"] == "websocket.accept"


def test_the_websocket_of_a_session_goes_to_its_route_without_the_token():
    assert _open_websocket()
    assert not _open_websocket(path="/api/other")
    assert _open_websocket(path="/api/other", headers=_with_token())


def test_the_websocket_of_a_session_still_needs_a_host_of_the_backend():
    assert not _open_websocket(headers={"host": "malo.com:8000"})


def test_only_the_websocket_of_a_ticketed_path_is_spared_the_token():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/claude/terminal",
        "headers": [(b"host", b"127.0.0.1:8000")],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = TokenAuthMiddleware(
        _ok_app, token=TOKEN, hosts=token_auth.LOOPBACK_NAMES, pages=PAGES, ticketed=TICKETED
    )
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 401
