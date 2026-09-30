#!/usr/bin/env python3
"""Change coupling of the code: the files that change together.

Two files that keep changing in the same commits depend on each other,
whether or not the code says so. For every pair of source files this
counts:

- shared: the commits of the period that changed both (following renames);
- degree: shared over the mean of the commits of each file, as a
  percentage: 100 means that neither file ever changes without the other.

Where the two files lie tells how to read a pair. Two files of the same
directory changing together is what a cohesive module looks like; two files
of different parts of the code (engine, api, frontend) changing together is
a responsibility spread over several places, or an implicit contract
between them. Each pair is marked with its span:

- dir: both files are in the same directory;
- part: same part of the code (engine, api, frontend), different directory;
- cross: different parts of the code;
- test: a test and a file that is not one (only with --include-tests).

The report ends with the sum of coupling of each file: for every commit
that changed it, how many other files of the report the commit also
changed. A file with a high sum drags other changes with it wherever they
are; crossed with hotspots.py, it tells whether a hotspot also spreads its
changes.

Usage: coupling.py [--since DATE] [--top N] [--min-revs N] [--min-shared N]
                   [--min-degree PCT] [--max-changeset N] [--span SPAN]
                   [--include-tests] [PATH ...]

PATH is a directory or file of the repository (default: engine, api and
frontend/src). --since takes whatever `git log --since` accepts (default:
1 year ago). Commits that changed more than --max-changeset files of the
report are left out: a mass rename or reformatting couples everything with
everything and says nothing. --span, which may be repeated, lists only the
pairs of that span (for instance --span cross for the pairs across parts).
"""

import argparse
import os
import subprocess
import sys
from collections import Counter
from itertools import combinations

# Importing hotspots.py would leave its bytecode next to it, in the tree
sys.dont_write_bytecode = True
from hotspots import DEFAULT_PATHS, commits_by_file, git, is_test, \
    source_files

SPANS = ["dir", "part", "cross", "test"]

# Parts of the code, for the span of a pair: a file belongs to the first
# one its path starts with
PARTS = ["engine/", "api/", "frontend/", "test/", "data/"]


def part(path):
    for p in PARTS:
        if path.startswith(p):
            return p
    return path.split("/")[0]


def span(a, b):
    """How far apart the two files of a pair lie."""
    if is_test(a) != is_test(b):
        return "test"
    if os.path.dirname(a) == os.path.dirname(b):
        return "dir"
    if part(a) == part(b):
        return "part"
    return "cross"


def coupling(commits, files, max_changeset):
    """Return the commits of each file, the commits shared by each pair
    and the sum of coupling of each file, counting only the files given
    and the commits that changed at most max_changeset of them."""
    revs = Counter()
    shared = Counter()
    soc = Counter()
    for changed in commits:
        changed = sorted(changed & files)
        if not changed or len(changed) > max_changeset:
            continue
        revs.update(changed)
        shared.update(combinations(changed, 2))
        for f in changed:
            soc[f] += len(changed) - 1
    return revs, shared, soc


def main():
    parser = argparse.ArgumentParser(
        description="Files that change together.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help="directories or files of the repository "
                        f"(default: {' '.join(DEFAULT_PATHS)})")
    parser.add_argument("--since", default="1 year ago",
                        help="start of the period, as git log --since takes "
                        "it (default: 1 year ago)")
    parser.add_argument("--top", type=int, default=20,
                        help="how many pairs and files to list (default 20)")
    parser.add_argument("--min-revs", type=int, default=5,
                        help="leave out the files changed by fewer commits "
                        "(default 5)")
    parser.add_argument("--min-shared", type=int, default=5,
                        help="leave out the pairs that shared fewer commits "
                        "(default 5)")
    parser.add_argument("--min-degree", type=float, default=30,
                        help="leave out the pairs with a lower degree, in "
                        "percent (default 30)")
    parser.add_argument("--max-changeset", type=int, default=30,
                        help="leave out the commits that changed more files "
                        "of the report (default 30)")
    parser.add_argument("--span", action="append", choices=SPANS,
                        help="list only the pairs of this span; may be "
                        "repeated (default: all)")
    parser.add_argument("--include-tests", action="store_true",
                        help="also couple the tests")
    parser.add_argument("--root", default=".",
                        help="the repository (default: the current directory)")
    args = parser.parse_args()

    try:
        root = git(args.root, "rev-parse", "--show-toplevel").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("coupling.py: not in a git work tree: the change history "
                 "comes from git")
    files = set(source_files(root, args.paths, args.include_tests))
    commits = commits_by_file(root, args.since)
    revs, shared, soc = coupling(commits, files, args.max_changeset)
    total_commits = sum(1 for changed in commits
                        if 0 < len(changed & files) <= args.max_changeset)

    rows = []
    for (a, b), n in shared.items():
        if n < args.min_shared or min(revs[a], revs[b]) < args.min_revs:
            continue
        degree = 100 * n / ((revs[a] + revs[b]) / 2)
        sp = span(a, b)
        if degree >= args.min_degree and (not args.span or sp in args.span):
            rows.append((degree, n, sp, a, b))
    rows.sort(key=lambda r: (-r[0], -r[1], r[3], r[4]))

    print(f"Change coupling of {' '.join(args.paths)} since {args.since}: "
          f"{len(files)} files, {total_commits} commits (those that changed "
          f"at most {args.max_changeset} of the files)")
    print()
    spans = f" of span {', '.join(args.span)}" if args.span else ""
    print(f"Pairs{spans} with at least {args.min_shared} shared commits and "
          f"a degree of at least {args.min_degree:g}% ({len(rows)}):")
    print()
    print(f"{'degree':>6} {'shared':>6} {'revs':>9}  {'span':<5}  files")
    for degree, n, sp, a, b in rows[:args.top]:
        pair_revs = f"{revs[a]}/{revs[b]}"
        print(f"{degree:5.0f}% {n:6d} {pair_revs:>9}  {sp:<5}  {a}")
        print(f"{'':>30}  {b}")
    print()
    print("Sum of coupling:")
    print()
    print(f"{'soc':>6} {'commits':>7}  file")
    top_soc = sorted(soc.items(), key=lambda kv: (-kv[1], kv[0]))
    for f, s in top_soc[:args.top]:
        print(f"{s:6d} {revs[f]:7d}  {f}")


if __name__ == "__main__":
    main()
