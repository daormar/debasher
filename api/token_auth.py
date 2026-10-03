"""
The token of the backend: every request but those for the page of the web UI
has to carry it in its Authorization header (`Bearer <token>`), since the
backend runs anything as the user who started it. The middleware also checks
the Host header, against a page whose own name was made to point to the local
machine (DNS rebinding).
"""

import ipaddress
import os
import secrets
from pathlib import Path

from starlette.responses import JSONResponse

# The token of the backend, which debasher_webui (api/serve.py) sets, and
# without which the backend does not start.
TOKEN_ENV_VAR = "DEBASHER_WEBUI_TOKEN"

# The address that the backend listens on, which api/serve.py sets; uvicorn
# started by hand listens on its default.
HOST_ENV_VAR = "DEBASHER_WEBUI_HOST"
DEFAULT_HOST = "127.0.0.1"

# The port that the backend listens on, which api/serve.py sets; unknown to a
# backend that uvicorn starts by hand.
PORT_ENV_VAR = "DEBASHER_WEBUI_PORT"

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "[::1]"})

REFUSED_DETAIL = (
    "The backend refused the request: it carries no valid token. Open the "
    "address with the token (#token=...) that debasher_webui printed when it "
    "started."
)


def token_from_env() -> str:
    token = os.environ.get(TOKEN_ENV_VAR, "")
    if not token:
        raise RuntimeError(
            f"{TOKEN_ENV_VAR} is not set: start the backend with debasher_webui, "
            f"or set {TOKEN_ENV_VAR} to a token of your own"
        )
    return token


def is_every_address(host: str) -> bool:
    return host in ("", "0.0.0.0", "::")


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def url_host(host: str) -> str:
    """`host` as the host of a URL: an IPv6 address between brackets."""
    return f"[{host}]" if ":" in host else host


def allowed_hosts(listen_host: str) -> frozenset[str] | None:
    """
    The hosts that a request may name in its Host header, for a backend that
    listens on `listen_host`; None when it listens on every address, and
    cannot know every name that it is reached by.
    """
    if is_every_address(listen_host):
        return None
    if is_loopback(listen_host):
        return LOOPBACK_NAMES
    return LOOPBACK_NAMES | {url_host(listen_host).lower()}


def host_name(host_header: str) -> str:
    """The host of a Host header, without its port."""
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        return host_header[: host_header.find("]") + 1]
    return host_header.split(":", 1)[0]


def page_paths(static_dir: Path | None) -> frozenset[str]:
    """
    The paths of the page of the web UI, which a GET or HEAD reaches without
    the token: `/` and the files of the built frontend, the same for every
    user and holding none of their data.
    """
    paths = {"/"}
    if static_dir is not None and static_dir.is_dir():
        paths |= {f"/{entry.name}" for entry in static_dir.iterdir() if entry.is_file()}
    return frozenset(paths)


def bearer_token(authorization: str) -> str | None:
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else None


class TokenAuthMiddleware:
    """Refuses every request without the token, but those for the page."""

    def __init__(self, app, token: str, hosts: frozenset[str] | None, pages: frozenset[str]):
        self.app = app
        self.token = token
        self.hosts = hosts
        self.pages = pages

    def _has_token(self, headers: dict[bytes, bytes]) -> bool:
        token = bearer_token(headers.get(b"authorization", b"").decode("latin-1"))
        return token is not None and secrets.compare_digest(
            token.encode(), self.token.encode()
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])

        if self.hosts is not None:
            host = headers.get(b"host")
            if host is None or host_name(host.decode("latin-1")) not in self.hosts:
                await self._refuse(scope, receive, send, 400, "Unknown host")
                return

        is_page = (
            scope["type"] == "http"
            and scope["method"] in ("GET", "HEAD")
            and scope["path"] in self.pages
        )
        if is_page or self._has_token(headers):
            await self.app(scope, receive, send)
            return

        await self._refuse(scope, receive, send, 401, REFUSED_DETAIL)

    async def _refuse(self, scope, receive, send, status: int, detail: str):
        if scope["type"] == "websocket":
            # Policy violation: a websocket is refused before it is accepted.
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
