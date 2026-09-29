"""
The code of a node of a resident program (see "Script generation and import
of a resident program" in doc/design_doc_webui.md): the Python heredoc of
its process, which script generation assembles from the parts of the code
(the node preamble, the class body and one body for each hook), and the
fixed class of the Supervisor, which has no code of its own. The class is
named after the process, in CamelCase, as the engine requires.

Import does the inverse (decompose_heredoc): it parses the heredoc with
Python's ast module, without running it, and takes the parts back, or says
why the heredoc does not fit them.
"""

import ast
import textwrap
from dataclasses import dataclass

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

# The classes of the runtime library that a node derives from: its node
# kinds.
RUNTIME_CLASSES = ("FBPProcess", "Supervisor", "ProgramLauncher", "DirectoryWatcher")


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


# --- import: the parts of a heredoc ------------------------------------------


@dataclass
class Misfit:
    """Why the heredoc of a node does not fit the parts of a node: the line
    where it does not (None for the whole heredoc), what the web UI finds
    there, and how to change the code so that it fits."""

    line: int | None
    problem: str
    fix: str


@dataclass
class DecomposedHeredoc:
    """What import takes from the heredoc of a node: its node kind, and the
    parts of its code, None for a Supervisor or for a heredoc that does not
    fit them (see misfits)."""

    kind: str | None
    code: NodeCode | None
    misfits: list[Misfit]


_HOOK_PARAMS = {hook: params[1:-1].split(", ") for _, hook, params in NODE_HOOKS}
_HOOK_FIELDS = {hook: field for field, hook, _ in NODE_HOOKS}
_RUNTIME_MODULE = "debasher_runtime_lib"


def _runtime_aliases(tree: ast.Module) -> dict[str, str]:
    """The names under which the heredoc imports the classes of the runtime
    library, as the engine resolves them."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in RUNTIME_CLASSES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def _base_kind(base: ast.expr, aliases: dict[str, str]) -> str | None:
    name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else None
    kind = aliases.get(name, name)
    return kind if kind in RUNTIME_CLASSES else None


def _is_run_call(statement: ast.stmt, class_name: str) -> bool:
    """Whether `statement` is the line that runs the node: <Name>().run()."""
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    call = statement.value
    return (
        not call.args
        and not call.keywords
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
        and isinstance(call.func.value, ast.Call)
        and isinstance(call.func.value.func, ast.Name)
        and call.func.value.func.id == class_name
        and not call.func.value.args
        and not call.func.value.keywords
    )


def _is_run_line(statement: ast.stmt, class_name: str) -> bool:
    """The line that runs the node, bare or under if __name__ == "__main__":,
    which is the same line, since the engine runs the heredoc as the main
    module."""
    if _is_run_call(statement, class_name):
        return True
    return (
        isinstance(statement, ast.If)
        and not statement.orelse
        and len(statement.body) == 1
        and _is_run_call(statement.body[0], class_name)
        and isinstance(statement.test, ast.Compare)
        and isinstance(statement.test.left, ast.Name)
        and statement.test.left.id == "__name__"
        and len(statement.test.ops) == 1
        and isinstance(statement.test.ops[0], ast.Eq)
        and isinstance(statement.test.comparators[0], ast.Constant)
        and statement.test.comparators[0].value == "__main__"
    )


def _is_hook(statement: ast.stmt) -> bool:
    """Whether a statement of the class is a hook: a method with the name of
    a hook, its fixed signature, no annotation, no decorator, and a body on
    lines of its own. Any other method stays in the class body."""
    if not isinstance(statement, ast.FunctionDef) or statement.name not in _HOOK_PARAMS:
        return False
    args = statement.args
    return (
        not statement.decorator_list
        and statement.returns is None
        and not args.posonlyargs
        and not args.vararg
        and not args.kwonlyargs
        and not args.kwarg
        and not args.defaults
        and [arg.arg for arg in args.args] == _HOOK_PARAMS[statement.name]
        and all(arg.annotation is None for arg in args.args)
        and statement.body[0].lineno > statement.lineno
    )


def _start_line(statement: ast.stmt) -> int:
    decorators = getattr(statement, "decorator_list", [])
    return min([statement.lineno, *(decorator.lineno for decorator in decorators)])


def _header_end(lines: list[str], statement: ast.stmt) -> int:
    """The line where the header of a class or a function ends, with its
    colon."""
    line = statement.lineno
    while not lines[line - 1].split("#", 1)[0].rstrip().endswith(":"):
        line += 1
    return line


def _indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def _loaded_names(statement: ast.stmt) -> set[str]:
    """The names that a statement of a class body reads when the class is
    created: not those of the bodies of the functions and classes that it
    defines, which run later."""
    names = set()
    pending = [statement]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        for field, value in ast.iter_fields(node):
            if field == "body" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            children = value if isinstance(value, list) else [value]
            pending.extend(child for child in children if isinstance(child, ast.AST))
    return names


def decompose_heredoc(source: str) -> DecomposedHeredoc:
    """
    The node kind and the parts of the code of a node, from the heredoc of
    its process, parsed with ast and never run:

    - the node kind is the base of the one class that derives from a class
      of the runtime library;
    - the node preamble is the text before the class, comments included,
      less the line "from debasher_runtime_lib import <kind>" when it has
      exactly that form;
    - a method of the class is a hook when it has the name of a hook and its
      fixed signature (see _is_hook), and its body is kept, comments
      included;
    - the class body is the rest of the class, in its order;
    - after the class comes only the line that runs it.

    What script generation could not write again from these parts is a
    misfit, and so is any code of the Supervisor beyond its class with the
    body pass.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return DecomposedHeredoc(
            None, None, [Misfit(exc.lineno, f"the code is not valid Python ({exc.msg})", "fix the syntax error")]
        )

    aliases = _runtime_aliases(tree)
    node_classes = [
        (index, statement, kind)
        for index, statement in enumerate(tree.body)
        if isinstance(statement, ast.ClassDef)
        for kind in [next((k for k in map(lambda b: _base_kind(b, aliases), statement.bases) if k), None)]
        if kind is not None
    ]
    if len(node_classes) != 1:
        return DecomposedHeredoc(
            None,
            None,
            [
                Misfit(
                    None,
                    f"the code defines {len(node_classes)} classes that derive from a class of the runtime library",
                    "define exactly one, the class of the node",
                )
            ],
        )
    index, cls, kind = node_classes[0]
    lines = source.split("\n")
    misfits = []

    if cls.decorator_list:
        misfits.append(
            Misfit(
                cls.decorator_list[0].lineno,
                "the class of the node has a decorator, which the web UI does not keep",
                "remove the decorator, and do what it does in the class body or the node preamble",
            )
        )
    if len(cls.bases) != 1 or cls.keywords:
        misfits.append(
            Misfit(
                cls.lineno,
                "the class of the node has more than one base, or a keyword such as metaclass=, "
                f"where the web UI writes class {cls.name}({kind}):",
                f"derive the class from {kind} alone",
            )
        )
    for statement in tree.body[index + 1 :]:
        if not _is_run_line(statement, cls.name):
            misfits.append(
                Misfit(
                    _start_line(statement),
                    f"there is code after the class other than the line {cls.name}().run(), "
                    "which is all that the web UI writes there",
                    "move it into the node preamble, before the class, or into a method of the class",
                )
            )

    # The preamble: what comes before the class, less the import of its
    # node kind when it has exactly the form that script generation writes.
    class_start = _start_line(cls)
    preamble_lines = lines[: class_start - 1]
    for statement in tree.body[:index]:
        if (
            isinstance(statement, ast.ImportFrom)
            and statement.module == _RUNTIME_MODULE
            and statement.level == 0
            and len(statement.names) == 1
            and statement.names[0].name == kind
            and statement.names[0].asname is None
        ):
            for line in range(statement.lineno, statement.end_lineno + 1):
                preamble_lines[line - 1] = None
            break
    preamble = normalized_part("\n".join(line for line in preamble_lines if line is not None))

    if kind == "Supervisor":
        own_code = [
            statement
            for statement in cls.body
            if not isinstance(statement, ast.Pass)
            and not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
        ]
        for statement in own_code:
            misfits.append(
                Misfit(
                    _start_line(statement),
                    "the Supervisor has code of its own, which the web UI does not edit and has "
                    "nowhere to keep",
                    "remove it: the web UI writes the whole Supervisor, with the body pass",
                )
            )
        if preamble:
            misfits.append(
                Misfit(
                    1,
                    "the Supervisor has code of its own before its class, which the web UI does "
                    "not edit and has nowhere to keep",
                    f"leave only the line from {_RUNTIME_MODULE} import Supervisor before the class",
                )
            )
        return DecomposedHeredoc(kind, None, misfits)

    if cls.body[0].lineno == cls.lineno:
        misfits.append(
            Misfit(
                cls.lineno,
                "the class body is on the line of the class declaration",
                "write the class body on the lines below the declaration",
            )
        )
        return DecomposedHeredoc(kind, None, misfits)

    # The lines of the class, up to its last indented line before the next
    # statement of the module.
    first = _header_end(lines, cls) + 1
    last = _start_line(tree.body[index + 1]) - 1 if index + 1 < len(tree.body) else len(lines)
    while last >= first and (not lines[last - 1].strip() or _indentation(lines[last - 1]) == 0):
        last -= 1

    class_lines = {line: lines[line - 1] for line in range(first, last + 1)}
    hooks: dict[str, str] = {}
    hooks_seen: set[str] = set()
    for position, statement in enumerate(cls.body):
        if _is_hook(statement) and statement.name not in hooks:
            body_start = _header_end(lines, statement) + 1
            body_end = body_start
            following = _start_line(cls.body[position + 1]) if position + 1 < len(cls.body) else last + 1
            for line in range(body_start, following):
                text = lines[line - 1]
                if text.strip() and _indentation(text) <= statement.col_offset:
                    break
                body_end = line
            hooks[statement.name] = normalized_part("\n".join(lines[body_start - 1 : body_end]))
            for line in range(statement.lineno, body_end + 1):
                class_lines.pop(line, None)
            hooks_seen.add(statement.name)
            continue
        used = _loaded_names(statement) & hooks_seen
        if used:
            hook = sorted(used)[0]
            misfits.append(
                Misfit(
                    _start_line(statement),
                    f"this statement of the class body uses {hook}, which it follows: the web UI "
                    "writes the hooks after the rest of the class body, where it would come first",
                    f"move the statement above def {hook}, or refer to the method some other way",
                )
            )

    code = NodeCode(
        preamble=preamble,
        classBody=normalized_part("\n".join(class_lines.values())),
        **{_HOOK_FIELDS[hook]: body for hook, body in hooks.items()},
    )
    return DecomposedHeredoc(kind, code, misfits)
