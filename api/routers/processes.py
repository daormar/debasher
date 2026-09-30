import os
import re
import subprocess
import tempfile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import inherited_hooks, paths
from ..debasher_constants import (
    RESERVED_HEREDOC_SUFFIXES,
    RESERVED_PROCESS_METHOD_SUFFIXES,
)
from ..models import NodeCode, NodeKind, OptionsHandler, ProgramOption
from ..program_import import read_preamble_processes
from ..resident_import import preamble_node_kinds, reuse_node
from ..markdown_parsing import (
    ProcessInfo,
    ProcessInfoOption,
    function_header_name,
    parse_proc_info_markdown,
    split_function_blocks,
)

router = APIRouter(prefix="/api/processes", tags=["processes"])


_PROCESS_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)*$")


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
_GET_VERBATIM_FUNC_SOURCE_SCRIPT = "debasher_get_verbatim_func_source"

# Time budget for sourcing a (possibly still-being-edited) preamble.
# These are editor conveniences, so a slow/hanging preamble should just
# yield no result rather than block the request.
_LIBEXEC_TOOL_TIMEOUT_SECS = 10


def _run_preamble_tool(
    script_name: str,
    preamble: str,
    program_env_vars: dict[str, str],
    *extra_args: str,
) -> str | None:
    """
    Run a DeBasher libexec tool that sources a preamble file as its
    first argument (debasher_list_proc_names, debasher_get_proc_info)
    and return its stdout, or None if the tool couldn't be found or run.

    These tools source the preamble in a DeBasher-aware Bash process, so
    DEBASHER_MOD_DIR (used to resolve any `load_debasher_module` calls
    the preamble makes) must be forwarded to them — taken from the
    program's own envVars (what the program will actually run with),
    not the webui server's environment.
    """
    script = paths.find_libexec_tool(script_name)
    if script is None:
        return None

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = program_env_vars.get("DEBASHER_MOD_DIR", "")

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


def _list_proc_names(preamble: str, program_env_vars: dict[str, str]) -> list[str]:
    """
    Run debasher_list_proc_names on `preamble` and return the process
    names it prints (one per line).
    """
    stdout = _run_preamble_tool(_LIST_PROC_NAMES_SCRIPT, preamble, program_env_vars)
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
    Suggest process names based on the program's preamble, by sourcing
    it (via libexec/debasher_list_proc_names) and listing the
    process-defining functions it declares.
    """
    return SuggestProcessNamesResponse(
        names=_list_proc_names(request.preamble, request.envVars)
    )


# --- debasher_get_proc_info ------------------------------------------
#
# Fetches a single process's Markdown documentation from a program's
# preamble; the actual parsing lives in markdown_parsing.py, shared with
# program_import.py.


def _get_proc_info(
    preamble: str, name: str, program_env_vars: dict[str, str]
) -> ProcessInfo | None:
    """
    Fetch `name`'s description, options, and code from the program's
    preamble via libexec/debasher_get_proc_info.
    """
    stdout = _run_preamble_tool(
        _GET_PROC_INFO_SCRIPT, preamble, program_env_vars, name
    )
    if stdout is None:
        return None

    info = parse_proc_info_markdown(stdout)

    # debasher_get_proc_info exits 0 even for an unknown process name,
    # printing only warnings (to stderr) and otherwise-empty sections —
    # treat that as "not found" rather than injecting blank data.
    if not info.description and not info.options and not info.code:
        return None

    return info.copy(update={"code": _verbatim_code(info.code, preamble, program_env_vars)})


def _verbatim_code(code: str, preamble: str, program_env_vars: dict[str, str]) -> str:
    """
    Best-effort upgrade of a process's `declare -f`-derived `code` (see
    _get_proc_info) to its exact original source -- comments and
    indentation intact -- via libexec/debasher_get_verbatim_func_source.

    `code` may bundle more than one function -- debasher::_show_proc_
    implem_bash_func pulls in any same-script helper the exec function
    calls alongside it (see split_function_blocks) -- so each is
    resolved and upgraded independently and rejoined the same way,
    rather than resolving a single function name from `code`'s first
    line and upgrading the whole blob to just that one function's
    source (which would silently drop every other function in it).
    Falls back to a given function's own block unchanged whenever its
    upgrade isn't available: the tool is missing, the block's own
    header line doesn't parse as a function name (shouldn't happen for
    debasher_get_proc_info's own output), or the verbatim source can't
    be recovered (see debasher::_get_verbatim_func_source's own failure
    cases).
    """
    if not code:
        return code

    upgraded_blocks = []
    for block in split_function_blocks(code):
        funcname = function_header_name(block)
        verbatim = (
            _run_preamble_tool(_GET_VERBATIM_FUNC_SOURCE_SCRIPT, preamble, program_env_vars, funcname)
            if funcname
            else None
        )
        upgraded_blocks.append(verbatim.rstrip("\n") if verbatim else block)
    return "\n\n".join(upgraded_blocks)


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
    from the program's preamble (via libexec/debasher_get_proc_info),
    so the editor can pre-fill a new process created from a suggested
    (already-existing) name.
    """
    return GetProcessInfoResponse(
        info=_get_proc_info(request.preamble, request.name, request.envVars)
    )


# --- the nodes of a preamble, for a resident program -----------------
#
# A node can only be told from the processes around it: its heartbeat
# channel is recognized by the Supervisor that reads it. So the processes
# that the preamble defines are read together, by the rules of import (see
# program_import.read_preamble_processes and resident_import.reuse_node),
# where a general program reads a single process with
# debasher_get_proc_info.


class SuggestNodesRequest(BaseModel):
    preamble: str
    envVars: dict[str, str]


class SuggestedNode(BaseModel):
    name: str
    nodeKind: NodeKind


class SuggestNodesResponse(BaseModel):
    nodes: list[SuggestedNode]


@router.post("/suggest-nodes", response_model=SuggestNodesResponse)
def suggest_nodes(request: SuggestNodesRequest) -> SuggestNodesResponse:
    """
    The nodes that the modules of the preamble define, with their node
    kinds, which the dialog that names a new process of a resident program
    suggests: never a Supervisor, nor a process that is not a node.
    Suggestions are a convenience: when the preamble cannot be read, there
    are none.
    """
    names = _list_proc_names(request.preamble, request.envVars)
    try:
        processes, edges = read_preamble_processes(
            request.preamble, names, request.envVars.get("DEBASHER_MOD_DIR", "")
        )
    except RuntimeError:
        return SuggestNodesResponse(nodes=[])
    kinds = preamble_node_kinds(processes, edges)
    return SuggestNodesResponse(
        nodes=[SuggestedNode(name=name, nodeKind=kinds[name]) for name in names if name in kinds]
    )


class NodeInfo(BaseModel):
    """What a node of a module brings to the resident program it is added
    to: its description, node kind, code and options, without the
    Supervisor wiring or its connections."""

    description: str
    nodeKind: NodeKind
    nodeCode: NodeCode
    options: list[ProgramOption]
    optionsHandler: OptionsHandler


class GetNodeInfoRequest(BaseModel):
    preamble: str
    envVars: dict[str, str]
    name: str


class GetNodeInfoResponse(BaseModel):
    info: NodeInfo


@router.post("/get-node-info", response_model=GetNodeInfoResponse)
def get_node_info(request: GetNodeInfoRequest) -> GetNodeInfoResponse:
    """
    A node that the modules of the preamble define, by the rules of import,
    to add it to a resident program. A node that the web UI cannot hold is
    refused with a 400 that says why, line by line, as import does.
    """
    names = _list_proc_names(request.preamble, request.envVars)
    try:
        processes, edges = read_preamble_processes(
            request.preamble, names, request.envVars.get("DEBASHER_MOD_DIR", "")
        )
        node = reuse_node(processes, edges, request.name)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return GetNodeInfoResponse(
        info=NodeInfo(
            description=node.description,
            nodeKind=node.nodeKind,
            nodeCode=node.nodeCode,
            options=node.options,
            optionsHandler=node.optionsHandler,
        )
    )


class InheritedHooksRequest(BaseModel):
    kind: str


class InheritedHooksResponse(BaseModel):
    # {field of NodeCode: source of the method} for each hook that the class
    # of the node kind implements; empty for an FBPProcess.
    hooks: dict[str, str] = {}
    error: str | None = None


@router.post("/inherited-hooks", response_model=InheritedHooksResponse)
def get_inherited_hooks(request: InheritedHooksRequest) -> InheritedHooksResponse:
    """
    The code of the hooks that a node of `kind` inherits from its class of
    the runtime library, for the node code editor, which shows it read only
    next to each hook: a body given for the hook replaces it.
    """
    try:
        return InheritedHooksResponse(hooks=inherited_hooks.inherited_hooks(request.kind))
    except inherited_hooks.InheritedHooksError as exc:
        return InheritedHooksResponse(error=str(exc))
