import json
import shutil

from pathlib import Path

from . import script_generation
from .models import Program

# Directory (inside the user-chosen output directory) where the program
# is serialized. Hidden, following the convention of tool directories
# like .git.
METADATA_DIRNAME = ".debasher"

PROGRAM_FILENAME = "program.json"


def is_reserved_name(name: str) -> bool:
    """
    True for a file/directory name DeBasher itself manages inside a
    program's home directory: the hidden .debasher metadata dir, a
    dot-prefixed engine file (.debasher_webui_run.log, .conda,
    .sched_opts, .deblib_vars_and_funcs.sh, .mod_vars_and_funcs.sh, ...),
    a __dunder__-wrapped engine directory (__exec__, __graphs__,
    __fifos__), or command_line.sh, the one engine-written name that
    follows neither convention.

    This is a rule, not a hardcoded list, so it also covers any future
    engine-internal file added under the same naming convention. The
    program-files browser (see routers/program_files.py) must never
    show, descend into, or write to anything this matches.
    """
    return (
        name.startswith(".")
        or (name.startswith("__") and name.endswith("__"))
        or name == "command_line.sh"
    )


def same_dir(a: str, b: str) -> bool:
    """
    True when both non-blank paths resolve to the same directory.

    Blank-safe: a blank on either side is never considered a match, so
    two not-yet-set directories don't trip a same-dir guard.
    """
    if not a.strip() or not b.strip():
        return False

    return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()


def delete_stale_script(output_dir: str, new_name: str) -> None:
    """
    If a program was already saved to `output_dir` under a different
    name (the program can be renamed in the editor after being saved),
    remove that now-orphaned <old_name>.sh before writing the new one,
    otherwise renaming a program leaves a stale script sitting alongside
    the current one on every subsequent save.

    Must be called before save_program overwrites the metadata file,
    since that's the only record of what the program used to be named.
    A missing or unreadable metadata file just means there's no prior
    save to clean up after, not an error.
    """
    metadata_path = Path(output_dir).expanduser() / METADATA_DIRNAME / PROGRAM_FILENAME

    if not metadata_path.is_file():
        return

    try:
        old_name = json.loads(metadata_path.read_text()).get("name")
    except (OSError, ValueError):
        return

    if not old_name or old_name == new_name:
        return

    stale_script_path = Path(output_dir).expanduser() / f"{old_name}.sh"
    if stale_script_path.is_file():
        stale_script_path.unlink()


def copy_ext_alias_files(program: Program, output_dir: str) -> None:
    """
    Copies each process's external-alias script (AdditionalSpecs.
    externalAlias, see AdditionalSpecsEditor.tsx and
    script_generation.py's _additional_specs_str, which writes it into
    the generated .sh as "ext_alias=<path>") from where `program` was
    originally imported from (program.sourceDir) into `output_dir`,
    preserving the same relative path.

    This matters because the engine resolves a relative ext_alias
    against the directory of the .sh that declares it (see
    debasher::_add_debasher_ext_alias_process in
    engine/debasher_lib_programs.sh), not against where it was
    originally imported from, so without this, saving an imported
    program anywhere other than its original directory would produce a
    script whose ext_alias process can't find its file.

    A missing source file, an absolute externalAlias (already a fixed,
    non-portable path per the engine's own warning when it's used), a
    program with no recorded sourceDir (not imported), or source and
    destination resolving to the same file (saving back into the
    program's own original directory) are all silently skipped rather
    than treated as an error: Save should never fail just because an
    ext-alias file can't be located or copied.
    """
    if not program.sourceDir:
        return

    source_root = Path(program.sourceDir).expanduser()
    resolved_output_dir = Path(output_dir).expanduser()

    for process in program.processes:
        external_alias = process.additionalSpecs.externalAlias
        if not external_alias or Path(external_alias).is_absolute():
            continue

        source_file = source_root / external_alias
        dest_file = resolved_output_dir / external_alias

        try:
            if not source_file.is_file() or source_file.resolve() == dest_file.resolve():
                continue
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, dest_file)
        except OSError:
            continue


def save_program(output_dir: str, program: Program) -> Path:
    """
    Serialize `program` into <output_dir>/.debasher/program.json,
    creating `output_dir` (and the hidden directory) if needed.

    Returns the path to the written file.
    """
    resolved_output_dir = Path(output_dir).expanduser()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    metadata_dir = resolved_output_dir / METADATA_DIRNAME
    metadata_dir.mkdir(parents=True, exist_ok=True)

    program_path = metadata_dir / PROGRAM_FILENAME
    program_path.write_text(program.model_dump_json(indent=2))

    return program_path


def save_script(output_dir: str, program: Program) -> Path:
    """
    Generate `program`'s Bash script via `script_generation.generate_script`
    and write it to <output_dir>/<program.name>.sh, creating `output_dir`
    if needed.

    Returns the path to the written file.
    """
    resolved_output_dir = Path(output_dir).expanduser()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    script_path = resolved_output_dir / f"{program.name}.sh"
    script_path.write_text(script_generation.generate_script(program))

    return script_path


def load_program(input_dir: str) -> Program:
    """
    Read and deserialize <input_dir>/.debasher/program.json.

    The program's home directory is the directory it is loaded from, as
    an absolute path, whatever the metadata recorded when it was saved:
    a home directory that was copied or moved, or one shipped with
    DeBasher (data/webui_programs), goes on being saved and run where it
    now is.

    Raises FileNotFoundError if that file doesn't exist.
    """
    home_dir = Path(input_dir).expanduser().resolve()
    program_path = home_dir / METADATA_DIRNAME / PROGRAM_FILENAME

    if not program_path.is_file():
        raise FileNotFoundError(
            f"No program found at {program_path} "
            f"(expected a {METADATA_DIRNAME}/{PROGRAM_FILENAME} file in the given directory)"
        )

    program = Program.model_validate_json(program_path.read_text())
    program.homeDir = str(home_dir)
    return program


def resolve_script_path(script_path: str) -> Path:
    """
    Resolve `script_path` to an existing file.

    Raises FileNotFoundError if it doesn't exist.
    """
    resolved_script_path = Path(script_path).expanduser()

    if not resolved_script_path.is_file():
        raise FileNotFoundError(f"No such file: {resolved_script_path}")

    return resolved_script_path
