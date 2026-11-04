import paths


def test_find_bin_tool_finds_uninstalled_dev_build(tmp_path, monkeypatch):
    # The SDK, imported by other tests of the same run, sets the variable
    # from its installation module
    monkeypatch.delenv("DEBASHER_WEBUI_BIN_DIR", raising=False)
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    tool = engine_dir / "debasher_exec"
    tool.write_text("#!/bin/bash\n")

    assert paths.find_bin_tool("debasher_exec") == tool


def test_find_bin_tool_prefers_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)
    (tmp_path / "engine").mkdir()
    override_dir = tmp_path / "custom_bin"
    override_dir.mkdir()
    tool = override_dir / "debasher_exec"
    tool.write_text("#!/bin/bash\n")
    monkeypatch.setenv("DEBASHER_WEBUI_BIN_DIR", str(override_dir))

    assert paths.find_bin_tool("debasher_exec") == tool


def test_find_bin_tool_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)
    (tmp_path / "engine").mkdir()

    assert paths.find_bin_tool("does_not_exist") is None
