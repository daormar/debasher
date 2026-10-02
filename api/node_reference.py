"""
The reference of the runtime library of resident programs that the code
prompt of a node carries (see "The code prompt of a node" in
doc/design_doc_webui.md): what the code of a node uses of its class, the
hooks that it redefines, the methods that it calls and the class attributes
that it may set, each with its documentation. It is read from the runtime
library itself, as the inherited hooks are (see inherited_hooks.py), so that
it says what the library that the node imports does: the modules are parsed,
never imported, the installed copy first.

The names are those that the page of the documentation on the classes of
the nodes lists (rtdocs/source/api_resident_nodes.rst), which a test keeps
in step with this module.
"""

import ast
import re

from . import paths

# What the code of a node uses of each class, in the order of the page of
# the documentation: (class, module, hooks, methods, class attributes). A
# hook is a method that the node redefines; a method, one that it calls (or,
# for the classes derived from FBPProcess, may redefine).
_CLASSES = {
    "FBPProcess": (
        "debasher_runtime_fbp.py",
        ("process_data", "capture_node_state", "restore_node_state", "initialize_runtime", "observe"),
        ("send_data", "sleep", "inject", "observe_now", "set_notice", "clear_notice"),
        (
            "OBSERVE_PORT", "OBSERVE_INTERVAL_SECS", "HEARTBEAT_INTERVAL_SECONDS",
            "INPUT_LOG_MAX_BYTES", "OUT_BACKLOG_MAX_BYTES", "OUT_BACKLOG_FAIL_BYTES",
            "GIL_SWITCH_INTERVAL_SECS", "NOTICE_MAX_CHARS",
        ),
    ),
    "DirectoryWatcher": (
        "debasher_runtime_watcher.py",
        (),
        ("request_for", "is_complete"),
        ("WATCH_DIR", "WATCH_DIR_OPTION", "PATTERN", "STABLE_OBSERVATIONS", "REQUESTS_PORT", "FILE_OPTION"),
    ),
    "ProgramLauncher": (
        "debasher_runtime_launcher.py",
        (),
        (),
        (
            "PFILE", "PROCESS", "RUNS_ROOT", "DONE_PORT", "MAX_CONCURRENT_RUNS",
            "BATCH_SCHED", "STATUS_CHECK_INTERVAL_SECS",
        ),
    ),
}

# The node kinds that have a code prompt, and the classes whose reference
# each one carries: its own and the ones it derives from. A Supervisor has
# no code of its own (script generation writes it), so it has none.
_KIND_CLASSES = {
    "FBPProcess": ("FBPProcess",),
    "DirectoryWatcher": ("FBPProcess", "DirectoryWatcher"),
    "ProgramLauncher": ("FBPProcess", "ProgramLauncher"),
}


class NodeReferenceError(Exception):
    """The runtime library could not be found or read."""


def documented_names() -> dict[str, tuple[str, ...]]:
    """{class: every hook, method and class attribute the reference names}."""
    return {cls: hooks + methods + attrs for cls, (_, hooks, methods, attrs) in _CLASSES.items()}


def node_reference(kind: str) -> str:
    """
    The reference, in Markdown, of what the code of a node of `kind` uses of
    the runtime library: for each class, from FBPProcess down to the class of
    the node kind, its documentation, then the signature and documentation
    of each hook and method, then each class attribute with its value and
    its documentation. Empty for a node kind with no code prompt.
    """
    sections = []
    for cls in _KIND_CLASSES.get(kind, ()):
        sections.append(_class_reference(cls, *_CLASSES[cls]))
    return "\n\n".join(sections)


def _class_reference(cls: str, module: str, hooks, methods, attrs) -> str:
    source, node = _read_class(cls, module)
    lines = [f"### {cls}", "", ast.get_docstring(node) or ""]
    functions = {f.name: f for f in node.body if isinstance(f, ast.FunctionDef)}
    for title, names in (("Hooks", hooks), ("Methods", methods)):
        if names:
            lines += ["", f"#### {title} of {cls}"]
            for name in names:
                function = functions.get(name)
                if function is None:
                    raise NodeReferenceError(f"{module} defines no method {cls}.{name}")
                lines += ["", f"`{_signature(source, function)}`", "", ast.get_docstring(function) or ""]
    if attrs:
        documented = _documented_attributes(source, node)
        lines += ["", f"#### Class attributes of {cls}", ""]
        for name in attrs:
            if name not in documented:
                raise NodeReferenceError(f"{module} documents no class attribute {cls}.{name}")
            value, doc = documented[name]
            lines.append(f"- `{name} = {value}`: {doc}")
    return "\n".join(lines)


def _read_class(cls: str, module: str) -> tuple[str, ast.ClassDef]:
    path = paths.find_runtime_module(module)
    if path is None:
        raise NodeReferenceError(f"the runtime library ({module}) was not found")
    try:
        source = path.read_text()
        tree = ast.parse(source)
    except (OSError, SyntaxError) as exc:
        raise NodeReferenceError(f"cannot read {path}: {exc}") from exc
    node = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None)
    if node is None:
        raise NodeReferenceError(f"{path} defines no class {cls}")
    return source, node


def _signature(source: str, function: ast.FunctionDef) -> str:
    """The line that defines `function`, without its colon: def f(self, x)."""
    header = ast.get_source_segment(source, function).split("\n")[0]
    return re.sub(r":\s*$", "", header.strip())


def _documented_attributes(source: str, node: ast.ClassDef) -> dict[str, tuple[str, str]]:
    """
    {name: (value, documentation)} for each class attribute of `node` that
    the comment lines starting with `#:` right above it document, the
    convention of the Sphinx documentation of the library.
    """
    lines = source.split("\n")
    documented = {}
    for statement in node.body:
        if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)):
            continue
        comments = []
        row = statement.lineno - 2
        while row >= 0 and lines[row].strip().startswith("#:"):
            comments.insert(0, lines[row].strip()[2:].strip())
            row -= 1
        if comments:
            value = ast.get_source_segment(source, statement.value)
            documented[statement.targets[0].id] = (value, " ".join(comments))
    return documented
