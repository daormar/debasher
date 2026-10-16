"""
Where the SDK finds the API of the web UI (the package `api`, whose model,
script generation and persistence it builds on) and the tools of the
engine.

The package `api` is installed as data under the package data directory
(`$(pkgdatadir)/api`), not as a Python package, so it is importable only
from a directory on `sys.path`: in the source tree, the root of the
repository, found from this file; once installed, the directory that
`_install.py` names, a module that `make` writes with the directories of
the installation and that the source tree does not have. The tools of the
engine are found by `api.paths` through the environment variables that
the installed `debasher_webui` sets; the SDK sets them the same way from
`_install.py`, when they are not set already.
"""

import os
import sys
from pathlib import Path

# sdk/python/debasher/_paths.py: the root of the repository is three
# directories up
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _install_dirs() -> dict[str, str]:
    try:
        from . import _install
    except ImportError:
        return {}
    return {
        name: getattr(_install, name, "")
        for name in ("PKGDATADIR", "BINDIR", "LIBEXECDIR", "PYTHONDIR")
    }


def _api_importable() -> bool:
    try:
        import api  # noqa: F401
    except ImportError:
        return False
    return True


def locate_api() -> None:
    """
    Makes the package `api` importable, when it is not yet: from the
    source tree when this file is in one, else from the installed package
    data directory. Also points `api.paths` at the installed tools of the
    engine, through the variables that `debasher_webui` sets, when the
    installation is known and the variables are not set.
    """
    dirs = _install_dirs()
    if not _api_importable():
        if (_REPO_ROOT / "api" / "__init__.py").is_file():
            sys.path.append(str(_REPO_ROOT))
        elif dirs.get("PKGDATADIR"):
            sys.path.append(dirs["PKGDATADIR"])
    for variable, name in (
        ("DEBASHER_WEBUI_BIN_DIR", "BINDIR"),
        ("DEBASHER_WEBUI_LIBEXEC_DIR", "LIBEXECDIR"),
        ("DEBASHER_WEBUI_PYTHON_DIR", "PYTHONDIR"),
    ):
        directory = dirs.get(name)
        if directory and variable not in os.environ and Path(directory).is_dir():
            os.environ[variable] = directory
