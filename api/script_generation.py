from .debasher_constants import (
    MODULE_PROGRAM_SUFFIX,
    PROCESS_METHOD_DOCUMENT_SUFFIX,
    PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX,
    PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_EXEC_SUFFIX,
)
from .models import ComputationalSpecs, AdditionalSpecs, Workflow

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
    if specs.forced:
        parts.append("forced")
    if specs.processdeps:
        parts.append(f"processdeps={specs.processdeps}")
    if specs.alias:
        parts.append(f"alias={specs.alias}")
    if specs.externalAlias:
        parts.append(f"externalAlias={specs.externalAlias}")
    return " ".join(parts)


def _add_preamble(preamble):
    lines = [preamble]
    return lines


def _add_document_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_DOCUMENT_SUFFIX}()", "{"]
    lines.append("}")
    return lines


def _add_explain_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX}()", "{"]
    lines.append("}")
    return lines


def _add_identify_cmdline_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX}()", "{"]
    lines.append("}")
    return lines


def _add_define_opts_func(process):
    lines = [f"{process.name}{PROCESS_METHOD_DEFINE_OPTS_SUFFIX}()", "{"]
    lines.append("}")
    return lines


def _add_opts_handler(process):
    if process.optionsHandler.mode == "standard":
        return _add_define_opts_func(process)


def _add_exec_func(process):
    if process.code:
        lines = [process.code]
        return lines
    else:
        return []

def _add_program_function(workflow):
    lines = [f"{workflow.name}{MODULE_PROGRAM_SUFFIX}()", "{"]
    for process in workflow.processes:
        comp_specs = _computational_specs_str(process.computationalSpecs)
        add_specs = _additional_specs_str(process.additionalSpecs)
        lines.append(
            f'{INDENT}add_debasher_process "{process.name}" "{comp_specs}" "{add_specs}"'
        )
    lines.append("}")
    return lines


def generate_script(workflow: Workflow) -> str:
    """
    Generate the contents of the <workflow.name>.sh file for `workflow`.

    Implement the actual translation from the Workflow model
    (workflow.preamble, workflow.envVars, workflow.processes, workflow.edges,
    workflow.executionOptions, workflow.workflowOptions, ...) into a debasher
    pipeline script.
    """

    lines = []

    # Add preamble
    lines.extend(_add_preamble(workflow.preamble))
    lines.extend(["", ""])

    # Add process functions
    for process in workflow.processes:
        lines.extend(_add_document_func(process))
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
    lines.extend(_add_program_function(workflow))

    return "\n".join(lines) + "\n"
