#!/usr/bin/env python3
"""Hotspots of the code: the files that are both complex and often changed.

A complex file that nobody touches is a latent risk; a complex file that
changes all the time is where bugs concentrate and where a refactoring pays
back most. For every source file this crosses:

- commits: how many commits changed it in the period (following renames);
- complexity: its indentation complexity, the sum over its lines of code of
  their indentation level (a level being the indentation step of the
  language in this repo: 4 spaces in Bash and Python, 2 in TypeScript, or a
  tab). It does not depend on the language, so Bash, Python and TypeScript
  are ranked together, and it grows with both size and nesting;

into a score, commits times complexity. The tool is at the level of files;
the complexity of the functions of a hotspot is given by bash_complexity.py,
crap_report.py and the report of the frontend.

Usage: hotspots.py [--since DATE] [--top N] [--include-tests] [PATH ...]

PATH is a directory or file of the repository (default: engine, api and
frontend/src). --since takes whatever `git log --since` accepts (default:
1 year ago). Tests (test/, *.test.ts and *.test.tsx) are left out unless
--include-tests is given.
"""

import argparse
import os
import re
import subprocess
import sys
from collections import Counter

# Indentation step of each language in this repo
INDENT_STEP = {".sh": 4, ".py": 4, ".ts": 2, ".tsx": 2, ".mjs": 2}
EXTENSIONS = tuple(INDENT_STEP)
DEFAULT_PATHS = ["engine", "api", "frontend/src"]
COMMENT = re.compile(r"^\s*(#|//|/\*|\*)")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, text=True).stdout


def is_test(path):
    return (path.startswith("test/") or ".test." in os.path.basename(path))


def source_files(root, paths, include_tests):
    """Tracked source files under paths, relative to the root."""
    files = git(root, "ls-files", "--", *paths).splitlines()
    return [f for f in files if f.endswith(EXTENSIONS)
            and (include_tests or not is_test(f))]


def commits_by_file(root, since):
    """The files each commit of the period changed, newest commit first,
    every file under its current name: a file renamed in the period also
    gets the commits of its old names. The
    log is that of the whole repository, since the old names may lie
    outside the paths of the report (engine/ was utils/ once). Merges are
    left out: their changes are already counted in the commits merged."""
    log = git(root, "log", f"--since={since}", "--no-merges", "-M",
              "--name-status", "--format=%x00")
    commits = []
    current = {}  # name at some commit -> current name
    # Newest first: a rename maps the old name to what the new one is now
    for commit in log.split("\0")[1:]:
        changed = set()
        for line in commit.strip().splitlines():
            fields = line.split("\t")
            if fields[0].startswith("R"):
                old, new = fields[1], fields[2]
                current[old] = current.get(new, new)
                changed.add(current[old])
            elif len(fields) >= 2:
                changed.add(current.get(fields[1], fields[1]))
        commits.append(changed)
    return commits


def indentation_complexity(path):
    """Return the indentation complexity of a file and its lines of code
    (blank lines and comments left out)."""
    step = INDENT_STEP[os.path.splitext(path)[1]]
    complexity = 0.0
    code_lines = 0
    with open(path, errors="replace") as f:
        for line in f:
            if not line.strip() or COMMENT.match(line):
                continue
            leading = line[:len(line) - len(line.lstrip(" \t"))]
            complexity += leading.count("\t") + leading.count(" ") / step
            code_lines += 1
    return complexity, code_lines


def main():
    parser = argparse.ArgumentParser(
        description="Files that are both complex and often changed.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help="directories or files of the repository "
                        f"(default: {' '.join(DEFAULT_PATHS)})")
    parser.add_argument("--since", default="1 year ago",
                        help="start of the period, as git log --since takes "
                        "it (default: 1 year ago)")
    parser.add_argument("--top", type=int, default=20,
                        help="how many files to list (default 20)")
    parser.add_argument("--include-tests", action="store_true",
                        help="also rank the tests")
    parser.add_argument("--root", default=".",
                        help="the repository (default: the current directory)")
    args = parser.parse_args()

    try:
        root = git(args.root, "rev-parse", "--show-toplevel").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("hotspots.py: not in a git work tree: the change history "
                 "comes from git")
    files = source_files(root, args.paths, args.include_tests)
    commits = commits_by_file(root, args.since)
    counts = Counter(f for changed in commits for f in changed)
    total_commits = sum(1 for changed in commits if changed & set(files))
    rows = []
    for f in files:
        complexity, code_lines = indentation_complexity(os.path.join(root, f))
        rows.append((counts[f] * complexity, counts[f], code_lines,
                     complexity, f))
    rows.sort(reverse=True)

    print(f"Hotspots of {' '.join(args.paths)} since {args.since}: "
          f"{len(rows)} files, {total_commits} commits")
    print()
    print(f"{'score':>8} {'commits':>7} {'lines':>6} {'indent':>7}  file")
    for score, commits, code_lines, complexity, f in rows[:args.top]:
        print(f"{score:8.0f} {commits:7d} {code_lines:6d} {complexity:7.0f}"
              f"  {f}")


if __name__ == "__main__":
    main()
