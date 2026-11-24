#!/usr/bin/env python3
"""Duplication of the code: fragments and functions written twice.

Code copied and then adapted is a fix that has to be made twice, and the
second copy is the one that gets forgotten. This report finds two kinds of
duplication in the source files of the repository:

- clones: fragments of at least --min-tokens tokens that are the same
  code in two places. A clone is exact when the tokens are the same, or
  renamed when the identifiers differ but map one to one between the two
  fragments (the same name on one side is always the same name on the
  other). In both kinds at least --min-same of the identifiers and
  literals (strings and numbers) are the same on both sides, so that two
  runs of `echo "..."` with different texts are not a clone. Comments,
  whitespace and import statements do not count;
- similar functions: pairs of functions whose bodies share at least
  --min-similarity of their sequences of 5 tokens (weighted Jaccard
  similarity, a sequence counted as many times as it appears), which also
  finds a copy with lines added or removed.

Each pair is marked with its span, as in coupling.py: dir, part, cross or
test. The report ends with the duplicated lines of each part of the code
and of each file: the lines of code that lie in some clone.

Files are tokenized by language: Python with the tokenize module, Bash and
TypeScript with a scanner of their own that knows quotes, comments,
here-documents and template strings. Functions are found with ast in
Python, with the parser of bash_complexity.py in Bash, and in TypeScript
as function declarations, functions assigned to a variable and methods. It
is enough to rank the duplication, not to measure it exactly.

Usage: duplication.py [--min-tokens N] [--min-same FRACTION]
                      [--min-similarity FRACTION] [--min-function-tokens N]
                      [--top N] [--span SPAN] [--include-tests] [PATH ...]

PATH is a directory or file of the repository (default: engine, api,
frontend/src, frontend/mcp/src and sdk). Tests are left out unless
--include-tests is given. --span, which may be repeated, lists only the
pairs of that span.
"""

import argparse
import ast
import io
import keyword
import os
import re
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict

# Importing the other reports would leave their bytecode next to them
sys.dont_write_bytecode = True
from bash_complexity import functions_of as bash_functions_of
from coupling import SPANS, part, span
from hotspots import git, source_files

DEFAULT_PATHS = ["engine", "api", "frontend/src", "frontend/mcp/src", "sdk"]
SHINGLE = 5
# A window of tokens found in more places than this is boilerplate (a run
# of `local x="$1"`, say): it is not compared, or the pairs would be many
COMMON_WINDOW = 40

PY_KEYWORDS = set(keyword.kwlist) | set(keyword.softkwlist)
TS_KEYWORDS = {
    "abstract", "as", "async", "await", "break", "case", "catch", "class",
    "const", "continue", "debugger", "declare", "default", "delete", "do",
    "else", "enum", "export", "extends", "false", "finally", "for", "from",
    "function", "get", "if", "implements", "import", "in", "instanceof",
    "interface", "keyof", "let", "new", "null", "of", "private",
    "protected", "public", "readonly", "return", "set", "static", "super",
    "switch", "this", "throw", "true", "try", "type", "typeof",
    "undefined", "var", "void", "while", "with", "yield"}
SH_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "case", "esac", "for", "while",
    "until", "do", "done", "in", "function", "select", "time", "local",
    "declare", "return", "exit", "echo", "printf", "read", "shift", "set",
    "unset", "export", "readonly", "eval", "exec", "trap", "test", "break",
    "continue", "true", "false"}


class Token:
    """A token: its text, its kind (ID for an identifier, LIT for a
    literal, its own text for a keyword or an operator) and its line."""

    __slots__ = ("raw", "kind", "line")

    def __init__(self, raw, kind, line):
        self.raw = raw
        self.kind = kind
        self.line = line


def make_token(raw, line, keywords):
    if raw in keywords:
        return Token(raw, raw, line)
    return Token(raw, "ID", line)


def tokenize_python(text):
    tokens = []
    skipping = False  # inside an import statement
    at_start = True  # at the start of a logical line
    fstring_depth = 0
    fstring_line = 0
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            ttype, raw, (line, _), _, _ = t
            if ttype in (tokenize.NEWLINE, tokenize.ENDMARKER):
                skipping, at_start = False, True
                continue
            if ttype in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT,
                         tokenize.DEDENT, tokenize.ENCODING):
                continue
            # An f-string is one literal, whatever its expressions hold
            if ttype == getattr(tokenize, "FSTRING_START", None):
                if fstring_depth == 0:
                    fstring_line = line
                fstring_depth += 1
                continue
            if ttype == getattr(tokenize, "FSTRING_END", None):
                fstring_depth -= 1
                if fstring_depth == 0 and not skipping:
                    tokens.append(Token('f""', "LIT", fstring_line))
                continue
            if fstring_depth:
                continue
            if at_start and raw in ("import", "from"):
                skipping = True
            at_start = False
            if skipping:
                continue
            if ttype in (tokenize.STRING, tokenize.NUMBER):
                tokens.append(Token(raw, "LIT", line))
            elif ttype == tokenize.NAME:
                tokens.append(make_token(raw, line, PY_KEYWORDS))
            else:
                tokens.append(Token(raw, raw, line))
    except (tokenize.TokenError, SyntaxError):
        pass
    return tokens


TS_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)
  | (?P<num>\d[\w.]*)
  | (?P<id>[A-Za-z_$][\w$]*)
  | (?P<op>=>|===|!==|==|!=|<=|>=|&&|\|\||\?\?|\?\.|\.\.\.|\+\+|--
           |[-+*/%&|^]=|\S)
""", re.X | re.S)


def tokenize_typescript(text):
    tokens = []
    line = 1
    for m in TS_TOKEN.finditer(text):
        raw = m.group()
        kind = m.lastgroup
        if kind == "str" or kind == "num":
            tokens.append(Token(raw, "LIT", line))
        elif kind == "id":
            tokens.append(make_token(raw, line, TS_KEYWORDS))
        elif kind == "op":
            tokens.append(Token(raw, raw, line))
        line += raw.count("\n")
    return drop_typescript_imports(tokens)


def drop_typescript_imports(tokens):
    """Leave out the import statements: `import ... from "x";` and
    `import "x";`, but not a dynamic `import(...)`."""
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        starts = not out or out[-1].raw in (";", "}")
        nxt = tokens[i + 1].raw if i + 1 < len(tokens) else ""
        if t.raw == "import" and starts and nxt not in ("(", "."):
            j = i + 1
            # The statement ends at its module name: the literal that
            # follows `from`, or the one right after `import`
            while j < len(tokens):
                if tokens[j].kind == "LIT" and (
                        j == i + 1 or tokens[j - 1].raw == "from"):
                    break
                j += 1
            if j + 1 < len(tokens) and tokens[j + 1].raw == ";":
                j += 1
            i = j + 1
            continue
        out.append(t)
        i += 1
    return out


SH_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")
SH_WORD = re.compile(r"[A-Za-z_]\w*(?:(?:::|\.)\w+)*")
SH_VAR = re.compile(r"\$(?:[A-Za-z_]\w*|[0-9@#?*!$-])")
SH_OPS = ("<<<", "&&", "||", ";;", ">>", "[[", "]]", "$((", "$(", "((",
          "))")


def skip_quoted(text, i, quote):
    """Index right after the quote that closes the one at i."""
    j = i + 1
    while j < len(text) and text[j] != quote:
        j += 2 if quote == '"' and text[j] == "\\" else 1
    return j + 1


def tokenize_bash(text):
    tokens = []
    line = 1
    heredocs = []  # delimiters whose bodies start at the next line
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            # A here-document is one literal: its body is text, not code
            for delimiter, strip_tabs in heredocs:
                while i < n:
                    end = text.find("\n", i)
                    end = n if end < 0 else end
                    body_line = text[i:end]
                    i = end + 1
                    line += 1
                    if (body_line.lstrip("\t") if strip_tabs
                            else body_line) == delimiter:
                        break
            heredocs = []
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c == "#" and (i == 0 or text[i - 1] in " \t\n;|&("):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        start, start_line = i, line
        if c in "'\"":
            i = skip_quoted(text, i, c)
            tokens.append(Token(text[start:i], "LIT", start_line))
        elif text.startswith("$'", i):
            i = skip_quoted(text, i + 1, "'")
            tokens.append(Token(text[start:i], "LIT", start_line))
        elif text.startswith("${", i):
            depth, i = 0, i + 1
            while i < n:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            i += 1
            tokens.append(Token(text[start:i], "ID", start_line))
        elif SH_VAR.match(text, i):
            i = SH_VAR.match(text, i).end()
            tokens.append(Token(text[start:i], "ID", start_line))
        elif SH_HEREDOC.match(text, i) and not text.startswith("<<<", i):
            m = SH_HEREDOC.match(text, i)
            heredocs.append((m.group(2), m.group().startswith("<<-")))
            i = m.end()
            tokens.append(Token("<<", "<<", start_line))
            tokens.append(Token(m.group(2), "LIT", start_line))
        elif c.isdigit():
            while i < n and text[i].isdigit():
                i += 1
            tokens.append(Token(text[start:i], "LIT", start_line))
        elif SH_WORD.match(text, i):
            i = SH_WORD.match(text, i).end()
            tokens.append(make_token(text[start:i], start_line, SH_KEYWORDS))
        else:
            op = next((o for o in SH_OPS if text.startswith(o, i)), c)
            i += len(op)
            tokens.append(Token(op, op, start_line))
        line += text.count("\n", start, i)
    return tokens


TOKENIZERS = {".py": tokenize_python, ".sh": tokenize_bash,
              ".ts": tokenize_typescript, ".tsx": tokenize_typescript,
              ".mjs": tokenize_typescript}


class Function:
    def __init__(self, name, path, line, start, end):
        self.name = name
        self.path = path
        self.line = line
        self.start = start  # its first token
        self.end = end  # past its last token
        self.shingles = Counter()


def get_token_range(tokens, first_line, last_line):
    """Indexes of the first token on first_line or after, and past the
    last token on last_line or before."""
    start = next((i for i, t in enumerate(tokens) if t.line >= first_line),
                 len(tokens))
    end = start
    while end < len(tokens) and tokens[end].line <= last_line:
        end += 1
    return start, end


def find_python_functions(path, text, tokens):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start, end = get_token_range(tokens, child.lineno,
                                             child.end_lineno)
                found.append(Function(prefix + child.name, path,
                                      child.lineno, start, end))
                visit(child, prefix + child.name + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, prefix + child.name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def find_bash_functions(path, text, tokens):
    found = []
    for fn in bash_functions_of(path):
        # The body runs from the line after the start to the closing brace
        start, end = get_token_range(tokens, fn.line, fn.line + fn.lines + 1)
        found.append(Function(fn.name, path, fn.line, start, end))
    return found


def find_matching(tokens, i, opening, closing):
    """Index of the token that closes the bracket at i, or None."""
    depth = 0
    for j in range(i, len(tokens)):
        if tokens[j].raw == opening:
            depth += 1
        elif tokens[j].raw == closing:
            depth -= 1
            if depth == 0:
                return j
    return None


def find_body_brace(tokens, i):
    """Index of the `{` that opens a body after the token at i, skipping a
    return type, or None if a `;`, `=` or `,` comes first."""
    for j in range(i, min(i + 40, len(tokens))):
        if tokens[j].raw == "{":
            return j
        if tokens[j].raw in (";", "=", ",", ")"):
            return None
    return None


METHOD_PREFIXES = {"{", "}", ";", "async", "static", "private", "public",
                   "protected", "get", "set", "readonly", "override"}


def find_typescript_functions(path, text, tokens):
    """Function declarations, functions and arrow functions assigned to a
    variable, and methods of classes and object literals."""
    found = []
    n = len(tokens)
    for i, t in enumerate(tokens):
        name, params = None, None
        if t.raw == "function" and i + 2 < n and tokens[i + 1].kind == "ID" \
                and tokens[i + 2].raw == "(":
            name, params = tokens[i + 1].raw, i + 2
        elif t.raw in ("const", "let", "var") and i + 2 < n \
                and tokens[i + 1].kind == "ID":
            # const f = (async)? (function)? (...) (: type)? =>
            j = i + 2
            if tokens[j].raw == ":":
                j = next((k for k in range(j, min(j + 30, n))
                          if tokens[k].raw == "="), n)
            if j < n and tokens[j].raw == "=":
                j += 1
                while j < n and tokens[j].raw in ("async", "function"):
                    j += 1
                if j < n and tokens[j].raw == "(":
                    name, params = tokens[i + 1].raw, j
        elif t.kind == "ID" and i + 1 < n and tokens[i + 1].raw == "(" \
                and i > 0 and tokens[i - 1].raw in METHOD_PREFIXES:
            name, params = t.raw, i + 1
        if name is None:
            continue
        close = find_matching(tokens, params, "(", ")")
        if close is None:
            continue
        j = close + 1
        if j < n and tokens[j].raw == ":":
            j += 1
        while j < n and tokens[j].raw != "{" and tokens[j].raw != "=>" \
                and tokens[j].raw not in (";", ",", ")") and j < close + 40:
            j += 1
        if j < n and tokens[j].raw == "=>":
            j += 1
        brace = j if j < n and tokens[j].raw == "{" else None
        if brace is None:
            continue
        end = find_matching(tokens, brace, "{", "}")
        if end is not None:
            found.append(Function(name, path, t.line, i, end + 1))
    return found


FUNCTION_FINDERS = {".py": find_python_functions, ".sh": find_bash_functions,
                    ".ts": find_typescript_functions,
                    ".tsx": find_typescript_functions,
                    ".mjs": find_typescript_functions}


class SourceFile:
    def __init__(self, path, root):
        self.path = path
        ext = os.path.splitext(path)[1]
        with open(os.path.join(root, path), errors="replace") as f:
            text = f.read()
        self.tokens = TOKENIZERS[ext](text)
        self.code_lines = {t.line for t in self.tokens}
        # bash_complexity.py reads the file itself
        cwd = os.getcwd()
        os.chdir(root)
        try:
            self.functions = FUNCTION_FINDERS[ext](path, text, self.tokens)
        finally:
            os.chdir(cwd)
        self.dup_lines = set()


class Clone:
    def __init__(self, a, i, b, j, length, exact):
        self.a, self.i = a, i
        self.b, self.j = b, j
        self.length = length
        self.exact = exact

    def lines(self, f, start):
        return f.tokens[start].line, f.tokens[start + self.length - 1].line


def hash_windows(files, ids, width):
    """Map the hash of every window of `width` tokens (by kind) to the
    places where it starts, as (file index, token index)."""
    base, mod = 1_000_003, (1 << 61) - 1
    top = pow(base, width, mod)
    buckets = defaultdict(list)
    for fi, f in enumerate(files):
        h = 0
        seq = [ids[t.kind] for t in f.tokens]
        for k, v in enumerate(seq):
            h = (h * base + v) % mod
            if k >= width:
                h = (h - seq[k - width] * top) % mod
            if k >= width - 1:
                buckets[h].append((fi, k - width + 1))
    return buckets


def extend_clone(fa, i, fb, j, limit):
    """Length of the clone starting at token i of fa and j of fb: the
    tokens agree in kind and the identifiers map one to one. Return the
    length, the number of identifiers and literals of the clone, and how
    many of them are the same on both sides."""
    a_to_b, b_to_a = {}, {}
    same = names = 0
    length = 0
    ta, tb = fa.tokens, fb.tokens
    while length < limit and i + length < len(ta) and j + length < len(tb):
        x, y = ta[i + length], tb[j + length]
        if x.kind != y.kind:
            break
        if x.kind == "ID":
            if a_to_b.setdefault(x.raw, y.raw) != y.raw \
                    or b_to_a.setdefault(y.raw, x.raw) != x.raw:
                break
        if x.kind in ("ID", "LIT"):
            names += 1
            same += x.raw == y.raw
        length += 1
    return length, names, same


def find_clones(files, min_tokens, min_same):
    ids = defaultdict(lambda: len(ids))
    clones = []
    for places in hash_windows(files, ids, min_tokens).values():
        if len(places) < 2 or len(places) > COMMON_WINDOW:
            continue
        for p, (fa_i, i) in enumerate(places):
            fa = files[fa_i]
            for fb_i, j in places[p + 1:]:
                fb = files[fb_i]
                # Only the start of a clone: one more token before it
                # that agrees would make this window part of a longer one
                if i > 0 and j > 0 and \
                        fa.tokens[i - 1].kind == fb.tokens[j - 1].kind:
                    continue
                # Two fragments of the same file must not overlap
                limit = j - i if fa_i == fb_i else len(fa.tokens)
                length, names, same = extend_clone(fa, i, fb, j, limit)
                if length < min_tokens or same < min_same * names:
                    continue
                exact = all(fa.tokens[i + k].raw == fb.tokens[j + k].raw
                            for k in range(length))
                clones.append(Clone(fa, i, fb, j, length, exact))
    return drop_contained(clones)


def drop_contained(clones):
    """Leave out the clones whose two fragments lie mostly (half or more)
    inside the two of a longer clone: in repetitive code the same copy
    also aligns shifted by a few tokens, and that says nothing new."""
    kept = []
    for c in sorted(clones, key=lambda c: -c.length):
        def inside(f, start, g, gstart, glen):
            if f is not g:
                return False
            shared = min(start + c.length, gstart + glen) - max(start, gstart)
            return 2 * shared >= c.length
        if not any((inside(c.a, c.i, k.a, k.i, k.length)
                    and inside(c.b, c.j, k.b, k.j, k.length))
                   or (inside(c.a, c.i, k.b, k.j, k.length)
                       and inside(c.b, c.j, k.a, k.i, k.length))
                   for k in kept):
            kept.append(c)
    return kept


def get_shingles(f, fn):
    raws = [t.raw for t in f.tokens[fn.start:fn.end]]
    return Counter(hash(tuple(raws[k:k + SHINGLE]))
                   for k in range(len(raws) - SHINGLE + 1))


def overlaps(fx, fy):
    return fx.path == fy.path and fx.start < fy.end and fy.start < fx.end


def find_similar_functions(files, min_tokens, min_similarity):
    functions = []
    for f in files:
        for fn in f.functions:
            if fn.end - fn.start >= min_tokens:
                fn.shingles = get_shingles(f, fn)
                functions.append(fn)
    # Candidates share some shingle that few functions have: those that
    # many have (a `return` after a call, say) say nothing of a copy
    index = defaultdict(list)
    for k, fn in enumerate(functions):
        for s in fn.shingles:
            index[s].append(k)
    common = max(COMMON_WINDOW, len(functions) // 50)
    candidates = set()
    for ks in index.values():
        if len(ks) <= common:
            for p, x in enumerate(ks):
                for y in ks[p + 1:]:
                    candidates.add((x, y))
    pairs = []
    for x, y in candidates:
        fx, fy = functions[x], functions[y]
        sx, sy = fx.shingles.total(), fy.shingles.total()
        if min(sx, sy) < min_similarity * max(sx, sy) or overlaps(fx, fy):
            continue
        shared = (fx.shingles & fy.shingles).total()
        similarity = shared / (sx + sy - shared)
        if similarity >= min_similarity:
            pairs.append((similarity, fx, fy))
    return pairs


def mark_duplicated_lines(clones):
    for c in clones:
        for f, start in ((c.a, c.i), (c.b, c.j)):
            first, last = c.lines(f, start)
            f.dup_lines.update(line for line in range(first, last + 1)
                               if line in f.code_lines)


def format_percent(part_lines, whole):
    return f"{100 * part_lines / whole:5.1f}%" if whole else "    -"


def main():
    parser = argparse.ArgumentParser(
        description="Fragments and functions written twice.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help="directories or files of the repository "
                        f"(default: {' '.join(DEFAULT_PATHS)})")
    parser.add_argument("--min-tokens", type=int, default=60,
                        help="the shortest clone, in tokens (default 60)")
    parser.add_argument("--min-same", type=float, default=0.5,
                        help="fraction of the identifiers of a renamed "
                        "clone that must be the same on both sides "
                        "(default 0.5)")
    parser.add_argument("--min-similarity", type=float, default=0.7,
                        help="the lowest similarity of two functions "
                        "listed (default 0.7)")
    parser.add_argument("--min-function-tokens", type=int, default=40,
                        help="leave out the functions with fewer tokens "
                        "(default 40)")
    parser.add_argument("--top", type=int, default=20,
                        help="how many pairs and files to list (default 20)")
    parser.add_argument("--span", action="append", choices=SPANS,
                        help="list only the pairs of this span; may be "
                        "repeated (default: all)")
    parser.add_argument("--include-tests", action="store_true",
                        help="also look at the tests")
    parser.add_argument("--root", default=".",
                        help="the repository (default: the current directory)")
    args = parser.parse_args()

    try:
        root = git(args.root, "rev-parse", "--show-toplevel").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("duplication.py: not in a git work tree: the files of the "
                 "report are those git tracks")
    paths = [p for p in source_files(root, args.paths, args.include_tests)
             if os.path.splitext(p)[1] in TOKENIZERS]
    files = [SourceFile(p, root) for p in paths]
    clones = find_clones(files, args.min_tokens, args.min_same)
    mark_duplicated_lines(clones)
    similar = find_similar_functions(files, args.min_function_tokens,
                                     args.min_similarity)

    def listed(a, b):
        return not args.span or span(a, b) in args.span

    total = sum(len(f.code_lines) for f in files)
    dup = sum(len(f.dup_lines) for f in files)
    print(f"Duplication of {' '.join(args.paths)}: {len(files)} files, "
          f"{total} lines of code, {dup} in clones "
          f"({format_percent(dup, total).strip()})")

    by_part = defaultdict(lambda: [0, 0])
    for f in files:
        by_part[part(f.path)][0] += len(f.code_lines)
        by_part[part(f.path)][1] += len(f.dup_lines)
    print()
    print(f"{'lines':>7} {'in clones':>9} {'pct':>6}  part")
    for p, (lines, d) in sorted(by_part.items()):
        print(f"{lines:7d} {d:9d} {format_percent(d, lines)}  {p}")

    rows = [c for c in clones if listed(c.a.path, c.b.path)]
    rows.sort(key=lambda c: (-c.length, c.a.path, c.i))
    kinds = Counter("exact" if c.exact else "renamed" for c in rows)
    spans = f" of span {', '.join(args.span)}" if args.span else ""
    print()
    print(f"Clones{spans} of at least {args.min_tokens} tokens ({len(rows)}: "
          f"{kinds['exact']} exact, {kinds['renamed']} renamed):")
    print()
    print(f"{'tokens':>6} {'lines':>5}  {'kind':<7}  {'span':<5}  fragments")
    for c in rows[:args.top]:
        a_first, a_last = c.lines(c.a, c.i)
        b_first, b_last = c.lines(c.b, c.j)
        kind = "exact" if c.exact else "renamed"
        print(f"{c.length:6d} {a_last - a_first + 1:5d}  {kind:<7}  "
              f"{span(c.a.path, c.b.path):<5}  "
              f"{c.a.path}:{a_first}-{a_last}")
        print(f"{'':>30}{c.b.path}:{b_first}-{b_last}")

    pairs = [p for p in similar if listed(p[1].path, p[2].path)]
    pairs.sort(key=lambda p: (-p[0], -(p[1].end - p[1].start), p[1].path))
    print()
    print(f"Similar functions{spans} (similarity of at least "
          f"{args.min_similarity:.0%}, functions of at least "
          f"{args.min_function_tokens} tokens) ({len(pairs)}):")
    print()
    print(f"{'sim':>4} {'tokens':>9}  {'span':<5}  functions")
    for similarity, fx, fy in pairs[:args.top]:
        sizes = f"{fx.end - fx.start}/{fy.end - fy.start}"
        print(f"{similarity:4.0%} {sizes:>9}  {span(fx.path, fy.path):<5}  "
              f"{fx.name} ({fx.path}:{fx.line})")
        print(f"{'':>23}{fy.name} ({fy.path}:{fy.line})")

    print()
    print("Files with most lines in clones:")
    print()
    print(f"{'lines':>6} {'in clones':>9} {'pct':>6}  file")
    top_files = sorted((f for f in files if f.dup_lines),
                       key=lambda f: (-len(f.dup_lines), f.path))
    for f in top_files[:args.top]:
        print(f"{len(f.code_lines):6d} {len(f.dup_lines):9d} "
              f"{format_percent(len(f.dup_lines), len(f.code_lines))}  "
              f"{f.path}")


if __name__ == "__main__":
    main()
