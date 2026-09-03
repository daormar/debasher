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

DEFAULT_FLAGS = ("--show-opts", "--show-opthnd", "--show-impl", "--show-specs")

_MODULE_TITLE_RE = re.compile(r"^# (?P<name>.+)$")
_PROCESS_HEADING_RE = re.compile(r"^## (?P<name>.+)$")


def run_doc_mod(
    script_path: Path,
    debasher_mod_dir: str = "",
    flags: tuple[str, ...] = DEFAULT_FLAGS,
) -> str:
    """
    Run debasher_doc_mod over `script_path` and return its Markdown
    documentation. `flags` selects which "### <section>" blocks it
    prints per process (see engine/debasher_doc_mod's usage) — defaults
    to every section (name/description, options, option handler,
    implementation, specs); pass a narrower tuple (e.g. ("--show-impl",))
    when the caller only needs one of them, to skip the rest of the work
    debasher_doc_mod would otherwise do.

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


def parse_module_markdown(markdown: str) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Split debasher_doc_mod's output into the module name, its
    description, and a (process name, per-process Markdown) pair for
    each "## <process>" section — each of which
    markdown_parsing.parse_proc_info_markdown can parse on its own,
    exactly as it does for a single-process debasher_get_proc_info
    block.
    """
    name = ""
    description_lines: list[str] = []
    processes: list[tuple[str, str]] = []

    current_process_name: str | None = None
    current_process_lines: list[str] = []

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
        heading_match = _PROCESS_HEADING_RE.match(line)
        if heading_match:
            flush_process()
            current_process_name = heading_match.group("name").strip()
            current_process_lines = []
        elif current_process_name is not None:
            current_process_lines.append(line)
        else:
            description_lines.append(line)
    flush_process()

    description = "\n".join(description_lines).strip()

    return name, description, processes
