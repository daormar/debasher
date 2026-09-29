#!/usr/bin/env python3
"""CRAP report of the Python code of a directory.

Runs a pytest suite under coverage, measures the cyclomatic complexity of
every function of the code with radon, and combines both into the CRAP score
(Change Risk Anti-Patterns) of each function:

    CRAP(f) = comp(f)^2 * (1 - cov(f))^3 + comp(f)

where comp(f) is the cyclomatic complexity of f and cov(f) the fraction of
its lines that the tests execute. A score above 30 flags a function too
complex for how little it is tested. With full coverage the score equals the
complexity, so a function whose complexity is above 30 stays above the
threshold however well it is tested: only splitting it brings it under.

Usage: crap_report.py [--top N] [--threshold T] SOURCE_DIR TEST_DIR

It needs pytest, coverage and radon (api/requirements-dev.txt), so it is run
with the Python of the virtual environment of the API. The report goes to
standard output, with the summary line of pytest. The whole output of pytest
goes to standard error only when the suite fails, so that the tracebacks some
tests print on purpose (a thread dying on bad input, reported by pytest as a
warning) do not bury the report.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

try:
    import coverage  # noqa: F401  (run below as python -m coverage)
    from radon.visitors import Class, ComplexityVisitor
except ImportError as e:
    sys.exit(f"crap_report.py: module {e.name} not found: install "
             "api/requirements-dev.txt into the Python that runs this script")

DEFAULT_THRESHOLD = 30


def crap_score(complexity, coverage_fraction):
    return complexity ** 2 * (1 - coverage_fraction) ** 3 + complexity


def run_coverage(source_dir, test_dir, work_dir):
    """Run the pytest suite of test_dir under coverage, measuring the code
    of source_dir, and return pytest's exit status, its summary line and
    the coverage data as a dict from absolute file path to its "files" entry
    of the JSON report of coverage.

    The Python processes that the tests start are measured too: part of the
    code of the engine only runs in them.
    """
    root = os.path.dirname(source_dir)
    rcfile = os.path.join(work_dir, "coveragerc")
    with open(rcfile, "w") as f:
        f.write("[run]\n"
                f"source = {source_dir}\n"
                f"omit = {source_dir}/.*/*\n"
                f"data_file = {os.path.join(work_dir, '.coverage')}\n"
                "patch = subprocess\n"
                "parallel = true\n")
    cov = [sys.executable, "-m", "coverage"]
    pytest = subprocess.run(
        cov + ["run", f"--rcfile={rcfile}", "-m", "pytest", "-q", test_dir],
        cwd=root, capture_output=True, text=True)
    if pytest.returncode != 0:
        sys.stderr.write(pytest.stdout + pytest.stderr)
    # The summary is the last line pytest writes to standard output (coverage
    # writes its own warnings to standard error)
    lines = pytest.stdout.strip().splitlines()
    summary = lines[-1].strip("= ") if lines else ""
    json_path = os.path.join(work_dir, "coverage.json")
    subprocess.check_call(cov + ["combine", f"--rcfile={rcfile}", "-q"],
                          cwd=root, stdout=sys.stderr)
    subprocess.check_call(
        cov + ["json", f"--rcfile={rcfile}", "-q", "-o", json_path],
        cwd=root, stdout=sys.stderr)
    with open(json_path) as f:
        files = json.load(f)["files"]
    return (pytest.returncode, summary,
            {os.path.abspath(os.path.join(root, path)): data
             for path, data in files.items()})


def python_files(source_dir):
    for dirpath, dirnames, filenames in os.walk(source_dir):
        # Hidden directories (a virtual environment, for one) and
        # __pycache__ hold no code of the directory
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def functions(blocks, prefix=""):
    """Yield (qualified name, block) for every function and method under the
    radon blocks, closures included, each as a function of its own. The
    blocks are the top level ones of a ComplexityVisitor (cc_visit would
    list every method twice: alone and inside its class)."""
    for b in blocks:
        name = prefix + b.name
        if isinstance(b, Class):
            yield from functions(b.methods, name + ".")
            yield from functions(b.inner_classes, name + ".")
        else:
            yield name, b
            yield from functions(b.closures, name + ".")


def own_lines(block):
    """Lines of a function minus those of its closures, which radon also
    leaves out of its complexity."""
    lines = set(range(block.lineno, block.endline + 1))
    for c in block.closures:
        lines -= set(range(c.lineno, c.endline + 1))
    return lines


def crap_rows(source_dir, coverage_files):
    """Return (CRAP, complexity, coverage fraction, name, file, line) for
    every function of the code of source_dir, highest score first. A file
    the coverage data does not know counts as never executed."""
    rows = []
    for path in python_files(source_dir):
        data = coverage_files.get(path)
        executed = set(data["executed_lines"]) if data else set()
        missing = set(data["missing_lines"]) if data else None
        with open(path) as f:
            visitor = ComplexityVisitor.from_code(f.read())
        for name, block in functions(visitor.functions + visitor.classes):
            lines = own_lines(block)
            if missing is None:
                fraction = 0.0
            else:
                run = len(lines & executed)
                total = run + len(lines & missing)
                fraction = run / total if total else 0.0
            rows.append((crap_score(block.complexity, fraction),
                         block.complexity, fraction, name, path,
                         block.lineno))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="CRAP report of the Python code of a directory.")
    parser.add_argument("source_dir", help="code to measure, e.g. api")
    parser.add_argument("test_dir", help="pytest suite to run, e.g. test/api")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="score above which a function is flagged "
                        f"(default {DEFAULT_THRESHOLD})")
    parser.add_argument("--top", type=int,
                        help="list the N highest scores instead of the "
                        "functions above the threshold")
    args = parser.parse_args()
    source_dir = os.path.abspath(args.source_dir)
    test_dir = os.path.abspath(args.test_dir)
    root = os.path.dirname(source_dir)

    with tempfile.TemporaryDirectory(prefix="crap_report.") as work_dir:
        status, summary, coverage_files = run_coverage(source_dir, test_dir,
                                                       work_dir)
    rows = crap_rows(source_dir, coverage_files)
    flagged = [r for r in rows if r[0] > args.threshold]
    listed = rows[:args.top] if args.top is not None else flagged

    if os.path.commonpath([test_dir, root]) == root:
        test_dir = os.path.relpath(test_dir, root)
    print(f"CRAP report of {os.path.relpath(source_dir, root)} "
          f"(tests: {test_dir})")
    print(f"pytest: {summary}")
    if status != 0:
        print(f"WARNING: pytest exited with status {status}, so the coverage "
              "below may be lower than the real one")
    print(f"{len(rows)} functions, {len(flagged)} above {args.threshold:g}")
    if listed:
        print()
        print(f"{'CRAP':>7} {'CC':>4} {'cov':>5}  function")
        for score, complexity, fraction, name, path, line in listed:
            print(f"{score:7.1f} {complexity:4d} {fraction * 100:4.0f}%  "
                  f"{name}  ({os.path.relpath(path, root)}:{line})")


if __name__ == "__main__":
    main()
