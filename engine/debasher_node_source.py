"""
DeBasher package
Copyright 2019-2026 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import ast
import builtins
import sys

####################
# Source of a node #
####################
#
# The rules by which the engine reads the Python heredoc of a process of a
# resident program, parsed with ast and never run: the role of the process,
# the name of the class of its node and the line that starts it. The engine
# runs this module from debasher_lib_resident.sh when it loads a program, and
# the node harness (debasher_runtime_testing) imports it. The API of the web
# UI keeps a copy of what it needs, since it never imports the engine, and a
# test keeps the two in step.

# The classes of the runtime library, with the role of a process whose class
# derives from each
BASE_ROLES = {
    "Supervisor": "supervisor",
    "FBPProcess": "fbpprocess",
    "ProgramLauncher": "fbpprocess",
    "DirectoryWatcher": "fbpprocess",
}
RUNTIME_CLASSES = tuple(BASE_ROLES)

# Nodes whose names live in a scope of their own, not in the module's
_SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def get_node_class_name(processname):
    """The name of the class of the node of `processname`, in CamelCase:
    every part between dots and underscores, with its first letter in upper
    case ("org.ns.count_words" gives "OrgNsCountWords")."""
    parts = processname.replace(".", "_").split("_")
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def get_runtime_aliases(tree):
    """{local name: class of the runtime library} for the classes that the
    module imports, following `import ... as`."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in RUNTIME_CLASSES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def get_base_name(base):
    """The name of the base `base` of a class (a Name or an Attribute), or
    None for another expression."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def find_node_classes(tree):
    """The classes at the top level of the module that derive from a class of
    the runtime library."""
    aliases = get_runtime_aliases(tree)
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = get_base_name(base)
            if name is not None and aliases.get(name, name) in RUNTIME_CLASSES:
                classes.append(node)
                break
    return classes


def classify_role(source):
    """
    "supervisor", "fbpprocess" or "unknown": the role of the process whose
    Python heredoc is `source`, from the base of its classes. Raises
    SyntaxError when `source` is not valid Python.
    """
    tree = ast.parse(source)
    aliases = get_runtime_aliases(tree)
    found_role = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = get_base_name(base)
            if name is None:
                continue
            role = BASE_ROLES.get(aliases.get(name, name))
            # A Supervisor wins: a module with a Supervisor and a node is
            # refused anyway by check_class_name, which wants one class
            if role == "supervisor":
                return "supervisor"
            if role == "fbpprocess" and found_role is None:
                found_role = "fbpprocess"
    return found_role or "unknown"


def is_run_line(statement, class_names):
    """Whether `statement` is the line <Name>().run() of one of the classes
    named in `class_names`."""
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
        and call.func.value.func.id in class_names
        and not call.func.value.args
        and not call.func.value.keywords
    )


def is_main_guard(statement):
    """Whether `statement` is if __name__ == "__main__":, which holds when the
    engine runs the heredoc, as python3 -c runs it as the main module."""
    if not isinstance(statement, ast.If) or not isinstance(statement.test, ast.Compare):
        return False
    test = statement.test
    return (
        isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def is_node_start(statement):
    """
    Whether the top-level statement `statement` calls a method run() with no
    arguments, as a node is started, outside a definition and outside
    if __name__ == "__main__":. A call with arguments, such as
    subprocess.run([...]), starts no node.
    """
    if isinstance(statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or is_main_guard(statement):
        return False
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and not node.args
        and not node.keywords
        for node in ast.walk(statement)
    )


def has_run_line(tree, name):
    """Whether the module has the line <name>().run(), at the top level or
    under if __name__ == "__main__":."""
    for statement in tree.body:
        if is_run_line(statement, {name}):
            return True
        if is_main_guard(statement) and any(is_run_line(inner, {name}) for inner in statement.body):
            return True
    return False


def get_bindings(node):
    """The (name, line) pairs that `node`, a statement at the top level, binds
    in the module."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name, node.lineno
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            if alias.name != "*":
                yield alias.asname or alias.name.split(".")[0], node.lineno
        return
    if isinstance(node, _SCOPES):
        return
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield node.id, node.lineno
    for child in ast.iter_child_nodes(node):
        yield from get_bindings(child)


def check_class_name(processname, source):
    """
    The first rule that the class of the node of `processname`, in its Python
    heredoc `source`, breaks, as a message, or None. The class is the one that
    derives from a class of the runtime library; it is named after its
    process (see get_node_class_name), hides no class of the runtime library,
    no builtin and nothing that the heredoc binds at its top level, and the
    heredoc has the line that starts it. Raises SyntaxError when `source` is
    not valid Python.
    """
    tree = ast.parse(source)
    expected = get_node_class_name(processname)

    if expected in RUNTIME_CLASSES:
        return (f"the class of process {processname} is named {expected}, after the process, "
                "which is a class of the runtime library that it would hide: rename the process")
    if expected in dir(builtins):
        return (f"the class of process {processname} is named {expected}, after the process, "
                "which is a Python builtin that it would hide: rename the process")

    classes = find_node_classes(tree)
    if len(classes) != 1:
        names = ", ".join(node.name for node in classes)
        return (f"process {processname} defines {len(classes)} classes deriving from a class of "
                f"the runtime library ({names}), but a node defines exactly one")
    node_class = classes[0]
    if node_class.name != expected:
        return (f"process {processname} names its class {node_class.name}, but the class of a "
                f"node is named after its process, in CamelCase: {expected}")

    for statement in tree.body:
        if statement is node_class:
            continue
        for name, line in get_bindings(statement):
            if name == expected:
                return (f"the class of process {processname}, {expected}, has the name of what "
                        f"its code also defines on line {line}, which it would hide")

    if not has_run_line(tree, expected):
        return (f"process {processname} has no line {expected}().run(), at the top level or "
                'under if __name__ == "__main__":, which is how a node is started')
    return None


def main():
    """
    classify, or check-class-name <process>, on the heredoc read from stdin:
    prints the role, or nothing. Exits 1, with an error on stderr, on a
    source that is not valid Python, on a rule of the class broken, or on a
    wrong command.
    """
    args = sys.argv[1:]
    source = sys.stdin.read()
    try:
        if args == ["classify"]:
            print(classify_role(source))
            return
        if len(args) == 2 and args[0] == "check-class-name":
            violation = check_class_name(args[1], source)
            if violation is not None:
                print(f"Error: {violation}", file=sys.stderr)
                sys.exit(1)
            return
    except SyntaxError as exc:
        print(f"Error: invalid Python source ({exc})", file=sys.stderr)
        sys.exit(1)
    print("Usage: debasher_node_source.py classify | check-class-name <process>", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
