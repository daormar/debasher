import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (see test_fs_browse.py).
pytest.importorskip("fastapi")

from api.routers import webui  # noqa: E402
from api.routers.webui import (  # noqa: E402
    CLAUDE_CODE_ENV_VAR,
    CLAUDE_CODE_INSTALL_ENV_VAR,
    CLAUDE_CODE_PREFIX_ENV_VAR,
    CLAUDE_CODE_TERMINAL_ENV_VAR,
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


@pytest.fixture
def terminal_offered(monkeypatch):
    """A backend that debasher_webui started, with debasher_claude."""
    monkeypatch.setenv(PORT_ENV_VAR, "8000")
    monkeypatch.setenv(HOST_ENV_VAR, "127.0.0.1")
    monkeypatch.delenv(CLAUDE_CODE_ENV_VAR, raising=False)
    monkeypatch.delenv(CLAUDE_CODE_TERMINAL_ENV_VAR, raising=False)
    monkeypatch.setattr(webui, "find_bin_tool", lambda name: "/usr/bin/" + name)


def test_claude_code_runs_in_the_page_by_default(terminal_offered):
    assert get_webui_info().claudeCodeTerminal is True


def test_claude_code_in_the_page_can_be_turned_off_alone(terminal_offered, monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_TERMINAL_ENV_VAR, "no")

    assert get_webui_info().claudeCodeTerminal is False
    assert get_webui_info().claudeCode is True


def test_claude_code_turned_off_does_not_run_in_the_page(terminal_offered, monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_ENV_VAR, "no")

    assert get_webui_info().claudeCodeTerminal is False


def test_a_backend_started_by_hand_does_not_run_claude_code_in_the_page(
    terminal_offered, monkeypatch
):
    monkeypatch.delenv(PORT_ENV_VAR)

    assert get_webui_info().claudeCodeTerminal is False


def test_without_debasher_claude_claude_code_does_not_run_in_the_page(
    terminal_offered, monkeypatch
):
    monkeypatch.setattr(webui, "find_bin_tool", lambda name: None)

    assert get_webui_info().claudeCodeTerminal is False
