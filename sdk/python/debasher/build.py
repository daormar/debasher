"""
The tool `debasher_build`: loads a Python file that defines a program with
the SDK, finds the one Program it defines, and writes the program where
`debasher_exec` runs it, which is what Save does in the editor. The file
is named after its program, as a module is named after the program it
defines (`align_all.py` defines `Program("align_all")`), and the program
goes by default to the directory of the file, beside the files of its
processes.

The installed `debasher_build` is a launcher (sdk/python/debasher_build.sh)
that chooses the Python to run this module with, as `debasher_webui`
does, and runs it as `python -m debasher.build`.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from .errors import DefinitionError
from .program import Program


def load_program(path: str | Path) -> Program:
    """
    The Program that the Python file at `path` defines: the file is run as
    a module, with its directory on `sys.path` so that it can import files
    beside it, and the one Program among its global names is returned.
    Raises DefinitionError when the file defines no Program or several,
    or one whose name is not the name of the file.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise DefinitionError(f"{path} does not exist.")
    if path.suffix != ".py":
        raise DefinitionError(f"{path.name} is not a Python file.")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    programs = [value for value in vars(module).values() if isinstance(value, Program)]
    if not programs:
        raise DefinitionError(f"{path.name} defines no Program.")
    if len(programs) > 1:
        names = ", ".join(program.name for program in programs)
        raise DefinitionError(f"{path.name} defines more than one Program ({names}): a file defines one.")
    program = programs[0]
    if program.name != path.stem:
        raise DefinitionError(
            f'{path.name} defines Program("{program.name}"): the file is named after its program, '
            f"so rename one of them ({program.name}.py, or Program(\"{path.stem}\"))."
        )
    return program


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="debasher_build",
        description="Writes a program described in Python with the SDK of DeBasher: its program "
        "metadata (.debasher/program.json) and its generated module (<name>.sh), which "
        "debasher_exec runs and the web interface opens.",
    )
    parser.add_argument("file", help="the Python file that defines the program, named after it")
    parser.add_argument(
        "-o", "--outdir", help="the directory to write the program into (default: that of the file)"
    )
    args = parser.parse_args(argv)
    try:
        program = load_program(args.file)
        home = Path(args.outdir) if args.outdir else Path(args.file).resolve().parent
        script = program.write(home)
    except DefinitionError as error:
        print(f"debasher_build: {error}", file=sys.stderr)
        return 1
    print(script)
    return 0


if __name__ == "__main__":
    sys.exit(main())
