import re

from fastapi import APIRouter
from pydantic import BaseModel

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


class SuggestProcessNamesRequest(BaseModel):
    preamble: str


class SuggestProcessNamesResponse(BaseModel):
    names: list[str]


@router.post("/suggest-names", response_model=SuggestProcessNamesResponse)
def suggest_process_names(request: SuggestProcessNamesRequest) -> SuggestProcessNamesResponse:
    """
    Suggest process names based on the workflow's preamble.

    Stub: always returns an empty list.

    TODO: replace with real logic that inspects `request.preamble`
    (e.g. functions/commands it defines) to suggest names.
    """
    return SuggestProcessNamesResponse(names=[])
