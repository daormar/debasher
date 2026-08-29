import os
import re
import subprocess
import tempfile
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from .. import paths
from ..debasher_constants import (
    RESERVED_HEREDOC_SUFFIXES,
    RESERVED_PROCESS_METHOD_SUFFIXES,
)

router = APIRouter(prefix="/api/processes", tags=["processes"])


_PROCESS_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*(::[a-zA-Z_][a-zA-Z_0-9]*)?$")


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
        for suffix in RESERVED_PROCESS_METHOD_SUFFIXES
    ):
        return False

    if any(
        _collides_with_reserved_suffix(name, suffix)
        for suffix in RESERVED_HEREDOC_SUFFIXES
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
_GET_PROC_INFO_SCRIPT = "debasher_get_proc_info"

# Time budget for sourcing a (possibly still-being-edited) preamble.
# These are editor conveniences, so a slow/hanging preamble should just
# yield no result rather than block the request.
_LIBEXEC_TOOL_TIMEOUT_SECS = 10


def _run_preamble_tool(
    script_name: str,
    preamble: str,
    workflow_env_vars: dict[str, str],
    *extra_args: str,
) -> str | None:
    """
    Run a DeBasher libexec tool that sources a preamble file as its
    first argument (debasher_list_proc_names, debasher_get_proc_info)
    and return its stdout, or None if the tool couldn't be found or run.

    These tools source the preamble in a DeBasher-aware Bash process, so
    DEBASHER_MOD_DIR (used to resolve any `load_debasher_module` calls
    the preamble makes) must be forwarded to them — taken from the
    workflow's own envVars (what the workflow will actually run with),
    not the webui server's environment.
    """
    script = paths.find_libexec_tool(script_name)
    if script is None:
        return None

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = workflow_env_vars.get("DEBASHER_MOD_DIR", "")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh") as preamble_file:
        preamble_file.write(preamble)
        preamble_file.flush()

        try:
            result = subprocess.run(
                [str(script), preamble_file.name, *extra_args],
                env=env,
                capture_output=True,
                text=True,
                timeout=_LIBEXEC_TOOL_TIMEOUT_SECS,
            )
        except subprocess.TimeoutExpired:
            return None

    if result.returncode != 0:
        return None

    return result.stdout


def _list_proc_names(preamble: str, workflow_env_vars: dict[str, str]) -> list[str]:
    """
    Run debasher_list_proc_names on `preamble` and return the process
    names it prints (one per line).
    """
    stdout = _run_preamble_tool(_LIST_PROC_NAMES_SCRIPT, preamble, workflow_env_vars)
    if stdout is None:
        return []

    # debasher::list_proc_names (engine/debasher_lib_processes.sh) echoes
    # each process name once per required method it detects (e.g. both
    # "..._explain_cmdline_opts" and "..._explain_opts"), so dedupe here.
    names: list[str] = []
    seen: set[str] = set()
    for name in stdout.splitlines():
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


# --- debasher_get_proc_info ------------------------------------------
#
# Parses the Markdown produced by debasher::_document_process (engine/
# debasher_lib_processes.sh), e.g.:
#
#   ## generate
#
#   ### Description
#   Generates a text file of a given size and random content.
#
#   ### Process Options
#   - `-outf` <string> output file
#   - `-v` verbose flag (command-line)
#
#   ### Process Methods
#   - `generate_document`
#
#   ### Process Variables
#
#   ### Process Implementation
#   ```bash
#   generate ()
#   { ... }
#   ```

_OPTION_LINE_RE = re.compile(r"^-\s*`(?P<label>[^`]+)`\s*(?P<rest>.*)$")
_OPTION_TYPE_RE = re.compile(r"^<(?P<type>\w+)>\s*(?P<rest>.*)$")
_OPTION_FLAGS_RE = re.compile(r"^(?P<desc>.*?)\s*\((?P<flags>[^)]*)\)\s*$")
_CODE_FENCE_START_RE = re.compile(r"^```(?P<lang>\S*)\s*$")

_OPTION_DATA_TYPES: set[str] = {"int", "float", "string"}
_PROCESS_LANGUAGES: set[str] = {"bash", "python", "perl", "r", "groovy"}

OptionDataType = Literal["int", "float", "string"]
ProcessLanguage = Literal["bash", "python", "perl", "r", "groovy"]


class ProcessInfoOption(BaseModel):
    label: str
    dataType: OptionDataType
    description: str
    commandLine: bool


class ProcessInfo(BaseModel):
    description: str
    options: list[ProcessInfoOption]
    language: ProcessLanguage
    code: str


def _split_markdown_sections(markdown: str) -> dict[str, list[str]]:
    """Group lines under their nearest "### <title>" heading."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in markdown.splitlines():
        if line.startswith("### "):
            current = line[len("### "):].strip()
            sections[current] = []
        elif line.startswith("## "):
            current = None
        elif current is not None:
            sections[current].append(line)

    return sections


def _parse_options(lines: list[str]) -> list[ProcessInfoOption]:
    options = []

    for line in lines:
        line_match = _OPTION_LINE_RE.match(line)
        if not line_match:
            continue

        label = line_match.group("label").strip()
        rest = line_match.group("rest")

        data_type: OptionDataType = "string"
        type_match = _OPTION_TYPE_RE.match(rest)
        if type_match:
            candidate = type_match.group("type")
            if candidate in _OPTION_DATA_TYPES:
                data_type = candidate  # type: ignore[assignment]
            rest = type_match.group("rest")

        flags_match = _OPTION_FLAGS_RE.match(rest)
        if flags_match:
            description = flags_match.group("desc").strip()
            flags = [flag.strip() for flag in flags_match.group("flags").split(",")]
        else:
            description = rest.strip()
            flags = []

        options.append(
            ProcessInfoOption(
                label=label,
                dataType=data_type,
                description=description,
                commandLine="command-line" in flags,
            )
        )

    return options


def _parse_code(lines: list[str]) -> tuple[ProcessLanguage, str]:
    language: ProcessLanguage = "bash"
    code_lines: list[str] = []
    in_fence = False

    for line in lines:
        if not in_fence:
            fence_match = _CODE_FENCE_START_RE.match(line)
            if fence_match:
                in_fence = True
                candidate = fence_match.group("lang")
                if candidate in _PROCESS_LANGUAGES:
                    language = candidate  # type: ignore[assignment]
        elif line.strip() == "```":
            break
        else:
            code_lines.append(line)

    return language, "\n".join(code_lines)


def _parse_proc_info_markdown(markdown: str) -> ProcessInfo:
    sections = _split_markdown_sections(markdown)

    description = "\n".join(sections.get("Description", [])).strip()
    options = _parse_options(sections.get("Process Options", []))
    language, code = _parse_code(sections.get("Process Implementation", []))

    return ProcessInfo(
        description=description,
        options=options,
        language=language,
        code=code,
    )


def _get_proc_info(
    preamble: str, name: str, workflow_env_vars: dict[str, str]
) -> ProcessInfo | None:
    """
    Fetch `name`'s description, options, and code from the workflow's
    preamble via libexec/debasher_get_proc_info.
    """
    stdout = _run_preamble_tool(
        _GET_PROC_INFO_SCRIPT, preamble, workflow_env_vars, name
    )
    if stdout is None:
        return None

    info = _parse_proc_info_markdown(stdout)

    # debasher_get_proc_info exits 0 even for an unknown process name,
    # printing only warnings (to stderr) and otherwise-empty sections —
    # treat that as "not found" rather than injecting blank data.
    if not info.description and not info.options and not info.code:
        return None

    return info


class GetProcessInfoRequest(BaseModel):
    preamble: str
    envVars: dict[str, str]
    name: str


class GetProcessInfoResponse(BaseModel):
    info: ProcessInfo | None


@router.post("/get-info", response_model=GetProcessInfoResponse)
def get_process_info(request: GetProcessInfoRequest) -> GetProcessInfoResponse:
    """
    Fetch a previously-defined process's description, options, and code
    from the workflow's preamble (via libexec/debasher_get_proc_info),
    so the editor can pre-fill a new process created from a suggested
    (already-existing) name.
    """
    return GetProcessInfoResponse(
        info=_get_proc_info(request.preamble, request.name, request.envVars)
    )
