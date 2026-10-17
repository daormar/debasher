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

"""
debasher_run_py_func.py

Runs a Python function of a process, kept in a file of its own, for the
functions of the engine that call it (debasher::tasks_from_file,
debasher::num_tasks_from_file and debasher::skip_from_file), and prints
what it returns in the form that they read:

    debasher_run_py_func array <file> <process> <process outdir> -- <args>
    debasher_run_py_func count <file> <process> <process outdir> -- <args>
    debasher_run_py_func skip <file> <process> -- <args>

In the modes array and count, the file defines tasks(run), and <args>
is the command line of the run: array prints the elements that the
function returns, each followed by a NUL character, and count prints the
number of tasks that it returns. In the mode skip, the file defines
skip(task), and <args> are the options of the task: nothing is printed,
and the exit status is 0 when the function returns True, the task being
skipped, and 1 when it returns False.

Any error (a file that cannot be loaded, a function that is missing,
raises or returns something of the wrong kind) is reported on the
standard error, with the traceback of the function when it raised, and
gives the exit status 2. What the file prints on its standard output
while it is loaded and called goes to the standard error, so that it
never mixes with what the engine reads.
"""

import importlib.util
import os
import re
import sys
import traceback
from collections.abc import Iterable, Mapping

ERROR_STATUS = 2

# The rule of the engine for an argument that is an option rather than a
# value (debasher::_str_is_option)
_OPTION_RE = re.compile(r"^--?[A-Za-z_]")

# The prefix of the name of a value descriptor
# (DEBASHER_VALUE_DESCRIPTOR_NAME_PREFIX)
_VALUE_DESCRIPTOR_PREFIX = ".__VAL_DESCRIPTOR__"


class FuncError(Exception):
    """An error of the function or of its file, reported with its message."""


class Options:
    """
    A list of options as the engine gives them to a method: a label
    followed by its value, or a flag alone. It reads them as the engine
    does (read_opt_value_from_func_args and read_flag_from_func_args).
    """

    def __init__(self, args):
        self.args = list(args)

    def value(self, label, default=None):
        """The value given to the option `label`, or `default` when the
        option is not given or is given without a value."""
        for i, arg in enumerate(self.args):
            if arg == label:
                if i + 1 < len(self.args) and not _OPTION_RE.match(self.args[i + 1]):
                    return self.args[i + 1]
                return default
        return default

    def given(self, label):
        """Whether the option or flag `label` is given."""
        return label in self.args


class Run(Options):
    """What tasks(run) receives: the command line of the run, the name of
    the process and its process output directory."""

    def __init__(self, args, process, outdir):
        super().__init__(args)
        self.process = process
        self.outdir = outdir


class Task(Options):
    """What skip(task) receives: the options of the task, and the name of
    its process."""

    def __init__(self, args, process):
        super().__init__(args)
        self.process = process

    def value(self, label, default=None):
        """The value given to the option `label`, as for any options, except
        that the value of an input option that is a value descriptor is
        the value that the descriptor holds, as read_opt_value_from_func_args
        reads it."""
        value = super().value(label, default)
        if (
            isinstance(value, str)
            and os.path.isabs(value)
            and os.path.basename(value).startswith(_VALUE_DESCRIPTOR_PREFIX)
            and not (label.startswith("-out") or label.startswith("--out"))
        ):
            with open(value, encoding="utf-8") as desc:
                # A command substitution drops the newlines that end it
                return desc.read().rstrip("\n")
        return value


def load_func(path, funcname):
    """The function `funcname` of the Python file `path`, which is loaded
    with its own directory first on sys.path, so that it can import the
    files beside it."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    modname = "_debasher_py_func_" + re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0])
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise FuncError(f"{path} cannot be loaded as a Python file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, funcname, None)
    if not callable(func):
        raise FuncError(f"{path} defines no function {funcname}")
    return func


def array_elements(result, path):
    """The elements of an array, as the text of each, from what tasks(run)
    returned."""
    if isinstance(result, (str, bytes, Mapping)) or not isinstance(result, Iterable):
        raise FuncError(
            f"tasks() of {path} returned {type(result).__name__}, not a list of the elements of the array"
        )
    elements = []
    for i, element in enumerate(result):
        if isinstance(element, bool) or not isinstance(element, (str, int, float, os.PathLike)):
            raise FuncError(
                f"tasks() of {path} returned an element {i} of type {type(element).__name__}: an element is "
                "a string, a number or a path"
            )
        text = os.fspath(element) if isinstance(element, os.PathLike) else str(element)
        if "\0" in text:
            raise FuncError(f"tasks() of {path} returned an element {i} with a NUL character")
        elements.append(text)
    return elements


def num_tasks(result, path):
    """The number of tasks of an option generator, from what tasks(run)
    returned."""
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise FuncError(f"tasks() of {path} returned {result!r}, not a number of tasks (an integer, 0 or more)")
    return result


def skip_decision(result, path):
    """Whether the task is skipped, from what skip(task) returned."""
    if not isinstance(result, bool):
        raise FuncError(f"skip() of {path} returned {result!r}, not True or False")
    return result


def run(mode, path, process, outdir, args):
    """Calls the function of the file for `mode` and returns what it
    returned, checked: a list of texts, a number of tasks or a decision."""
    if mode == "skip":
        result = load_func(path, "skip")(Task(args, process))
        return skip_decision(result, path)
    result = load_func(path, "tasks")(Run(args, process, outdir))
    if mode == "array":
        return array_elements(result, path)
    return num_tasks(result, path)


def parse_args(argv):
    """The mode, file, process, process output directory and arguments of
    the command line; raises FuncError when it is not of the form above."""
    if "--" not in argv:
        raise FuncError("usage: debasher_run_py_func <array|count|skip> <file> <process> [<outdir>] -- <args>")
    sep = argv.index("--")
    head, args = argv[:sep], argv[sep + 1:]
    if len(head) < 1 or head[0] not in ("array", "count", "skip"):
        raise FuncError("the mode is one of array, count and skip")
    expected = 3 if head[0] == "skip" else 4
    if len(head) != expected:
        raise FuncError(f"the mode {head[0]} takes {expected - 1} arguments before --")
    mode, path, process = head[0], head[1], head[2]
    outdir = head[3] if mode != "skip" else ""
    return mode, path, process, outdir, args


def main(argv):
    try:
        mode, path, process, outdir, args = parse_args(argv)
    except FuncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return ERROR_STATUS

    # What the file prints goes to the standard error: the standard output
    # carries the result only
    sys.stdout.flush()
    result_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        result = run(mode, path, process, outdir, args)
    except FuncError as exc:
        print(f"Error: {exc} (process {process})", file=sys.stderr)
        return ERROR_STATUS
    except BaseException as exc:  # an error of the user's code, of any kind
        if isinstance(exc, SystemExit) and exc.code in (0, None):
            print(f"Error: {path} exited instead of returning (process {process})", file=sys.stderr)
        else:
            # The traceback starts at the code of the user, leaving out
            # the frames of this tool that lead to it
            tb = exc.__traceback__
            while tb is not None and tb.tb_frame.f_code.co_filename == __file__:
                tb = tb.tb_next
            traceback.print_exception(type(exc), exc, tb)
            print(f"Error: the Python function of {path} failed (process {process})", file=sys.stderr)
        return ERROR_STATUS
    finally:
        sys.stdout.flush()
        os.dup2(result_fd, 1)
        os.close(result_fd)

    if mode == "skip":
        return 0 if result else 1
    with os.fdopen(os.dup(1), "w", encoding="utf-8", newline="") as out:
        if mode == "array":
            out.write("".join(element + "\0" for element in result))
        else:
            out.write(f"{result}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
