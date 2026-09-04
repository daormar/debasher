import tempfile
from pathlib import Path

from .debasher_constants import (
    MODULE_DOCUMENT_SUFFIX,
    MODULE_PROGRAM_SUFFIX,
    PROCESS_METHOD_DOCUMENT_SUFFIX,
    PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX,
    PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
    PROCESS_METHOD_EXEC_SUFFIX,
)
from .doc_mod import run_get_proc_info
from .markdown_parsing import parse_proc_info_markdown
from .models import ComputationalSpecs, AdditionalSpecs, Program

INDENT_WIDTH = 4
INDENT = " " * INDENT_WIDTH


def _indent_block(text: str, indent: str) -> str:
    """Prefixes every non-blank line of `text` with `indent`, preserving its own relative indentation."""
    return "\n".join(indent + line if line else line for line in text.splitlines())
SCRIPT_HEADER = "# AUTOMATICALLY GENERATED DEBASHER SCRIPT"

def _computational_specs_str(specs: ComputationalSpecs) -> str:
    parts = []
    if specs.cpus is not None:
        parts.append(f"cpus={specs.cpus:g}")
    if specs.mem is not None:
        parts.append(f"mem={specs.mem:g}")
    if specs.time is not None:
        parts.append(f"time={specs.time}")
    return " ".join(parts)


def _additional_specs_str(specs: AdditionalSpecs) -> str:
    parts = []
    if specs.force:
        # The engine only recognizes "force=yes" (see
        # debasher::_extract_force_from_process_spec /
        # _define_forced_rerun_processes in
        # engine/debasher_lib_sched_rerun.sh, which checks
        # `[ ${process_forced} = "yes" ]`) — a bare "forced" token would
        # never match.
        parts.append("force=yes")
    if specs.processdeps:
        parts.append(f"processdeps={specs.processdeps}")
    if specs.alias:
        parts.append(f"alias={specs.alias}")
    if specs.externalAlias:
        # The engine's own attribute key is "ext_alias" (see
        # debasher::_extract_ext_alias_from_process_spec /
        # add_debasher_process in engine/debasher_lib_programs.sh) —
        # "externalAlias" is only this app's field name for it.
        parts.append(f"ext_alias={specs.externalAlias}")
    return " ".join(parts)


def _add_preamble(preamble):
    if preamble:
        return [preamble]
    else:
        return []


def _add_document_module_func(name, description):
    lines = [f"{name}{MODULE_DOCUMENT_SUFFIX}()", "{"]
    if description:
        lines.append(f'{INDENT}debasher::document_module "{description}"')
    else:
        lines.append(INDENT + ":")
    lines.append("}")
    return lines


def _add_document_proc_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_DOCUMENT_SUFFIX}()", "{"]
    if process.description:
        lines.append(f'{INDENT}debasher::document_process "{process.description}"')
    else:
        lines.append(INDENT + ":")
    lines.append("}")
    return lines


def _add_explain_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX}()", "{"]
    if process.options:
        for option in process.options:
            if option.dataType == "None":
                lines.append(f'{INDENT}debasher::explain_flag "{option.label}" "{option.description}"')
            else:
                # By convention throughout data/programs, e.g. "<int>",
                # "<string>" — purely the value's type; how it's
                # delivered (option.channel) isn't encoded here, see
                # markdown_parsing.py's _OPTION_TYPE_RE.
                lines.append(f'{INDENT}debasher::explain_opt "{option.label}" "<{option.dataType}>" "{option.description}"')
    else:
        lines.append(INDENT + ":")
    lines.append("}")
    return lines


def _add_identify_cmdline_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX}()", "{"]
    if process.options:
        cmdline_option_found = False
        for option in process.options:
            if option.commandLine:
                if option.mandatory:
                    lines.append(f'{INDENT}debasher::opt_is_cmdline "{option.label}"')
                else:
                    lines.append(f'{INDENT}debasher::opt_is_non_mandatory_cmdline "{option.label}"')
                cmdline_option_found = True
        if not cmdline_option_found:
            lines.append(INDENT + ":")
    else:
        lines.append(INDENT + ":")
    lines.append("}")
    return lines


def _define_opts_func_header():
    lines = []
    lines.append(INDENT + "# Initialize variables")
    lines.append(INDENT + "local cmdline=$1")
    lines.append(INDENT + "local process_spec=$2")
    lines.append(INDENT + "local process_name=$3")
    lines.append(INDENT + "local process_outdir=$4")
    lines.append(INDENT + "local optlist=\"\"")
    return lines


def _generate_opts_func_header():
    # Same as _define_opts_func_header, plus the per-task index the
    # engine calls _generate_opts with (see debasher_lib_processes.sh).
    lines = _define_opts_func_header()
    lines.insert(-1, INDENT + "local task_idx=$5")
    return lines


def _define_opts_func_foot():
    lines = []
    lines.append(INDENT + "save_opt_list optlist")
    return lines


def _opt_is_connected_to_proc(option):
    return option.value.startswith("[") and option.value.endswith("]")


def _get_process_plus_opt(option):
    return tuple(option.value[1:-1].split(";"))


# Modes whose _define_opts/_generate_opts is guaranteed to produce one
# save_opt_list call per task, numbered 0..N-1 — generator via the
# engine calling _generate_opts once per task_idx, array via a loop that
# calls save_opt_list once per idx (see debasher_array_example.sh). Only
# a source in one of these modes can be trusted to actually have a task
# N to connect to; a standard source has only task 0, and a manual
# source's task shape is unknown, so both default to task 0 instead (see
# _opt_is_connected_to_proc below).
_TASK_INDEXED_MODES = {"generator", "array"}


def _task_idx_var(mode):
    return "task_idx" if mode == "generator" else "idx"


def _option_definition_line(process, option, process_modes):
    # channel is checked ahead of commandLine: an option can be both a
    # mandatory command-line option (for _identify_cmdline_opts/
    # documentation purposes) and, in _define_opts, actually sourced
    # from a fifo/value descriptor instead — see
    # debasher_cycle_trigger_interactive.sh's worker, whose "-threshold"
    # is exactly that.
    if option.dataType == "None":
        if option.commandLine:
            return f'debasher::define_cmdline_flag_if_given "${{cmdline}}" "{option.label}" optlist || return 1'
        return f'debasher::define_flag "{option.label}" optlist || return 1'
    if option.channel == "value_desc":
        return f'debasher::define_value_desc_opt "{option.label}" optlist || return 1'
    if option.channel == "fifo":
        return f'debasher::define_fifo_opt "{option.label}" "{option.value}" optlist || return 1'
    if option.commandLine:
        if option.mandatory:
            return f'debasher::define_cmdline_opt "${{cmdline}}" "{option.label}" optlist || return 1'
        return f'debasher::define_cmdline_opt_if_given "${{cmdline}}" "{option.label}" optlist || return 1'
    if _opt_is_connected_to_proc(option):
        conn_proc, conn_opt = _get_process_plus_opt(option)
        if process.optionsHandler.mode in _TASK_INDEXED_MODES and process_modes.get(conn_proc) in _TASK_INDEXED_MODES:
            idx_var = _task_idx_var(process.optionsHandler.mode)
            return f'debasher::define_opt_from_proc_task_out "{option.label}" "{conn_proc}" "${{{idx_var}}}" "{conn_opt}" optlist || return 1'
        return f'debasher::define_opt_from_proc_out "{option.label}" "{conn_proc}" "{conn_opt}" optlist || return 1'
    return f'debasher::define_opt "{option.label}" "{option.value}" optlist || return 1'


def _add_opts_definition_func(process, suffix, header_lines, process_modes):
    lines = [f"{process.name}{suffix}()", "{"]
    lines.extend(header_lines)
    lines.append("")
    if process.options:
        for option in process.options:
            lines.append(INDENT + _option_definition_line(process, option, process_modes))
    lines.append("")
    lines.extend(_define_opts_func_foot())
    lines.append("}")
    return lines


def _add_array_opts_func(process, process_modes):
    # array mode: the engine's per-process task numbering (see
    # debasher::_save_opt_list_loop) already treats "call save_opt_list
    # N times inside one _define_opts" as N tasks — the same mechanism
    # debasher_array_example.sh uses by hand — so, unlike generator
    # mode, no separate _generate_opts_size is needed. The array itself
    # is built by the user's own arrayCode, embedded verbatim, under the
    # fixed name "array"; the fixed loop variable "idx" (mirroring
    # generator mode's "task_idx") is then available to option values as
    # "${array[$idx]}" or "${idx}" and to connections (see
    # _option_definition_line/_task_idx_var).
    #
    # Unlike "standard"/"generator", the header's own "local optlist="
    # is dropped: every option is (re)defined inside the loop regardless
    # of whether its value actually depends on idx (uniform — no
    # idx-independent option gets hoisted out as a one-time "shared
    # prefix"), so "optlist" itself is simply declared fresh, empty, at
    # the top of each iteration instead of copied from an outer one.
    lines = [f"{process.name}{PROCESS_METHOD_DEFINE_OPTS_SUFFIX}()", "{"]
    lines.extend(_define_opts_func_header()[:-1])
    lines.append("")
    if process.optionsHandler.arrayCode:
        lines.append(_indent_block(process.optionsHandler.arrayCode, INDENT))
        lines.append("")
    lines.append(f'{INDENT}for idx in "${{!array[@]}}"; do')
    lines.append(f'{INDENT * 2}local optlist=""')
    if process.options:
        for option in process.options:
            lines.append(INDENT * 2 + _option_definition_line(process, option, process_modes))
    lines.append(f'{INDENT * 2}save_opt_list optlist')
    lines.append(f'{INDENT}done')
    lines.append("}")
    return lines


def _add_generate_opts_size_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX}()", "{"]
    lines.append(f'{INDENT}echo "{process.optionsHandler.generatorSize or ""}"')
    lines.append("}")
    return lines


def _add_opts_handler(process, process_modes):
    handler = process.optionsHandler
    if handler.mode == "standard":
        return _add_opts_definition_func(
            process, PROCESS_METHOD_DEFINE_OPTS_SUFFIX, _define_opts_func_header(), process_modes
        )
    if handler.mode == "generator":
        lines = _add_generate_opts_size_func(process)
        lines.extend(["", ""])
        lines.extend(
            _add_opts_definition_func(
                process, PROCESS_METHOD_GENERATE_OPTS_SUFFIX, _generate_opts_func_header(), process_modes
            )
        )
        return lines
    if handler.mode == "array":
        return _add_array_opts_func(process, process_modes)
    if handler.mode == "manual":
        manual_code = handler.manualCode
        return [manual_code] if manual_code else []
    raise NotImplementedError(
        f'Options handler mode "{handler.mode}" is not implemented yet'
    )


# A process implemented in anything but bash isn't a bash function at
# all: the engine recognizes it via a variable named
# "<processname>_<suffix>" (debasher_lib.sh's DEBASHER_PROCESS_VARNAMES/
# DEBASHER_HEREDOC_LANGUAGES) holding the raw interpreter source, and
# auto-generates the actual "<processname>()" wrapper around it
# (debasher::_create_process_func_heredoc) — see
# debasher::_is_heredoc_process in engine/debasher_lib_programs.sh.
_HEREDOC_LANGUAGE_SUFFIXES = {
    "python": "py",
    "r": "r",
    "perl": "perl",
    "groovy": "groovy",
}


def _code_definition_lines(process_name: str, language: str, code: str) -> list[str]:
    if language == "bash":
        return [code]
    suffix = _HEREDOC_LANGUAGE_SUFFIXES[language]
    return [f"{process_name}_{suffix}=$(cat <<'EOF'", code, "EOF", ")"]


def _add_exec_func(process):
    # An alias/external alias supplies the implementation itself (the
    # engine builds the "<processname>()" wrapper from the "alias"/
    # "ext_alias" additional-spec attribute — see
    # debasher::_add_debasher_alias_process/_add_debasher_ext_alias_process
    # in engine/debasher_lib_programs.sh), so process.code, if any, is
    # never actually used and embedding it would just be dead code.
    if process.additionalSpecs.alias or process.additionalSpecs.externalAlias:
        return []
    if not process.code:
        return []
    return _code_definition_lines(process.name, process.language, process.code)


def _add_program_function(program):
    lines = [f"{program.name}{MODULE_PROGRAM_SUFFIX}()", "{"]
    for process in program.processes:
        comp_specs = _computational_specs_str(process.computationalSpecs)
        add_specs = _additional_specs_str(process.additionalSpecs)
        lines.append(
            f'{INDENT}add_debasher_process "{process.name}" "{comp_specs}" "{add_specs}"'
        )
    lines.append("}")
    return lines


def _build_script(program: Program, skip_exec_for: frozenset[str] = frozenset()) -> str:
    """
    Build the <program.name>.sh contents, omitting the exec function
    (_add_exec_func) for any process whose name is in `skip_exec_for` —
    used by generate_script to leave out processes _find_redundant_exec_funcs
    determined are already provided by a loaded module.
    """
    lines = [SCRIPT_HEADER, "", ""]

    process_modes = {p.name: p.optionsHandler.mode for p in program.processes}

    # Add preamble
    preamble_lines = _add_preamble(program.preamble)
    if preamble_lines:
        lines.extend(preamble_lines)
        lines.extend(["", ""])

    # Add program description
    lines.extend(_add_document_module_func(program.name, program.description))
    lines.extend(["", ""])

    # Add process functions
    for process in program.processes:
        lines.extend(_add_document_proc_func(process))
        lines.extend(["", ""])

        lines.extend(_add_explain_opts_func(process))
        lines.extend(["", ""])

        lines.extend(_add_identify_cmdline_opts_func(process))
        lines.extend(["", ""])

        lines.extend(_add_opts_handler(process, process_modes))
        lines.extend(["", ""])

        if process.name not in skip_exec_for:
            exec_func_lines = _add_exec_func(process)
            if exec_func_lines:
                lines.extend(exec_func_lines)
                lines.extend(["", ""])

    # Add program function
    lines.extend(_add_program_function(program))

    return "\n".join(lines) + "\n"


def _proc_info_code(script_path: Path, process_name: str, debasher_mod_dir: str) -> str:
    markdown = run_get_proc_info(script_path, process_name, debasher_mod_dir)
    return parse_proc_info_markdown(markdown).code


def _module_provided_code(process_name: str, preamble: str, debasher_mod_dir: str) -> str:
    """
    What debasher_get_proc_info reports for `process_name` when only
    `preamble` (and whatever it load_debasher_module's in) is sourced —
    i.e. the implementation this process would get "for free" without
    embedding process.code in the generated script at all. Empty if
    nothing sourced from the preamble defines it.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        preamble_path = Path(tmp_dir) / "preamble.sh"
        preamble_path.write_text(preamble)
        return _proc_info_code(preamble_path, process_name, debasher_mod_dir)


def _own_code_canonicalized(process_name: str, language: str, code: str, debasher_mod_dir: str) -> str:
    """
    debasher_get_proc_info's own `declare -f` canonicalization of `code`
    alone (a standalone file containing just this one process's own
    implementation, nothing else) — so it's directly comparable to
    _module_provided_code's output despite process.code being free-typed
    rather than already in debasher_doc_mod/debasher_get_proc_info's own
    printed format. Wrapped the same way _add_exec_func embeds it (a
    heredoc variable assignment for a non-bash language), so
    debasher_get_proc_info recognizes it the same way it would in the
    generated script.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        code_path = Path(tmp_dir) / "code.sh"
        code_path.write_text("\n".join(_code_definition_lines(process_name, language, code)) + "\n")
        return _proc_info_code(code_path, process_name, debasher_mod_dir)


def _find_redundant_exec_funcs(program: Program) -> frozenset[str]:
    """
    Returns the names of processes whose exec function shouldn't be
    embedded in the generated script because it's already provided,
    identically, by a module the preamble loads (via
    load_debasher_module) — so embedding process.code again would just
    be a duplicate definition of the exact same bash function.

    Checked per process via debasher_get_proc_info, which — unlike
    debasher_doc_mod — never runs the script's "_program" function or
    registers anything through add_debasher_process, so it can't fail
    just because some unrelated process has no implementation of its
    own; it only ever looks at the one process name it's asked about
    (see run_get_proc_info). A process is redundant when
    debasher_get_proc_info reports the exact same non-empty
    implementation both for the bare preamble and for process.code in
    isolation. Each check is independent, and one failing (tool missing,
    timeout, code that doesn't source cleanly) just leaves that process
    embedded as it always was rather than affecting any other process.
    """
    debasher_mod_dir = program.envVars.get("DEBASHER_MOD_DIR", "")
    redundant: set[str] = set()

    for process in program.processes:
        # An alias/external alias process embeds no code of its own (see
        # _add_exec_func), so there's nothing here to compare.
        if process.additionalSpecs.alias or process.additionalSpecs.externalAlias:
            continue
        if not process.code:
            continue
        try:
            module_code = _module_provided_code(process.name, program.preamble, debasher_mod_dir)
            if not module_code:
                continue
            own_code = _own_code_canonicalized(process.name, process.language, process.code, debasher_mod_dir)
        except RuntimeError:
            continue
        if module_code == own_code:
            redundant.add(process.name)

    return frozenset(redundant)


def generate_script(program: Program) -> str:
    """
    Generate the contents of the <program.name>.sh file for `program`.

    Implement the actual translation from the Program model
    (program.preamble, program.envVars, program.processes, program.edges,
    program.executionOptions, program.programOptions, ...) into a debasher
    pipeline script.

    A process's exec function is left out when it's redundant with one
    already provided by a module the preamble loads — see
    _find_redundant_exec_funcs.
    """
    return _build_script(program, skip_exec_for=_find_redundant_exec_funcs(program))
