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
import io
import textwrap
import tokenize
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


# What the engine reads of the source of a node is in debasher_node_source.py
# of the runtime library. The API keeps a copy of the part it needs, since it
# parses the runtime library and never imports it, and a test keeps the two in
# step. The rules of this copy are stricter where the web UI has to write the
# code back: the line that starts the node is alone, after the class.


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

    found = _find_node_class(tree)
    if isinstance(found, Misfit):
        return DecomposedHeredoc(None, None, [found])
    index, cls, kind = found
    lines = source.split("\n")
    misfits = _check_class_declaration(tree, index, cls, kind)
    preamble = _get_preamble(lines, tree, index, cls, kind)

    if kind == "Supervisor":
        return DecomposedHeredoc(kind, None, misfits + _check_supervisor_code(cls, preamble))

    if cls.body[0].lineno == cls.lineno:
        misfits.append(
            Misfit(
                cls.lineno,
                "the class body is on the line of the class declaration",
                "write the class body on the lines below the declaration",
            )
        )
        return DecomposedHeredoc(kind, None, misfits)

    layout = _SourceLayout(source)
    class_body, hooks, body_misfits = _split_class(lines, layout, tree, index, cls)
    code = NodeCode(
        preamble=preamble,
        classBody=class_body,
        **{_HOOK_FIELDS[hook]: body for hook, body in hooks.items()},
    )
    return DecomposedHeredoc(kind, code, misfits + body_misfits)


def _find_node_class(tree: ast.Module):
    """(index in the module, class, node kind) of the one class that derives
    from a class of the runtime library, or the Misfit of a module with
    none or several."""
    aliases = _runtime_aliases(tree)
    node_classes = [
        (index, statement, kind)
        for index, statement in enumerate(tree.body)
        if isinstance(statement, ast.ClassDef)
        for kind in [next((k for k in map(lambda b: _base_kind(b, aliases), statement.bases) if k), None)]
        if kind is not None
    ]
    if len(node_classes) != 1:
        return Misfit(
            None,
            f"the code defines {len(node_classes)} classes that derive from a class of the runtime library",
            "define exactly one, the class of the node",
        )
    return node_classes[0]


def _check_class_declaration(tree: ast.Module, index: int, cls: ast.ClassDef, kind: str) -> list[Misfit]:
    """The misfits of the declaration of the class and of what follows it."""
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
                    "move it into the node preamble, before the class, or into a method of the class; "
                    f"a node is started only by the line {cls.name}().run()",
                )
            )
    return misfits


def _get_preamble(lines: list[str], tree: ast.Module, index: int, cls: ast.ClassDef, kind: str) -> str:
    """What comes before the class, less the import of its node kind when it
    has exactly the form that script generation writes."""
    preamble_lines = lines[: _start_line(cls) - 1]
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
    return normalized_part("\n".join(line for line in preamble_lines if line is not None))


def _check_supervisor_code(cls: ast.ClassDef, preamble: str) -> list[Misfit]:
    """The misfits of a Supervisor with code of its own, in its class or
    before it."""
    own_code = [
        statement
        for statement in cls.body
        if not isinstance(statement, ast.Pass)
        and not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
    ]
    misfits = [
        Misfit(
            _start_line(statement),
            "the Supervisor has code of its own, which the web UI does not edit and has nowhere to keep",
            "remove it: the web UI writes the whole Supervisor, with the body pass",
        )
        for statement in own_code
    ]
    if preamble:
        misfits.append(
            Misfit(
                1,
                "the Supervisor has code of its own before its class, which the web UI does not edit "
                "and has nowhere to keep",
                f"leave only the line from {_RUNTIME_MODULE} import Supervisor before the class",
            )
        )
    return misfits


class _SourceLayout:
    """What the tokens of a source say of its lines, which ast does not keep:
    where a header ends, which lines hold only a comment, and where the
    strings of several lines are."""

    def __init__(self, source: str):
        self.colons = []
        self.comments = {}
        self.multiline_strings = []
        code_lines = set()
        trivial = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER)
        fstring_start = getattr(tokenize, "FSTRING_START", None)
        fstring_end = getattr(tokenize, "FSTRING_END", None)
        open_fstrings = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            (start_line, start_col), (end_line, _) = token.start, token.end
            if token.type == tokenize.OP and token.string == ":":
                self.colons.append(token.start)
            if token.type == tokenize.COMMENT:
                self.comments[start_line] = start_col
            if token.type not in trivial:
                code_lines.update(range(start_line, end_line + 1))
            if token.type == tokenize.STRING and end_line > start_line:
                self.multiline_strings.append((start_line, end_line))
            # Since Python 3.12 an f-string comes as several tokens
            if token.type == fstring_start:
                open_fstrings.append(start_line)
            if token.type == fstring_end and open_fstrings:
                first = open_fstrings.pop()
                if end_line > first:
                    self.multiline_strings.append((first, end_line))
        # A line whose only token is a comment: never part of a string
        self.comment_lines = {line: col for line, col in self.comments.items() if line not in code_lines}

    def get_header_end(self, statement: ast.stmt) -> int:
        """The line of the colon that ends the header of a class or a function
        whose body starts on a line of its own."""
        # From the first line of the first statement, its decorators
        # included, whose colons are not those of the header
        body_start = (_start_line(statement.body[0]), 0)
        return max(line for line, col in self.colons if (statement.lineno, 0) <= (line, col) < body_start)

    def get_block_end(self, statement: ast.stmt, limit: int, lines: list[str], blanks: bool) -> int:
        """The last line of a class or a function: that of its last statement,
        and then the lines below it, up to `limit`, that hold only a comment
        indented more than its header, and, with `blanks`, the blank lines
        among and after them."""
        end = statement.end_lineno
        for line in range(end + 1, limit + 1):
            col = self.comment_lines.get(line)
            if col is not None and col > statement.col_offset:
                end = line
            elif col is not None:
                break
            # Past the last statement, so never inside a string
            elif not lines[line - 1].strip():
                if blanks:
                    end = line
            else:
                break
        return end

    def find_changed_string(self, lines: list[str], part_lines: list[int], indent: str) -> int | None:
        """
        The first line of a string of several lines, among the lines
        `part_lines` of a part, that would change when the part is written
        back with `indent`: because the indentation that the part loses to
        normalized_part and the one it gets back differ, or because a line of
        the string holds only spaces, which both empty.
        """
        in_part = set(part_lines)
        strings = [(start, end) for start, end in self.multiline_strings if start in in_part and end in in_part]
        if not strings:
            return None
        text = "\n".join(lines[line - 1] for line in part_lines)
        removed = next(
            (len(a) - len(b) for a, b in zip(text.splitlines(), textwrap.dedent(text).splitlines()) if a.strip()),
            len(indent),
        )
        for start, end in strings:
            spaces_only = any(lines[line - 1] and not lines[line - 1].strip() for line in range(start + 1, end + 1))
            if removed != len(indent) or spaces_only:
                return start
        return None


def _split_class(lines, layout, tree, index, cls):
    """The class body and the body of each hook, normalized, and the misfits of
    the class: a statement that uses a hook it follows, and a part with a
    string that writing it back would change."""
    first = layout.get_header_end(cls) + 1
    limit = _start_line(tree.body[index + 1]) - 1 if index + 1 < len(tree.body) else len(lines)
    last = layout.get_block_end(cls, limit, lines, blanks=False)
    misfits = []

    class_lines = {line: lines[line - 1] for line in range(first, last + 1)}
    hooks: dict[str, str] = {}
    hooks_seen: set[str] = set()
    for position, statement in enumerate(cls.body):
        if _is_hook(statement) and statement.name not in hooks:
            following = _start_line(cls.body[position + 1]) - 1 if position + 1 < len(cls.body) else last
            body_start = layout.get_header_end(statement) + 1
            body_end = layout.get_block_end(statement, following, lines, blanks=True)
            hooks[statement.name] = normalized_part("\n".join(lines[body_start - 1 : body_end]))
            misfits += _check_written_back(lines, layout, list(range(body_start, body_end + 1)), INDENT * 2)
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
    # As one text, since normalized_part takes the indentation of the whole
    # class body
    misfits += _check_written_back(lines, layout, sorted(class_lines), INDENT)
    misfits.sort(key=lambda misfit: misfit.line or 0)
    return normalized_part("\n".join(class_lines.values())), hooks, misfits


def _check_written_back(lines, layout, part_lines, indent) -> list[Misfit]:
    """The misfit of the lines `part_lines` of a part that script generation,
    which writes it back with `indent`, would not give again."""
    line = layout.find_changed_string(lines, part_lines, indent)
    if line is None:
        return []
    return [
        Misfit(
            line,
            "the web UI would not write this part of the code back as it is: it writes each part "
            "with 4 spaces per level, which would change this string of several lines (a line of "
            "it is less indented than the code, the code is not indented with 4 spaces per level, "
            "or a line of it holds only spaces)",
            "write the line breaks of the string as \\n, or indent the code with 4 spaces per level "
            "and the lines of the string with it, and take textwrap.dedent of the string",
        )
    ]
