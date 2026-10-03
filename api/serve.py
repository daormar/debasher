"""
Starts the backend of the web UI for debasher_webui, so that the token file
follows the backend that owns the port: the address is bound first, the token
file written only then, the bound socket handed to uvicorn, and the token file
removed, when uvicorn stops, before the port is released.

The token file (webui-<port>.token, in the user's private runtime directory)
holds the token of the backend for debasher_mcp to read by itself, with the PID
of the backend and the time at which it started, so that a token file left by
a backend that died is not taken for that of a live one.
"""

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

from .token_auth import HOST_ENV_VAR, PORT_ENV_VAR, TOKEN_ENV_VAR, is_every_address, url_host

DEFAULT_PORT = 8000


def token_dir() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "debasher"
    return Path.home() / ".debasher" / "run"


def token_file_path(port: int) -> Path:
    return token_dir() / f"webui-{port}.token"


def process_start_time(pid: int) -> str:
    """
    When the process `pid` started, as `ps -o lstart=` prints it, which
    debasher_mcp compares with the same command: in the C locale and in UTC,
    so that both read the same text whatever their environment. Empty when it
    cannot be told, as where there is no ps (a slim container image).
    """
    env = {**os.environ, "LC_ALL": "C", "TZ": "UTC"}
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True, text=True, env=env, check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def private_dir(directory: Path) -> bool:
    """
    Creates `directory` readable only by the user if it is missing, and tells
    whether it is fit for the token file: the user's own, with no access for
    anyone else.
    """
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.stat()
    except OSError:
        return False
    return info.st_uid == os.getuid() and info.st_mode & 0o077 == 0


def write_token_file(path: Path, token: str, pid: int, started: str) -> None:
    """
    Writes the token file through a new temporary file, readable only by the
    user from the start, that then takes its name, so that a reader never sees
    half of it.
    """
    content = json.dumps({"token": token, "pid": pid, "started": started})
    temp_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def remove_token_file(path: Path, token: str) -> None:
    """Removes the token file if it still holds `token`, and not another's."""
    try:
        if json.loads(path.read_text()).get("token") == token:
            path.unlink()
    except (OSError, ValueError, AttributeError):
        pass


def bind(host: str, port: int) -> socket.socket:
    """
    A socket bound to `host` and `port` and listening. It never takes
    SO_REUSEPORT, which would let another process bind the same port.
    """
    family, kind, proto, _, address = socket.getaddrinfo(
        host or None, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )[0]
    sock = socket.socket(family, kind, proto)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(2048)
    except BaseException:
        sock.close()
        raise
    return sock


def token_url(host: str, port: int, token: str) -> str:
    # No browser opens the address of every address: the local machine does.
    shown = "localhost" if is_every_address(host) else url_host(host)
    return f"http://{shown}:{port}/#token={token}"


def exit_on_signal(signum, frame):
    """
    Ends the backend through the cleanup of main. uvicorn stops on SIGTERM and
    SIGINT and then raises the signal again with the handler found before it,
    and the default one of SIGTERM would end the process before the token file
    is removed.
    """
    raise SystemExit(128 + signum)


def stop_on_hangup(signum, frame):
    """
    Stops the backend as SIGTERM does when its terminal closes (SIGHUP), which
    uvicorn leaves alone, so that it ends in order and removes the token file.
    """
    signal.raise_signal(signal.SIGTERM)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="debasher_webui")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    signal.signal(signal.SIGTERM, exit_on_signal)
    signal.signal(signal.SIGHUP, stop_on_hangup)

    token = os.environ.get(TOKEN_ENV_VAR) or secrets.token_hex(24)
    os.environ[TOKEN_ENV_VAR] = token
    os.environ[HOST_ENV_VAR] = args.host
    os.environ[PORT_ENV_VAR] = str(args.port)

    try:
        sock = bind(args.host, args.port)
    except OSError as err:
        print(f"debasher_webui: cannot listen on {args.host}:{args.port}: {err}", file=sys.stderr)
        return 1

    # A copy of the socket keeps the port bound after uvicorn closes its own,
    # until the token file is removed.
    held = sock.dup()
    path = token_file_path(args.port)
    try:
        # Without the time at which the backend started, debasher_mcp could
        # not tell it from a process that took its PID after it died.
        started = process_start_time(os.getpid())
        if not started:
            print(
                "debasher_webui: cannot tell when this process started (is ps "
                "installed?): no token file written, so debasher_mcp will not "
                "find the token",
                file=sys.stderr,
            )
        elif private_dir(path.parent):
            write_token_file(path, token, os.getpid(), started)
        else:
            print(
                f"debasher_webui: {path.parent} is not private to you: no token file "
                "written, so debasher_mcp will not find the token",
                file=sys.stderr,
            )

        print(
            "Open the web interface at this address, which holds its token:\n\n"
            f"    {token_url(args.host, args.port, token)}\n",
            file=sys.stderr,
        )

        config = uvicorn.Config("api.main:app", host=args.host, port=args.port)
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        remove_token_file(path, token)
        held.close()
        sock.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(128 + signal.SIGINT)
