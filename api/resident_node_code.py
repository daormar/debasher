"""
The code of a node of a resident program (see "Script generation and import
of a resident program" in doc/design_doc_webui.md): the Python heredoc of
its process, which script generation assembles from the parts of the code
(the node preamble, the class body and one body for each hook), and the
fixed class of the Supervisor, which has no code of its own. The class is
named after the process, in CamelCase, as the engine requires.
"""

import textwrap

from .models import NodeCode, ProgramProcess

INDENT = " " * 4

# The hooks of a node, in the order script generation writes them: the field
# of NodeCode that holds the body, the name of the method and its fixed
# parameters.
NODE_HOOKS = (
    ("processData", "process_data", "(self, port_name, packet)"),
    ("captureNodeState", "capture_node_state", "(self)"),
    ("restoreNodeState", "restore_node_state", "(self, node_state)"),
    ("initializeRuntime", "initialize_runtime", "(self)"),
    ("observe", "observe", "(self)"),
)

def node_class_name(process_name: str) -> str:
    """
    The name of the class of a node, after its process, in CamelCase, as the
    engine requires: every part of the process name between dots and
    underscores, with its first letter in upper case ("counter" gives
    "Counter", "org.ns.count_words" gives "OrgNsCountWords").
    """
    parts = process_name.replace(".", "_").split("_")
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def normalized_part(text: str) -> str:
    """
    A part of the code of a node as script generation writes it: without
    the indentation that all its lines share, and without blank lines at
    its start or its end.
    """
    lines = textwrap.dedent(text).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _indented(text: str, indent: str) -> str:
    return "\n".join(indent + line if line.strip() else "" for line in text.splitlines())


def node_heredoc(process: ProgramProcess) -> str:
    """
    The Python heredoc of a node: the import of its node kind, the node
    preamble, the class declaration, the class body, each hook that has a
    body with its fixed signature, and the line that runs the node.
    """
    kind = process.nodeKind
    name = node_class_name(process.name)
    code = process.nodeCode or NodeCode()

    lines = [f"from debasher_runtime_lib import {kind}"]
    preamble = normalized_part(code.preamble)
    if preamble:
        lines += ["", preamble]
    lines += ["", "", f"class {name}({kind}):"]

    blocks = []
    class_body = normalized_part(code.classBody)
    if class_body:
        blocks.append(_indented(class_body, INDENT))
    for field, hook, params in NODE_HOOKS:
        body = normalized_part(getattr(code, field))
        if body:
            blocks.append(f"{INDENT}def {hook}{params}:\n{_indented(body, INDENT * 2)}")
    lines.append("\n\n".join(blocks) if blocks else f"{INDENT}pass")

    lines += ["", "", f"{name}().run()"]
    return "\n".join(lines)


def supervisor_heredoc(process: ProgramProcess) -> str:
    """The Python heredoc of the Supervisor, which has no code of its own."""
    name = node_class_name(process.name)
    return "\n".join(
        [
            "from debasher_runtime_lib import Supervisor",
            "",
            "",
            f"class {name}(Supervisor):",
            f"{INDENT}pass",
            "",
            "",
            f"{name}().run()",
        ]
    )
