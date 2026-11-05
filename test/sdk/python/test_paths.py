"""
Where the SDK finds the API of the web UI and the tools of the engine
(sdk/python/debasher/_paths.py), and the launcher debasher_build: `api`
is made importable only when it is not, from the root of the repository
in a source tree, else from the installed package data directory; the
variables that point the API at the tools of the engine are set only
when unset and their directory exists; a Python without the dependencies
of the SDK stops the launcher with what to install.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from debasher import _paths


@pytest.fixture
def path_copy(monkeypatch):
    """sys.path as a copy that the test may change."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    return sys.path


def _install(monkeypatch, **dirs):
    monkeypatch.setattr(_paths, "_install_dirs", lambda: dirs)


_VARIABLES = ("DEBASHER_WEBUI_BIN_DIR", "DEBASHER_WEBUI_LIBEXEC_DIR", "DEBASHER_WEBUI_PYTHON_DIR")


def test_the_variables_of_the_tools_are_set_only_when_unset_and_their_directory_exists(tmp_path, monkeypatch):
    for variable in _VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DEBASHER_WEBUI_PYTHON_DIR", "/given")
    _install(monkeypatch, BINDIR=str(tmp_path), LIBEXECDIR=str(tmp_path / "missing"), PYTHONDIR=str(tmp_path))

    _paths.locate_api()

    assert os.environ["DEBASHER_WEBUI_BIN_DIR"] == str(tmp_path)
    assert "DEBASHER_WEBUI_LIBEXEC_DIR" not in os.environ
    assert os.environ["DEBASHER_WEBUI_PYTHON_DIR"] == "/given"


def test_outside_a_source_tree_the_api_comes_from_the_package_data_directory(tmp_path, monkeypatch, path_copy):
    monkeypatch.setattr(_paths, "_api_importable", lambda: False)
    monkeypatch.setattr(_paths, "_REPO_ROOT", tmp_path)
    _install(monkeypatch, PKGDATADIR="/installed/share/debasher")

    _paths.locate_api()

    assert path_copy[-1] == "/installed/share/debasher"


def test_in_a_source_tree_the_api_comes_from_the_root_of_the_repository(tmp_path, monkeypatch, path_copy):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "__init__.py").write_text("")
    monkeypatch.setattr(_paths, "_api_importable", lambda: False)
    monkeypatch.setattr(_paths, "_REPO_ROOT", tmp_path)
    _install(monkeypatch, PKGDATADIR="/installed/share/debasher")

    _paths.locate_api()

    assert path_copy[-1] == str(tmp_path)


def test_an_api_already_importable_is_left_as_it_is(monkeypatch, path_copy):
    before = list(path_copy)
    monkeypatch.setattr(_paths, "_api_importable", lambda: True)
    _install(monkeypatch, PKGDATADIR="/installed/share/debasher")

    _paths.locate_api()

    assert path_copy == before


# The launcher is built by make beside its source; a source tree that has
# not been built has none
_LAUNCHER = Path(__file__).resolve().parents[3] / "sdk" / "python" / "debasher_build"


@pytest.mark.skipif(not _LAUNCHER.is_file(), reason="the launcher debasher_build is not built")
def test_the_launcher_stops_with_what_to_install_when_its_python_lacks_the_dependencies(tmp_path):
    # A Python that fails every import, as one without pydantic 2 does
    python = tmp_path / "python3"
    python.write_text("#!/bin/sh\nexit 1\n")
    python.chmod(0o755)

    result = subprocess.run(
        [str(_LAUNCHER), "prg.py"],
        cwd=tmp_path,
        env={**os.environ, "DEBASHER_WEBUI_PYTHON": str(python)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "the Python packages required by the SDK are not installed" in result.stderr
    assert f"for interpreter: {python}" in result.stderr
    assert "pip install -r" in result.stderr
