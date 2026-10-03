import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# The backend that api/serve.py starts needs the dependencies of the API.
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from api import serve  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_token_file_is_private_and_holds_the_backend(tmp_path):
    directory = tmp_path / "debasher"
    assert serve.private_dir(directory)
    path = directory / "webui-8000.token"

    serve.write_token_file(path, "tok", os.getpid())

    assert directory.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    content = json.loads(path.read_text())
    assert content["token"] == "tok"
    assert content["pid"] == os.getpid()
    assert content["started"] == serve.process_start_time(os.getpid()) != ""
    assert [p.name for p in directory.iterdir()] == ["webui-8000.token"]


def test_a_directory_open_to_others_is_not_private(tmp_path):
    directory = tmp_path / "debasher"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)

    assert not serve.private_dir(directory)


def test_the_token_file_of_another_backend_is_not_removed(tmp_path):
    path = tmp_path / "webui-8000.token"
    serve.write_token_file(path, "theirs", os.getpid())

    serve.remove_token_file(path, "mine")
    assert path.exists()

    serve.remove_token_file(path, "theirs")
    assert not path.exists()


def test_the_token_url_names_a_host_that_a_browser_opens():
    assert serve.token_url("127.0.0.1", 8000, "t") == "http://127.0.0.1:8000/#token=t"
    assert serve.token_url("0.0.0.0", 8000, "t") == "http://localhost:8000/#token=t"
    assert serve.token_url("::1", 8001, "t") == "http://[::1]:8001/#token=t"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url, token=None):
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code


def _start(port, env):
    return subprocess.Popen(
        [sys.executable, "-m", "api.serve", "--port", str(port)],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _wait_for(condition, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def test_a_backend_owns_its_token_file_from_bind_to_stop(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(mode=0o700)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime_dir)}
    env.pop("DEBASHER_WEBUI_TOKEN", None)
    port = _free_port()
    path = runtime_dir / "debasher" / f"webui-{port}.token"

    backend = _start(port, env)
    try:
        assert _wait_for(lambda: path.exists() and _get(f"http://127.0.0.1:{port}/") == 200)
        token = json.loads(path.read_text())["token"]

        assert _get(f"http://127.0.0.1:{port}/api/webui/info") == 401
        assert _get(f"http://127.0.0.1:{port}/api/webui/info", token) == 200

        # A second backend on the same port ends without touching the file.
        second = _start(port, env)
        assert second.wait(timeout=20) == 1
        assert json.loads(path.read_text())["token"] == token

        backend.send_signal(signal.SIGTERM)
        output, _ = backend.communicate(timeout=20)
    finally:
        if backend.poll() is None:
            backend.kill()

    assert f"http://127.0.0.1:{port}/#token={token}" in output
    assert not path.exists()
