import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (see test_fs_browse.py).
pytest.importorskip("fastapi")

from api.routers.webui import CLAUDE_CODE_ENV_VAR, get_webui_info  # noqa: E402


def test_claude_code_is_offered_by_default(monkeypatch):
    monkeypatch.delenv(CLAUDE_CODE_ENV_VAR, raising=False)

    assert get_webui_info().claudeCode is True


def test_claude_code_is_not_offered_when_turned_off(monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_ENV_VAR, "no")

    assert get_webui_info().claudeCode is False


def test_claude_code_is_offered_for_any_other_value(monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_ENV_VAR, "yes")

    assert get_webui_info().claudeCode is True
