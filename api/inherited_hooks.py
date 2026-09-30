"""
The hooks that a node inherits from a class of the runtime library (see "The
program model of a resident program" in doc/design_doc_webui.md): a
ProgramLauncher or a DirectoryWatcher implements every hook, and a body that
the user gives replaces the one of its class. The node code editor shows the
inherited code, read only, next to the hook, so that the user sees what a
body would replace. It is read from the runtime library itself, the module
parsed and never imported, the installed copy first, since that is the one a
node imports (see paths.find_runtime_module).
"""

import ast
import textwrap

from . import paths
from .resident_node_code import NODE_HOOKS

# The node kinds whose class implements the hooks, and the module of the
# runtime library that defines each.
_KIND_MODULES = {
    "ProgramLauncher": "debasher_runtime_launcher.py",
    "DirectoryWatcher": "debasher_runtime_watcher.py",
}


class InheritedHooksError(Exception):
    """The runtime library could not be found or read."""


def inherited_hooks(kind: str) -> dict[str, str]:
    """
    {field of NodeCode: source of the method} for each hook that the class
    of `kind` defines, with its signature and its docstring, dedented. Empty
    for a node kind whose class implements no hook (an FBPProcess).
    """
    module = _KIND_MODULES.get(kind)
    if module is None:
        return {}
    path = paths.find_runtime_module(module)
    if path is None:
        raise InheritedHooksError(f"the runtime library ({module}) was not found")
    try:
        source = path.read_text()
        tree = ast.parse(source)
    except (OSError, SyntaxError) as exc:
        raise InheritedHooksError(f"cannot read {path}: {exc}") from exc

    cls = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == kind), None)
    if cls is None:
        raise InheritedHooksError(f"{path} defines no class {kind}")
    methods = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}

    hooks = {}
    for field, hook, _ in NODE_HOOKS:
        method = methods.get(hook)
        if method is not None:
            hooks[field] = textwrap.dedent(ast.get_source_segment(source, method, padded=True))
    return hooks
