#!/usr/bin/env python3
"""Complexity of the Bash functions of the engine.

There is no CRAP score for Bash here (no coverage), but the complexity of a
function says on its own when it is worth splitting, and how many test files
name it hints at whether it is tested. For every function of the given Bash
files this lists:

- CC: its cyclomatic complexity, one plus its decision points: `if`, `elif`,
  `for`, `while`, `until`, every `case` item but a final `*)`, and every
  `&&` and `||`;
- lines: the lines of its body;
- depth: the deepest nesting of `if`, `for`, `while`, `until` and `case`;
- tests: how many test files under the test directory contain its name. It
  counts direct mentions only: a function a test only reaches through
  another one counts as 0.

The parser is line based and knows the style of the engine rather than the
whole Bash grammar: a function starts with `name()` (or `function name`) and
ends at the first `}` alone on a line with the indentation of its start;
quoted text, comments and here-documents are skipped. That is enough to rank
functions, not to measure them exactly.

Usage: bash_complexity.py [--top N] [--threshold CC] [--tests DIR]
           [PATH ...]

PATH is a Bash file or a directory, whose *.sh files are read (default:
engine). Without --top, the functions whose complexity is above the
threshold (default 10) are listed.
"""

import argparse
import os
import re
import sys

DEFAULT_THRESHOLD = 10

FUNCTION_START = re.compile(
    r"^(?P<indent>\s*)(?:function\s+(?P<kw_name>[^\s()]+)\s*(?:\(\s*\))?"
    r"|(?P<name>[A-Za-z_][\w:.\-]*)\s*\(\s*\))\s*(?P<brace>\{)?\s*(?:#.*)?$")
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_]\w*)\2")
OPENERS = {"if", "for", "while", "until", "case"}
CLOSERS = {"fi", "done", "esac"}
LOOPS_AND_IFS = {"if", "elif", "for", "while", "until"}
# Words after which the next word is in command position again
COMMAND_PREFIXES = {"then", "do", "else", "elif", "if", "while", "until", "!",
                    "{", "(", "time"}


class LineScanner:
    """Removes quoted text and comments from lines of Bash, keeping the
    state of a quote left open at the end of a line for the next one."""

    def __init__(self):
        self.quote = None

    def code(self, line):
        out = []
        i = 0
        while i < len(line):
            c = line[i]
            if self.quote:
                if c == "\\" and self.quote == '"':
                    i += 2
                    continue
                if c == self.quote:
                    self.quote = None
                    out.append(" ")
                i += 1
                continue
            if c == "\\":
                out.append("  ")
                i += 2
                continue
            if c in "'\"":
                self.quote = c
                out.append(" ")
            elif c == "#" and (i == 0 or line[i - 1] in " \t;|&("):
                break
            else:
                out.append(c)
            i += 1
        return "".join(out)


def commands(code):
    """Split a line of code (quotes and comments removed) into its simple
    commands, each as a list of words."""
    for part in re.split(r"&&|\|\||;;&|;;|;&|[;|&]", code):
        words = part.replace("(", " ( ").replace(")", " ) ").split()
        if words:
            yield words


class Function:
    def __init__(self, name, path, line, indent):
        self.name = name
        self.path = path
        self.line = line
        self.indent = indent
        self.complexity = 1
        self.lines = 0
        self.depth = 0
        self.max_depth = 0


def measure(fn, code):
    """Add the decision points and the nesting of a line of code to fn."""
    fn.complexity += code.count("&&") + code.count("||")
    fn.complexity += len(re.findall(r";;&?|;&", code))
    for words in commands(code):
        # Only words in command position are keywords
        position = True
        for w in words:
            if not position:
                break
            if w in LOOPS_AND_IFS:
                fn.complexity += 1
            if w in OPENERS:
                fn.depth += 1
                fn.max_depth = max(fn.max_depth, fn.depth)
            elif w in CLOSERS:
                fn.depth = max(0, fn.depth - 1)
            position = w in COMMAND_PREFIXES
    # A final `*)` item is the default of a case, not a decision
    if re.match(r"^\s*\*\s*\)", code):
        fn.complexity -= 1


def functions_of(path):
    with open(path, errors="replace") as f:
        lines = f.read().splitlines()
    found = []
    scanner = LineScanner()
    current = None
    heredoc = None  # (delimiter, strip_tabs)
    for number, line in enumerate(lines, start=1):
        if heredoc:
            delimiter, strip_tabs = heredoc
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                heredoc = None
            if current:
                current.lines += 1
            continue
        if scanner.quote is None:
            m = FUNCTION_START.match(line)
            if m and not current:
                current = Function(m.group("kw_name") or m.group("name"), path,
                                   number, m.group("indent"))
                continue
            if current and line.rstrip() == current.indent + "}":
                found.append(current)
                current = None
                continue
        code = scanner.code(line)
        # The delimiter may be quoted, and the code has lost its quotes: look
        # for it in the line itself once the code shows a << outside quotes
        h = HEREDOC.search(line) if "<<" in code else None
        if h:
            heredoc = (h.group(3), h.group(1) == "-")
        if current:
            current.lines += 1
            if code.strip() != "{":
                measure(current, code)
    return found


def bash_files(paths):
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.endswith(".sh"):
                    yield os.path.join(path, name)
        else:
            yield path


def test_mentions(names, test_dir):
    """For every function name, how many files under test_dir contain it."""
    counts = dict.fromkeys(names, 0)
    if not test_dir or not os.path.isdir(test_dir):
        return counts
    # A name is bounded by characters that cannot be part of a name
    patterns = {n: re.compile(rf"(?<![\w:.\-]){re.escape(n)}(?![\w:.\-])")
                for n in names}
    for dirpath, dirnames, filenames in os.walk(test_dir):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "__pycache__"]
        for filename in filenames:
            with open(os.path.join(dirpath, filename), errors="replace") as f:
                text = f.read()
            for name, pattern in patterns.items():
                if pattern.search(text):
                    counts[name] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Complexity of the Bash functions of the engine.")
    parser.add_argument("paths", nargs="*", default=["engine"],
                        help="Bash files, or directories of *.sh files "
                        "(default: engine)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help="complexity above which a function is listed "
                        f"(default {DEFAULT_THRESHOLD})")
    parser.add_argument("--top", type=int,
                        help="list the N most complex functions instead")
    parser.add_argument("--tests", default="test/engine",
                        help="directory whose files are searched for the "
                        "names of the functions (default: test/engine)")
    args = parser.parse_args()

    functions = [fn for path in bash_files(args.paths)
                 for fn in functions_of(path)]
    functions.sort(key=lambda fn: (fn.complexity, fn.lines), reverse=True)
    flagged = [fn for fn in functions if fn.complexity > args.threshold]
    listed = functions[:args.top] if args.top is not None else flagged
    mentions = test_mentions({fn.name for fn in listed}, args.tests)

    print(f"Complexity of the Bash functions of {' '.join(args.paths)} "
          f"(tests: {args.tests})")
    print(f"{len(functions)} functions, {len(flagged)} with complexity above "
          f"{args.threshold}, "
          f"{sum(fn.complexity > 20 for fn in functions)} above 20")
    if listed:
        print()
        print(f"{'CC':>4} {'lines':>6} {'depth':>5} {'tests':>5}  function")
        for fn in listed:
            print(f"{fn.complexity:4d} {fn.lines:6d} {fn.max_depth:5d} "
                  f"{mentions[fn.name]:5d}  {fn.name}  ({fn.path}:{fn.line})")


if __name__ == "__main__":
    sys.exit(main())
