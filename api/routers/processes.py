import os
import re
import subprocess
import tempfile

from fastapi import APIRouter
from pydantic import BaseModel

from .. import paths

router = APIRouter(prefix="/api/processes", tags=["processes"])


_PROCESS_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*(::[a-zA-Z_][a-zA-Z_0-9]*)?$")

# Mirrors DEBASHER_PROCESS_METHODS in engine/debasher_lib.sh: suffixes
# DeBasher appends to a process name to build its method function names
# (e.g. "<name>_document", "<name>_post"). "" is the exec method's own
# (empty) suffix, kept to preserve the engine's exact behavior, which
# also rejects any name ending in a bare "_".
_RESERVED_METHOD_SUFFIXES = [
    "_document",
    "_reset_outfiles",
    "",
    "_post",
    "_outdir_basename",
    "_explain_cmdline_opts",
    "_explain_opts",
    "_define_opts",
    "_define_opt_deps",
    "_generate_opts_size",
    "_generate_opts",
    "_skip",
    "_conda_envs",
    "_docker_imgs",
]

# Mirrors DEBASHER_HEREDOC_SUFFIXES: language suffixes reserved for
# heredoc process variables (e.g. "<name>_py").
_RESERVED_HEREDOC_SUFFIXES = ["py", "r", "perl", "groovy"]


def _collides_with_reserved_suffix(name: str, suffix: str) -> bool:
    return name == suffix or name.endswith(f"_{suffix}")


def is_valid_process_name(name: str) -> bool:
    """
    Mirrors debasher::_is_valid_processname in
    engine/debasher_lib_programs.sh, so the editor rejects names the
    engine itself would reject.
    """
    if not _PROCESS_NAME_RE.match(name):
        return False

    if any(
        _collides_with_reserved_suffix(name, suffix)
        for suffix in _RESERVED_METHOD_SUFFIXES
    ):
        return False

    if any(
        _collides_with_reserved_suffix(name, suffix)
        for suffix in _RESERVED_HEREDOC_SUFFIXES
    ):
        return False

    return True


class ValidateProcessNameRequest(BaseModel):
    name: str


class ValidateProcessNameResponse(BaseModel):
    valid: bool


@router.post("/validate-name", response_model=ValidateProcessNameResponse)
def validate_process_name(request: ValidateProcessNameRequest) -> ValidateProcessNameResponse:
    """
    Validate a process name against DeBasher's naming rules.
    """
    return ValidateProcessNameResponse(valid=is_valid_process_name(request.name))


_LIST_PROC_NAMES_SCRIPT = "debasher_list_proc_names"

# Time budget for sourcing a (possibly still-being-edited) preamble.
# Suggestions are a convenience, so a slow/hanging preamble should just
# yield no suggestions rather than block the request.
_LIST_PROC_NAMES_TIMEOUT_SECS = 10


def _list_proc_names(preamble: str, workflow_env_vars: dict[str, str]) -> list[str]:
    """
    Run debasher_list_proc_names on `preamble` and return the process
    names it prints (one per line).

    The script sources the preamble in a DeBasher-aware Bash process and
    lists the process-defining functions it declares, so DEBASHER_MOD_DIR
    (used to resolve any `load_debasher_module` calls the preamble makes)
    must be forwarded to it — taken from the workflow's own envVars
    (what the workflow will actually run with), not the webui server's
    environment.
    """
    script = paths.find_libexec_tool(_LIST_PROC_NAMES_SCRIPT)
    if script is None:
        return []

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = workflow_env_vars.get("DEBASHER_MOD_DIR", "")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh") as preamble_file:
        preamble_file.write(preamble)
        preamble_file.flush()

        try:
            result = subprocess.run(
                [str(script), preamble_file.name],
                env=env,
                capture_output=True,
                text=True,
                timeout=_LIST_PROC_NAMES_TIMEOUT_SECS,
            )
        except subprocess.TimeoutExpired:
            return []

    if result.returncode != 0:
        return []

    # debasher::list_proc_names (engine/debasher_lib_processes.sh) echoes
    # each process name once per required method it detects (e.g. both
    # "..._explain_cmdline_opts" and "..._explain_opts"), so dedupe here.
    names: list[str] = []
    seen: set[str] = set()
    for name in result.stdout.splitlines():
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    return names


class SuggestProcessNamesRequest(BaseModel):
    preamble: str
    envVars: dict[str, str]


class SuggestProcessNamesResponse(BaseModel):
    names: list[str]


@router.post("/suggest-names", response_model=SuggestProcessNamesResponse)
def suggest_process_names(request: SuggestProcessNamesRequest) -> SuggestProcessNamesResponse:
    """
    Suggest process names based on the workflow's preamble, by sourcing
    it (via libexec/debasher_list_proc_names) and listing the
    process-defining functions it declares.
    """
    return SuggestProcessNamesResponse(
        names=_list_proc_names(request.preamble, request.envVars)
    )
