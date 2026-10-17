"""
The tool `debasher_build`: loads a Python file that defines a program with
the SDK, finds the one Program it defines, and writes the program where
`debasher_exec` runs it, which is what Save does in the editor. The file
is named after its program, as a module is named after the program it
defines (`align_all.py` defines `Program("align_all")`), and the program
goes by default to the directory of the file, beside the files of its
processes.

Given a home directory instead, or its topology file, or nothing in a
home directory, the tool writes the generated module again from the
artifact there (see "The doors and the regeneration tool" in
doc/design_doc_webui.md), so that a program kept in a repository as its
artifact is built without the editor. With `--schema` it prints the JSON
Schema of the topology file.

The installed `debasher_build` is a launcher (sdk/python/debasher_build.sh)
that chooses the Python to run this module with, as `debasher_webui`
does, and runs it as `python -m debasher.build`.
"""

import argparse
import importlib.util
import json
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


def rebuild(home_dir: str | Path) -> Path:
    """
    Writes the generated module of the program saved in `home_dir` again
    from its artifact, and returns its path: the program is loaded and
    saved back as it is, which regenerates the module and leaves the
    artifact as it was. Raises DefinitionError when the directory holds
    no program, or one that cannot be read or that script generation
    refuses.
    """
    from api import persistence
    from api.topology import TopologyError

    home = Path(home_dir).resolve()
    try:
        program = persistence.load_program(str(home))
    except FileNotFoundError as error:
        raise DefinitionError(str(error)) from error
    except TopologyError as error:
        raise DefinitionError(f"cannot read the program in {home}: {error}") from error
    try:
        return persistence.save(str(home), program).script_path
    except (ValueError, NotImplementedError) as error:
        raise DefinitionError(str(error)) from error


def _home_of(target: str | None) -> Path | None:
    """The home directory that `target` names, for a rebuild: a directory,
    its topology file, or the current directory when there is no target;
    None for anything else, such as a description."""
    from api.topology import TOPOLOGY_FILENAME

    if target is None:
        return Path.cwd()
    path = Path(target)
    if path.is_dir():
        return path
    if path.name == TOPOLOGY_FILENAME:
        return path.parent
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="debasher_build",
        description="Writes a program described in Python with the SDK of DeBasher: the program as "
        "the web interface saves it (the topology file program.yaml, beside the files of the "
        "processes) and its generated module (<name>.sh), which debasher_exec runs and the web "
        "interface opens. Given a home directory, its program.yaml, or nothing in a home "
        "directory, writes the module again from the program saved there.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="the Python file that defines the program, named after it; or a home directory, or "
        "its program.yaml, to write the module again from the program saved there (default: the "
        "current directory)",
    )
    parser.add_argument(
        "-o", "--outdir", help="the directory to write the program into (default: that of the file)"
    )
    parser.add_argument(
        "--schema", action="store_true", help="print the JSON Schema of the topology file and exit"
    )
    args = parser.parse_args(argv)
    if args.schema:
        from api.topology import json_schema

        print(json.dumps(json_schema(), indent=2))
        return 0
    try:
        home = _home_of(args.target)
        if home is not None:
            if args.outdir:
                raise DefinitionError("-o goes with a Python file: a program saved in a directory is built there.")
            script = rebuild(home)
        else:
            program = load_program(args.target)
            home = Path(args.outdir) if args.outdir else Path(args.target).resolve().parent
            script = program.write(home)
    except DefinitionError as error:
        print(f"debasher_build: {error}", file=sys.stderr)
        return 1
    print(script)
    return 0


if __name__ == "__main__":
    sys.exit(main())
