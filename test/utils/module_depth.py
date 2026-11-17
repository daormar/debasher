#!/usr/bin/env python3
"""Depth of the modules of the engine, in the sense of Ousterhout.

A deep module hides a lot of implementation behind a small interface; a
shallow one is almost all interface. For every module (a file) this weighs
the lines of code of its implementation against the cost of its interface:

- code: lines of code, without blank lines, comments or docstrings;
- names: the functions (and, in Python, classes) of the module that another
  file uses, whatever their name: a name with a leading `_` that another
  file calls is interface all the same;
- params: the parameters of those names (in Python, a class adds those of
  its constructor and its public methods);
- state: variables of the module that other files share, and that some
  function writes: Bash globals (variables in capitals declared at the top
  level or with `declare -g`), Python module variables that a function
  rebinds with `global`;
- const: shared variables that no function writes. They are listed, but not
  counted in the interface, as they cost the reader little;
- I: names + params + state, the cost of the interface;
- depth: code / I.

Who uses a module are the other modules of the report and the clients:
the Bash or Python files under the client directories, tests excluded.

A last row, the facade for authors, takes all the modules as a single one,
whose interface is what the authors of programs see of it: the functions
it declares public (in Bash, those without a leading `_` after the
namespace; in Python, those of an `__all__`), and any other name that the
files under the author directories use. Bash authors call the public
functions without the namespace, through one line wrappers that the
library defines (`f() { debasher::f "$@"; }`): a call to the wrapper counts
as one to the function.

The measure is a heuristic, as Ousterhout's own notion is: lines of code
stand for functionality, and the informal part of an interface (the order
of calls, files expected on disk) is not seen. It ranks modules to look at,
it does not grade them.

Usage: module_depth.py [--clients DIR ...] [--authors DIR ...] [-v]
           [PATH ...]

PATH is a .sh or .py file, or a directory whose files are all taken
(default: the Bash library of the engine, engine/debasher_lib_*.sh, and the
Python runtime library, engine/debasher_runtime_*.py). Bash and Python
modules are reported apart.
"""

import argparse
import ast
import glob
import io
import os
import re
import sys
import tokenize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bash_complexity as bc  # noqa: E402

DEFAULT_PATHS = ["engine/debasher_lib_*.sh", "engine/debasher_runtime_*.py"]
DEFAULT_CLIENTS = ["engine", "api", "data", "sdk"]
DEFAULT_AUTHORS = ["data"]
SKIPPED_DIRS = {"test", "tests", "__pycache__", "node_modules", "share", "lib"}

BASH_WORD = re.compile(r"[A-Za-z_][\w:.\-]*")
BASH_DECLARE = re.compile(
    r"^\s*(?:declare|readonly|export|typeset)(?:\s+-\w+)*\s+([A-Za-z_]\w*)")
BASH_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_]\w*)(?:\[[^]]*\])?\+?=")
BASH_DECLARE_GLOBAL = re.compile(
    r"\bdeclare\s+-\w*g\w*(?:\s+-\w+)*\s+([A-Za-z_]\w*)")
BASH_POSITIONAL = re.compile(r"\$\{?([1-9])(?!\d)")
BASH_ALL_ARGS = re.compile(r"\$\{?[@*]")
SINGLE_QUOTED = re.compile(r"'[^']*'")
BASH_WRAPPER = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*\(\)\s*\{\s*([\w:]+::\w+)\s+"\$@"\s*;?\s*\}')
# Variables of the environment, which a script may set but no module owns
ENVIRONMENT = {"PATH", "HOME", "PWD", "IFS", "LANG", "LC_ALL", "TMPDIR",
               "SHELL", "USER"}


class Module:
    def __init__(self, path):
        self.path = path
        self.code = 0
        self.names = []    # (name, params) used by other files
        self.state = []
        self.const = []
        # Only for the facade: public names no author uses, and names with
        # a leading _ that an author uses
        self.unused = []
        self.leaked = []

    @property
    def interface(self):
        return (len(self.names) + sum(p for _, p in self.names)
                + len(self.state))

    @property
    def depth(self):
        """None for a module that no other file uses."""
        return self.code / self.interface if self.interface else None


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def expand_paths(paths, suffix):
    """The files with the given suffix that the paths (files, directories or
    glob patterns) name."""
    found = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)) or [pattern]:
            if os.path.isdir(path):
                found += [os.path.join(path, n)
                          for n in sorted(os.listdir(path))
                          if n.endswith(suffix)]
            elif path.endswith(suffix) and os.path.isfile(path):
                found.append(path)
    return [os.path.normpath(p) for p in found]


def find_client_files(dirs, suffix, modules):
    """The files with the suffix under the client directories, tests,
    installed copies and the modules themselves left out."""
    found = []
    for top in dirs:
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                                 and d not in SKIPPED_DIRS)
            found += [os.path.normpath(os.path.join(dirpath, n))
                      for n in sorted(filenames) if n.endswith(suffix)]
    return [p for p in found if p not in modules]


def read_lines(path):
    with open(path, errors="replace") as f:
        return f.read().splitlines()


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------

def strip_bash_comment(line):
    """The line without a comment, or empty if the whole line is one."""
    return "" if line.lstrip().startswith("#") else line


def get_bash_bodies(path):
    """The functions of a Bash file, each with the lines of its body, and
    the lines that lie outside any function."""
    lines = read_lines(path)
    functions = bc.functions_of(path)
    inside = set()
    bodies = []
    for fn in functions:
        span = range(fn.line, fn.line + fn.lines)
        inside.update(span)
        bodies.append((fn, [lines[i] for i in span if i < len(lines)]))
    outside = [l for i, l in enumerate(lines) if i not in inside]
    return bodies, outside


def count_bash_code_lines(body):
    scanner = bc.LineScanner()
    return sum(1 for line in body
               if scanner.code(line).strip() not in ("", "{"))


def count_bash_params(body):
    """The positional parameters a function body reads, plus one if it takes
    a variable number of them."""
    text = "\n".join(SINGLE_QUOTED.sub("", strip_bash_comment(l))
                     for l in body)
    return (len(set(BASH_POSITIONAL.findall(text)))
            + (1 if BASH_ALL_ARGS.search(text) else 0))


def find_bash_globals(files):
    """The variables declared or assigned outside functions, or declared
    with `declare -g` inside one, in any of the files, whose name is in
    capitals."""
    names = set()
    for path in files:
        bodies, outside = get_bash_bodies(path)
        for line in outside:
            m = BASH_DECLARE.match(line) or BASH_ASSIGN.match(line)
            if m:
                names.add(m.group(1))
        for _, body in bodies:
            for line in body:
                names.update(BASH_DECLARE_GLOBAL.findall(line))
    # Globals of the engine are in capitals; a lowercase variable at the top
    # level of a script is the script's own, not one of the library
    return {n for n in names if n.isupper() and n not in ENVIRONMENT}


def get_bash_writes(line, names):
    """The globals that a line of a function body assigns."""
    written = set()
    m = BASH_ASSIGN.match(line)
    if m and m.group(1) in names:
        written.add(m.group(1))
    written.update(n for n in BASH_DECLARE_GLOBAL.findall(line) if n in names)
    for m in re.finditer(r"\b(?:unset|mapfile|readarray)\b[^;|&]*", line):
        written.update(w for w in BASH_WORD.findall(m.group(0)) if w in names)
    return written


def get_bash_usage(path, names):
    """For a Bash file: the words of its code (to find the functions of
    other files that it calls), the globals its functions or its top level
    code touch, and those its functions write. A declaration at the top
    level is not a use."""
    bodies, outside = get_bash_bodies(path)
    words, touched, written = set(), set(), set()
    for _, body in bodies:
        for line in map(strip_bash_comment, body):
            found = set(BASH_WORD.findall(line))
            words |= found
            touched |= found & names
            written |= get_bash_writes(line, names)
    for line in map(strip_bash_comment, outside):
        found = set(BASH_WORD.findall(line))
        words |= found
        if not (BASH_DECLARE.match(line) or BASH_ASSIGN.match(line)):
            touched |= found & names
    return words, touched, written


def find_bash_wrappers(files):
    """The one line wrappers of the files: wrapper name -> function."""
    wrappers = {}
    for path in files:
        for line in read_lines(path):
            m = BASH_WRAPPER.match(line)
            if m:
                wrappers[m.group(1)] = m.group(2)
    return wrappers


def is_public_bash_function(name):
    return not name.split("::")[-1].startswith("_")


def measure_bash(modules, clients, authors):
    """One Module per Bash file of modules, and the facade for authors."""
    names = find_bash_globals(modules + clients)
    usage = {p: get_bash_usage(p, names) for p in set(modules + clients
                                                     + authors)}
    # A call to a wrapper is a call to the function it wraps
    wrappers = find_bash_wrappers(modules)
    for words, _, _ in usage.values():
        words |= {wrappers[w] for w in words & wrappers.keys()}
    written = set().union(*(u[2] for u in usage.values()))
    author_words = set().union(*(usage[p][0] for p in authors))
    author_touched = set().union(*(usage[p][1] for p in authors))

    whole = Module("facade for authors")
    report = []
    for path in modules:
        mod = Module(path)
        others = [p for p in modules + clients if p != path]
        other_words = set().union(*(usage[p][0] for p in others))
        other_touched = set().union(*(usage[p][1] for p in others))
        for fn, body in get_bash_bodies(path)[0]:
            mod.code += count_bash_code_lines(body)
            if fn.name in other_words:
                mod.names.append((fn.name, count_bash_params(body)))
            public = is_public_bash_function(fn.name)
            if public or fn.name in author_words:
                whole.names.append((fn.name, count_bash_params(body)))
            if public and fn.name not in author_words:
                whole.unused.append(fn.name)
            if not public and fn.name in author_words:
                whole.leaked.append(fn.name)
        shared = usage[path][1] & other_touched
        mod.state = sorted(shared & written)
        mod.const = sorted(shared - written)
        whole.code += mod.code
        report.append(mod)
    modules_touched = set().union(*(usage[p][1] for p in modules))
    shared = modules_touched & author_touched
    whole.state = sorted(shared & written)
    whole.const = sorted(shared - written)
    return report, whole


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def parse_python(path):
    with open(path, errors="replace") as f:
        source = f.read()
    try:
        return source, ast.parse(source, path)
    except SyntaxError:
        return source, None


def count_python_code_lines(source, tree):
    """Lines holding a token of code, docstrings left out."""
    docstrings = set()
    for node in ast.walk(tree):
        has_docstring = isinstance(node, (
            ast.Module, ast.ClassDef, ast.FunctionDef,
            ast.AsyncFunctionDef)) and ast.get_docstring(node)
        if has_docstring:
            doc = node.body[0]
            docstrings.update(range(doc.lineno, doc.end_lineno + 1))
    lines = set()
    skipped = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
               tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in skipped:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(lines - docstrings)


def count_python_params(fn, method=False):
    args = fn.args
    count = (len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
             + (1 if args.vararg else 0) + (1 if args.kwarg else 0))
    # self or cls is not something the caller passes
    is_static = any(isinstance(d, ast.Name) and d.id == "staticmethod"
                    for d in fn.decorator_list)
    return count - 1 if method and not is_static and count else count


def count_class_params(cls):
    """The parameters of the constructor, plus one and the parameters of
    each public method."""
    count = 0
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "__init__":
            count += count_python_params(node, method=True)
        elif not node.name.startswith("_"):
            count += 1 + count_python_params(node, method=True)
    return count


def get_python_definitions(tree):
    """The top level names a module defines: name -> (kind, params), where
    kind is "def", "state" or "const" (a variable named in capitals, or one
    no function of the module rebinds with `global`)."""
    rebound = {n for node in ast.walk(tree) if isinstance(node, ast.Global)
               for n in node.names}
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = ("def", count_python_params(node))
        elif isinstance(node, ast.ClassDef):
            defs[node.name] = ("def", count_class_params(node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) \
                else [node.target]
            for t in targets:
                for name in ast.walk(t):
                    if isinstance(name, ast.Name) and name.id != "__all__":
                        kind = "state" if name.id in rebound \
                            and not name.id.isupper() else "const"
                        defs[name.id] = (kind, 0)
    return defs


def get_python_reexports(tree):
    """The names a module imports and lists in its __all__: name -> the
    module it imports it from."""
    exported = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__"
                for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                exported = {e.value for e in node.value.elts
                            if isinstance(e, ast.Constant)}
    imported = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                name = alias.asname or alias.name
                if name in exported:
                    imported[name] = node.module
    return imported


def get_python_uses(tree):
    """The names a file takes from other modules: module -> set of names."""
    uses = {}
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            uses.setdefault(node.module, set()).update(
                a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name] = a.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) \
                and isinstance(node.value, ast.Name) \
                and node.value.id in aliases:
            uses.setdefault(aliases[node.value.id], set()).add(node.attr)
    return uses


def resolve_python_name(name, module, defs, reexports):
    """The kind and parameters of a name of a module, following a
    re-export to the module that defines it."""
    seen = set()
    while (module, name) not in seen:
        seen.add((module, name))
        if name in defs.get(module, {}):
            return defs[module][name]
        if name not in reexports.get(module, {}):
            break
        module = reexports[module][name]
    return None


def add_python_name(mod, name, entry):
    kind, params = entry
    if kind == "def":
        mod.names.append((name, params))
    elif kind == "state":
        mod.state.append(name)
    else:
        mod.const.append(name)


def get_python_all(tree):
    """The names of the __all__ of a module, or None if it has none."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__"
                for t in node.targets) \
                and isinstance(node.value, (ast.List, ast.Tuple)):
            return {e.value for e in node.value.elts
                    if isinstance(e, ast.Constant)}
    return None


def measure_python(modules, clients, authors):
    """One Module per Python file of modules, and the facade for
    authors."""
    parsed = {p: parse_python(p) for p in set(modules + clients + authors)}
    parsed = {p: v for p, v in parsed.items() if v[1] is not None}
    module_name = {p: os.path.splitext(os.path.basename(p))[0]
                   for p in parsed}
    defs = {module_name[p]: get_python_definitions(parsed[p][1])
            for p in modules if p in parsed}
    reexports = {module_name[p]: get_python_reexports(parsed[p][1])
                 for p in modules if p in parsed}
    uses = {p: get_python_uses(parsed[p][1]) for p in parsed}

    whole = Module("facade for authors")
    # The declared facade: the __all__ of the modules, or their public
    # names if none has one
    declared = {(module_name[p], n) for p in modules if p in parsed
                for n in get_python_all(parsed[p][1]) or ()}
    if not declared:
        declared = {(m, n) for m, d in defs.items() for n in d
                    if not n.startswith("_")}
    used_by_authors = set()
    report = []
    for path in modules:
        if path not in parsed:
            continue
        name = module_name[path]
        mod = Module(path)
        mod.code = count_python_code_lines(*parsed[path])
        used = set().union(*(u.get(name, set())
                             for p, u in uses.items() if p != path))
        for n in sorted(used):
            entry = resolve_python_name(n, name, defs, reexports)
            if entry:
                add_python_name(mod, n, entry)
        whole.code += mod.code
        for p in authors:
            if p in uses:
                used_by_authors |= {(name, n)
                                    for n in uses[p].get(name, set())}
        report.append(mod)
    # A name re-exported by a facade is one name of the whole, not two
    resolved = {}
    for module, n in declared | used_by_authors:
        entry = resolve_python_name(n, module, defs, reexports)
        if entry:
            resolved[n] = entry
    used = {n for _, n in used_by_authors}
    for n, entry in sorted(resolved.items()):
        add_python_name(whole, n, entry)
        if n not in used:
            whole.unused.append(n)
        elif n.startswith("_"):
            whole.leaked.append(n)
    return report, whole


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(title, report, whole, verbose):
    print(title)
    print(f"{'code':>6} {'names':>5} {'params':>6} {'state':>5} {'const':>5} "
          f"{'I':>5} {'depth':>6}  module")
    # A module with no interface goes last: its depth is not defined
    ranked = sorted(report, key=lambda m: (m.depth is None, m.depth or 0))
    for mod in ranked + [whole]:
        if mod is whole:
            print("-" * 60)
        depth = "-" if mod.depth is None else f"{mod.depth:.1f}"
        print(f"{mod.code:6d} {len(mod.names):5d} "
              f"{sum(p for _, p in mod.names):6d} {len(mod.state):5d} "
              f"{len(mod.const):5d} {mod.interface:5d} {depth:>6}  "
              f"{mod.path}")
        if verbose:
            for n, p in mod.names:
                print(f"{'':42}name  {n} ({p})")
            for n in mod.state:
                print(f"{'':42}state {n}")
            for n in mod.unused:
                print(f"{'':42}unused by authors {n}")
            for n in mod.leaked:
                print(f"{'':42}private used by authors {n}")
    print()


LEGEND = """\
Columns:
  code    lines of code of the module, without blank lines, comments or
          docstrings: what it implements
  names   functions (Python: also classes) of the module that another file
          uses, with or without a leading _
  params  parameters of those names; a Python class adds those of its
          constructor and one plus the parameters of each public method
  state   variables of the module that other files share and some function
          writes: what couples modules most, so it counts as interface
  const   shared variables that no function writes; shown, not counted
  I       cost of the interface: names + params + state
  depth   code / I; low means a shallow module, almost all interface,
          and "-" one that no client uses (tests are not clients)
Rows are ordered from the shallowest module. The last row, the facade for
authors, takes all the modules as one, whose interface is what an author of
programs sees: the functions it declares public (Bash: no leading _ after
the namespace; Python: an __all__) and any other name that author code (the
--authors directories) uses. With -v it lists the public names that no
author code uses, and the private ones that some author code does."""


def main():
    parser = argparse.ArgumentParser(
        description="Depth of the modules of the engine: lines of code "
        "against the cost of their interface.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help=".sh or .py files, directories or glob patterns "
                        "(default: " + " ".join(DEFAULT_PATHS) + ")")
    parser.add_argument("--clients", nargs="+", default=DEFAULT_CLIENTS,
                        help="directories of the files that use the modules, "
                        "tests excluded (default: "
                        + " ".join(DEFAULT_CLIENTS) + ")")
    parser.add_argument("--authors", nargs="+", default=DEFAULT_AUTHORS,
                        help="directories of the programs written by authors, "
                        "for the facade (default: "
                        + " ".join(DEFAULT_AUTHORS) + ")")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list the names and the state of each module")
    args = parser.parse_args()

    for suffix, measure, language in ((".sh", measure_bash, "Bash"),
                                      (".py", measure_python, "Python")):
        modules = expand_paths(args.paths, suffix)
        if not modules:
            continue
        clients = find_client_files(args.clients, suffix, set(modules))
        authors = find_client_files(args.authors, suffix, set(modules))
        report, whole = measure(modules, clients, authors)
        print_report(f"Depth of the {language} modules "
                     f"(clients: {' '.join(args.clients)}; "
                     f"authors: {' '.join(args.authors)})",
                     report, whole, args.verbose)
    print(LEGEND)


if __name__ == "__main__":
    sys.exit(main())
