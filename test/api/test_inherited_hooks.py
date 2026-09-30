"""
The hooks that a node inherits from its class of the runtime library (see
api/inherited_hooks.py), read from the library itself for the node code
editor.
"""

import pytest

from api import inherited_hooks, paths
from api.resident_node_code import NODE_HOOKS


@pytest.mark.parametrize("kind", ["ProgramLauncher", "DirectoryWatcher"])
def test_every_hook_of_a_class_of_the_library_is_read_with_its_signature(kind):
    hooks = inherited_hooks.inherited_hooks(kind)

    assert set(hooks) == {field for field, _, _ in NODE_HOOKS}
    for field, hook, params in NODE_HOOKS:
        assert hooks[field].startswith(f"def {hook}{params}:")
        # Dedented: the method as it would be written at the top level.
        assert not hooks[field].startswith(" ")


def test_the_code_is_the_one_the_node_runs():
    hooks = inherited_hooks.inherited_hooks("ProgramLauncher")

    assert "self._register(packet)" in hooks["processData"]
    assert '"announced"' in hooks["captureNodeState"]


def test_a_node_kind_whose_class_implements_no_hook_inherits_nothing():
    assert inherited_hooks.inherited_hooks("FBPProcess") == {}
    assert inherited_hooks.inherited_hooks("Supervisor") == {}


def test_a_runtime_library_that_is_not_found_is_an_error(monkeypatch):
    monkeypatch.setattr(paths, "find_runtime_module", lambda name: None)

    with pytest.raises(inherited_hooks.InheritedHooksError, match="not found"):
        inherited_hooks.inherited_hooks("ProgramLauncher")


def test_the_installed_library_comes_first(tmp_path, monkeypatch):
    (tmp_path / "debasher_runtime_launcher.py").write_text(
        "class ProgramLauncher:\n    def observe(self):\n        return 'installed'\n"
    )
    monkeypatch.setenv("DEBASHER_WEBUI_PYTHON_DIR", str(tmp_path))

    assert paths.find_runtime_module("debasher_runtime_launcher.py") == tmp_path / "debasher_runtime_launcher.py"
    assert inherited_hooks.inherited_hooks("ProgramLauncher") == {
        "observe": "def observe(self):\n    return 'installed'"
    }


def test_without_the_launcher_a_local_install_comes_before_the_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("DEBASHER_WEBUI_PYTHON_DIR", raising=False)
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path)
    name = "debasher_runtime_launcher.py"
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / name).write_text("")

    assert paths.find_runtime_module(name) == tmp_path / "engine" / name

    installed = tmp_path / "lib" / "python3.12" / "site-packages"
    installed.mkdir(parents=True)
    (installed / name).write_text("")

    assert paths.find_runtime_module(name) == installed / name
