import os
import re
import subprocess
from pathlib import Path

from . import paths

_DOC_MOD_TOOL_NAME = "debasher_doc_mod"
_GET_PROC_INFO_TOOL_NAME = "debasher_get_proc_info"

# Editor convenience: a script that hangs while loading (a broken/looping
# preamble) should just fail the caller rather than block the request.
_TOOL_TIMEOUT_SECS = 20

DEFAULT_FLAGS = ("--show-shdirs", "--show-opts", "--show-opthnd", "--show-impl", "--show-specs")

_MODULE_TITLE_RE = re.compile(r"^# (?P<name>.+)$")
_SHARED_DIRS_HEADING_RE = re.compile(r"^## Shared Directories$")
_SHARED_DIR_ITEM_RE = re.compile(r"^- `(?P<name>.+)`$")
_PROCESS_HEADING_RE = re.compile(r"^## (?P<name>.+)$")
_ALL_SHARED_DIRS_HEADING_RE = re.compile(r"^## All Shared Directories$")
_ALL_ENVVARS_HEADING_RE = re.compile(r"^## All Module Variables$")
_RESOLVED_VARS_HEADING_RE = re.compile(r"^## Resolved Variables$")
_RESOLVED_VAR_ITEM_RE = re.compile(r"^- `(?P<name>.+)`: `(?P<value>.*)`$")


def run_doc_mod(
    script_path: Path,
    debasher_mod_dir: str = "",
    flags: tuple[str, ...] = DEFAULT_FLAGS,
) -> str:
    """
    Run debasher_doc_mod over `script_path` and return its Markdown
    documentation. `flags` selects which "## Shared Directories"/
    "### <section>" blocks it prints (see engine/debasher_doc_mod's
    usage) — defaults to every section (shared directories, options,
    option handler, implementation, specs); pass a narrower tuple (e.g.
    ("--show-impl",)) when the caller only needs one of them, to skip
    the rest of the work debasher_doc_mod would otherwise do.

    `debasher_mod_dir`, if given, is forwarded as DEBASHER_MOD_DIR so
    the script's own `load_debasher_module` calls (for shared modules
    outside its own directory) can resolve — mirroring how
    routers/execution.py's _debasher_env and routers/processes.py's
    _run_preamble_tool forward it from a program's own envVars.
    """
    tool = paths.find_bin_tool(_DOC_MOD_TOOL_NAME)
    if tool is None:
        raise RuntimeError(f"{_DOC_MOD_TOOL_NAME} tool not found")

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = debasher_mod_dir

    try:
        result = subprocess.run(
            [str(tool), "-m", str(script_path), *flags],
            env=env,
            capture_output=True,
            text=True,
            timeout=_TOOL_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"Timed out running {_DOC_MOD_TOOL_NAME} on {script_path}") from err

    if result.returncode != 0:
        raise RuntimeError(
            f"{_DOC_MOD_TOOL_NAME} failed on {script_path}: {result.stderr.strip()}"
        )

    return result.stdout


def run_get_proc_info(script_path: Path, process_name: str, debasher_mod_dir: str = "") -> str:
    """
    Run debasher_get_proc_info over `script_path` for `process_name` and
    return its Markdown documentation (markdown_parsing.
    parse_proc_info_markdown parses it directly, same as run_doc_mod's
    per-process chunks).

    Unlike run_doc_mod, this never runs `script_path`'s own module
    "_program" function or registers any process via
    add_debasher_process — it calls
    debasher::_show_process_documentation directly for the one process
    name given, so it works on a file that declares no processes of its
    own at all (e.g. just a program's preamble, or a single process's
    own code in isolation) and can't fail just because some other,
    unrelated process in a full script has no implementation (see
    debasher::_add_debasher_regular_process in
    engine/debasher_lib_programs.sh, which add_debasher_process — and so
    only a real "_program" run — would otherwise enforce).
    """
    tool = paths.find_libexec_tool(_GET_PROC_INFO_TOOL_NAME)
    if tool is None:
        raise RuntimeError(f"{_GET_PROC_INFO_TOOL_NAME} tool not found")

    env = os.environ.copy()
    env["DEBASHER_MOD_DIR"] = debasher_mod_dir

    try:
        result = subprocess.run(
            [str(tool), str(script_path), process_name],
            env=env,
            capture_output=True,
            text=True,
            timeout=_TOOL_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"Timed out running {_GET_PROC_INFO_TOOL_NAME} on {script_path}") from err

    if result.returncode != 0:
        raise RuntimeError(
            f"{_GET_PROC_INFO_TOOL_NAME} failed on {script_path}: {result.stderr.strip()}"
        )

    return result.stdout


def _parse_bullet_section(
    markdown: str, heading_re: re.Pattern[str], item_re: re.Pattern[str]
) -> list[re.Match[str]]:
    """
    Collect "- ..." bullet matches under the first line matching
    `heading_re`, stopping at the next "## ..." heading — mirrors how
    parse_module_markdown scopes its own "## Shared Directories"
    section. Used for the two standalone (single-section) doc_mod
    calls below, each run with only its own flag so no other "## ..."
    section precedes it.
    """
    matches: list[re.Match[str]] = []
    in_section = False
    for line in markdown.splitlines():
        if not in_section:
            if heading_re.match(line):
                in_section = True
            continue
        if _PROCESS_HEADING_RE.match(line):
            break
        item_match = item_re.match(line)
        if item_match:
            matches.append(item_match)
    return matches


def parse_all_shared_dirs_markdown(markdown: str) -> list[str]:
    """
    Parse the output of run_doc_mod_all_shared_dirs: every shared
    directory reachable from a program (the module named after -m plus
    every module it loads, transitively — see
    debasher::_show_all_program_shared_dirs), as opposed to
    parse_module_markdown's `shared_dirs`, which is scoped to the named
    module's own declarations only.
    """
    return [
        m.group("name").strip()
        for m in _parse_bullet_section(markdown, _ALL_SHARED_DIRS_HEADING_RE, _SHARED_DIR_ITEM_RE)
    ]


def parse_all_envvars_markdown(markdown: str) -> dict[str, str]:
    """
    Parse the output of debasher_doc_mod --show-all-envvars: every
    variable newly bound while sourcing the module (plus every module it
    loads, transitively) — see debasher::_show_all_program_envvars —
    as opposed to parse_resolved_vars_markdown, which requires already
    knowing the name to look up. Used by script_generation.get_all_envvars
    against a program's own (possibly stubbed, see there) generated
    script, run with only this one flag, so no other "## ..." section
    precedes it — see _parse_bullet_section.
    """
    return {
        m.group("name").strip(): m.group("value")
        for m in _parse_bullet_section(markdown, _ALL_ENVVARS_HEADING_RE, _RESOLVED_VAR_ITEM_RE)
    }


def parse_resolved_vars_markdown(markdown: str) -> dict[str, str]:
    """
    Parse the output of run_doc_mod_resolve_vars. A name that was never
    set after loading the module comes back mapped to "", not omitted.
    """
    return {
        m.group("name").strip(): m.group("value")
        for m in _parse_bullet_section(markdown, _RESOLVED_VARS_HEADING_RE, _RESOLVED_VAR_ITEM_RE)
    }


def run_doc_mod_all_shared_dirs(script_path: Path, debasher_mod_dir: str = "") -> list[str]:
    """
    Return every shared directory reachable from `script_path`'s
    program: its own plus every module it `load_debasher_module`s,
    transitively (--show-all-shdirs). Runs debasher_doc_mod with only
    that one flag, since the caller typically only wants this set on
    its own (e.g. to cross-check a resolved shared-dir name from
    run_doc_mod_resolve_vars).
    """
    markdown = run_doc_mod(script_path, debasher_mod_dir, flags=("--show-all-shdirs",))
    return parse_all_shared_dirs_markdown(markdown)


def run_doc_mod_resolve_vars(
    script_path: Path, names: list[str] | tuple[str, ...], debasher_mod_dir: str = ""
) -> dict[str, str]:
    """
    Resolve each name in `names` to its value once `script_path`'s
    module (and everything it loads) has been sourced, via
    debasher_doc_mod --resolve-var. This is a plain bash
    indirect-expansion read (`${!name}`), not a function call, so it
    carries no more execution risk than any other run_doc_mod call —
    important since `script_path` can be caller-supplied (see
    routers/programs.py's import endpoint).

    Used by program_import.py to resolve a bare-variable argument to
    get_absolute_shdirname (e.g. `` `get_absolute_shdirname
    ${SOME_BASENAME}` ``) to the literal directory name it names,
    without ever executing the process function that contains it.
    """
    if not names:
        return {}
    flags = tuple(flag for name in names for flag in ("--resolve-var", name))
    markdown = run_doc_mod(script_path, debasher_mod_dir, flags=flags)
    return parse_resolved_vars_markdown(markdown)


def parse_module_markdown(
    markdown: str,
) -> tuple[str, str, list[str], list[tuple[str, str]]]:
    """
    Split debasher_doc_mod's output into the module name, its
    description, the names listed under its "## Shared Directories"
    section (present only when debasher_doc_mod was run with
    --show-shdirs — see debasher::_show_module_shared_dirs in
    engine/debasher_lib_modules.sh, which lists one "- `<name>`" bullet
    per directory the module itself defines directly), and a (process
    name, per-process Markdown) pair for each "## <process>" section —
    each of which markdown_parsing.parse_proc_info_markdown can parse on
    its own, exactly as it does for a single-process
    debasher_get_proc_info block.
    """
    name = ""
    description_lines: list[str] = []
    shared_dirs: list[str] = []
    processes: list[tuple[str, str]] = []

    current_process_name: str | None = None
    current_process_lines: list[str] = []
    in_shared_dirs_section = False

    def flush_process() -> None:
        if current_process_name is not None:
            processes.append((current_process_name, "\n".join(current_process_lines)))

    lines = markdown.splitlines()
    start = 0
    if lines:
        title_match = _MODULE_TITLE_RE.match(lines[0])
        if title_match:
            name = title_match.group("name").strip()
            start = 1

    for line in lines[start:]:
        if current_process_name is None and _SHARED_DIRS_HEADING_RE.match(line):
            in_shared_dirs_section = True
            continue
        heading_match = _PROCESS_HEADING_RE.match(line)
        if heading_match:
            in_shared_dirs_section = False
            flush_process()
            current_process_name = heading_match.group("name").strip()
            current_process_lines = []
        elif current_process_name is not None:
            current_process_lines.append(line)
        elif in_shared_dirs_section:
            item_match = _SHARED_DIR_ITEM_RE.match(line)
            if item_match:
                shared_dirs.append(item_match.group("name").strip())
        else:
            description_lines.append(line)
    flush_process()

    description = "\n".join(description_lines).strip()

    return name, description, shared_dirs, processes
