"""
Locate DeBasher's build/install-time executables (the bin/ and libexec/
scripts built by engine/Makefile.am) from the api's plain Python files.

Unlike engine/*.sh, the files under api/ are shipped as-is (dist_*_DATA
in api/Makefile.am) rather than templated at build time, so they can't
have paths like $(bindir)/$(libexecdir) baked into them directly the way
the engine scripts do. The one api file that *is* templated is the
debasher_webui launcher (api/debasher_webui.sh + api/Makefile.am), which
exports DEBASHER_WEBUI_BIN_DIR / DEBASHER_WEBUI_LIBEXEC_DIR for the
installed case. Outside of that (e.g. running `uvicorn` directly, no
`make install` yet), fall back to the repo-relative location the build
leaves both kinds of script in before install: engine/Makefile.am's
suffix rule builds bin_SCRIPTS and libexec_SCRIPTS directly in engine/.
"""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def find_tool(name: str, installed_subdir: str, env_var: str) -> Path | None:
    """
    Locate a DeBasher engine executable named `name`.

    `installed_subdir` is where `make install` puts it relative to the
    install prefix ("bin" or "libexec"); `env_var` is the
    DEBASHER_WEBUI_*_DIR environment variable the installed
    `debasher_webui` launcher sets to override the lookup.
    """
    candidate_dirs = []

    override = os.environ.get(env_var)
    if override:
        candidate_dirs.append(Path(override))

    # Uninstalled dev build: both bin_SCRIPTS and libexec_SCRIPTS land
    # directly in engine/ before any `make install`.
    candidate_dirs.append(_REPO_ROOT / "engine")

    # Installed layout (e.g. this repo's local --prefix=<repo root> build).
    candidate_dirs.append(_REPO_ROOT / installed_subdir)

    for candidate_dir in candidate_dirs:
        candidate = candidate_dir / name
        if candidate.is_file():
            return candidate

    return None


def find_bin_tool(name: str) -> Path | None:
    """Locate a DeBasher tool installed under bin/ (e.g. debasher_exec)."""
    return find_tool(name, "bin", "DEBASHER_WEBUI_BIN_DIR")


def find_libexec_tool(name: str) -> Path | None:
    """Locate a DeBasher tool installed under libexec/ (e.g. debasher_list_proc_names)."""
    return find_tool(name, "libexec", "DEBASHER_WEBUI_LIBEXEC_DIR")
