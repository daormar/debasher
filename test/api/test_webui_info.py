import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (see test_fs_browse.py).
pytest.importorskip("fastapi")

from api.routers.webui import (  # noqa: E402
    CLAUDE_CODE_ENV_VAR,
    CLAUDE_CODE_INSTALL_ENV_VAR,
    CLAUDE_CODE_PREFIX_ENV_VAR,
    get_webui_info,
)
from api.token_auth import HOST_ENV_VAR, PORT_ENV_VAR  # noqa: E402


def test_claude_code_is_offered_by_default(monkeypatch):
    monkeypatch.delenv(CLAUDE_CODE_ENV_VAR, raising=False)

    assert get_webui_info().claudeCode is True


def test_claude_code_is_not_offered_when_turned_off(monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_ENV_VAR, "no")

    assert get_webui_info().claudeCode is False


def test_claude_code_is_offered_for_any_other_value(monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_ENV_VAR, "yes")

    assert get_webui_info().claudeCode is True


def test_the_command_runs_through_the_prefix_given(monkeypatch):
    monkeypatch.delenv(CLAUDE_CODE_PREFIX_ENV_VAR, raising=False)
    monkeypatch.delenv(CLAUDE_CODE_INSTALL_ENV_VAR, raising=False)
    assert get_webui_info().claudeCodePrefix is None
    assert get_webui_info().claudeCodeInstall is None

    monkeypatch.setenv(CLAUDE_CODE_PREFIX_ENV_VAR, "docker compose exec -it debasher")
    monkeypatch.setenv(CLAUDE_CODE_INSTALL_ENV_VAR, "docker compose exec -it debasher install-claude-code")
    assert get_webui_info().claudeCodePrefix == "docker compose exec -it debasher"
    assert get_webui_info().claudeCodeInstall == "docker compose exec -it debasher install-claude-code"


def test_the_backend_url_is_the_address_listened_on(monkeypatch):
    monkeypatch.setenv(PORT_ENV_VAR, "8000")

    monkeypatch.setenv(HOST_ENV_VAR, "127.0.0.1")
    assert get_webui_info().backendUrl == "http://127.0.0.1:8000"

    monkeypatch.setenv(HOST_ENV_VAR, "0.0.0.0")
    assert get_webui_info().backendUrl == "http://127.0.0.1:8000"

    monkeypatch.setenv(HOST_ENV_VAR, "::1")
    assert get_webui_info().backendUrl == "http://[::1]:8000"


def test_a_backend_started_by_hand_gives_no_url(monkeypatch):
    monkeypatch.delenv(PORT_ENV_VAR, raising=False)

    assert get_webui_info().backendUrl is None
