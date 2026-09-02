from .debasher_constants import (
    MODULE_DOCUMENT_SUFFIX,
    MODULE_PROGRAM_SUFFIX,
    PROCESS_METHOD_DOCUMENT_SUFFIX,
    PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX,
    PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_EXEC_SUFFIX,
)
from .models import ComputationalSpecs, AdditionalSpecs, Program

INDENT_WIDTH = 4
INDENT = " " * INDENT_WIDTH

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
    lines = [preamble]
    return lines


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


def _define_opts_func_foot():
    lines = []
    lines.append(INDENT + "save_opt_list optlist")
    return lines


def _opt_is_connected_to_proc(option):
    return option.value.startswith("[") and option.value.endswith("]")


def _get_process_plus_opt(option):
    return tuple(option.value[1:-1].split(";"))


def _add_define_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_DEFINE_OPTS_SUFFIX}()", "{"]
    lines.extend(_define_opts_func_header())
    lines.append("")
    if process.options:
        for option in process.options:
            # channel is checked ahead of commandLine: an option can be
            # both a mandatory command-line option (for
            # _identify_cmdline_opts/documentation purposes) and, in
            # _define_opts, actually sourced from a fifo/value descriptor
            # instead — see debasher_cycle_trigger_interactive.sh's
            # worker, whose "-threshold" is exactly that.
            if option.dataType == "None":
                if option.commandLine:
                    lines.append(f'{INDENT}debasher::define_cmdline_flag_if_given "${{cmdline}}" "{option.label}" optlist || return 1')
                else:
                    lines.append(f'{INDENT}debasher::define_flag "{option.label}" optlist || return 1')
            elif option.channel == "value_desc":
                lines.append(f'{INDENT}debasher::define_value_desc_opt "{option.label}" optlist || return 1')
            elif option.channel == "fifo":
                lines.append(f'{INDENT}debasher::define_fifo_opt "{option.label}" "{option.value}" optlist || return 1')
            elif option.commandLine:
                if option.mandatory:
                    lines.append(f'{INDENT}debasher::define_cmdline_opt "${{cmdline}}" "{option.label}" optlist || return 1')
                else:
                    lines.append(f'{INDENT}debasher::define_cmdline_opt_if_given "${{cmdline}}" "{option.label}" optlist || return 1')
            elif _opt_is_connected_to_proc(option):
                conn_proc, conn_opt = _get_process_plus_opt(option)
                lines.append(f'{INDENT}debasher::define_opt_from_proc_out "{option.label}" "{conn_proc}" "{conn_opt}" optlist || return 1')
            else:
                lines.append(f'{INDENT}debasher::define_opt "{option.label}" "{option.value}" optlist || return 1')
    lines.append("")
    lines.extend(_define_opts_func_foot())
    lines.append("}")
    return lines


def _add_opts_handler(process):
    if process.optionsHandler.mode == "standard":
        return _add_define_opts_func(process)
    raise NotImplementedError(
        f'Options handler mode "{process.optionsHandler.mode}" is not implemented yet'
    )


def _add_exec_func(process):
    if process.code:
        lines = [process.code]
        return lines
    else:
        return []


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


def generate_script(program: Program) -> str:
    """
    Generate the contents of the <program.name>.sh file for `program`.

    Implement the actual translation from the Program model
    (program.preamble, program.envVars, program.processes, program.edges,
    program.executionOptions, program.programOptions, ...) into a debasher
    pipeline script.
    """

    lines = []

    # Add preamble
    lines.extend(_add_preamble(program.preamble))
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

        lines.extend(_add_opts_handler(process))
        lines.extend(["", ""])

        lines.extend(_add_exec_func(process))
        lines.extend(["", ""])

    # Add program function
    lines.extend(_add_program_function(program))

    return "\n".join(lines) + "\n"
