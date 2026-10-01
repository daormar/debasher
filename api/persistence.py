import fcntl
import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import script_generation
from .models import Program

# Directory (inside the user-chosen output directory) where the program
# is serialized. Hidden, following the convention of tool directories
# like .git.
METADATA_DIRNAME = ".debasher"

PROGRAM_FILENAME = "program.json"

# The lock file that a save holds while it compares and writes the revision
# of the program metadata (see save).
LOCK_FILENAME = "program.lock"


def is_reserved_name(name: str) -> bool:
    """
    True for a file/directory name DeBasher itself manages inside a
    program's home directory: the hidden .debasher metadata dir, a
    dot-prefixed engine file (.debasher_webui_run.log, .conda,
    .sched_opts, .exec_context.sh, ...),
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


def read_raw_metadata(home_dir: str) -> dict | None:
    """
    The program metadata in `home_dir` as plain JSON, so that metadata the
    program model would refuse can still be read, or None when it is absent
    or is not a JSON object.
    """
    metadata_path = Path(home_dir).expanduser() / METADATA_DIRNAME / PROGRAM_FILENAME
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return None
    return metadata if isinstance(metadata, dict) else None


def delete_stale_script(output_dir: str, new_name: str) -> None:
    """
    If a program was already saved to `output_dir` under a different
    name (the program can be renamed in the editor after being saved),
    remove that now-orphaned <old_name>.sh before writing the new one,
    otherwise renaming a program leaves a stale script sitting alongside
    the current one on every subsequent save.

    Called by save before it replaces the metadata file, since that's the
    only record of what the program used to be named. A missing or
    unreadable metadata file just means there's no prior save to clean up
    after, not an error.
    """
    old_name = (read_raw_metadata(output_dir) or {}).get("name")

    if not old_name or old_name == new_name:
        return

    stale_script_path = Path(output_dir).expanduser() / f"{old_name}.sh"
    if stale_script_path.is_file():
        stale_script_path.unlink()


def copy_ext_alias_files(program: Program, output_dir: str) -> None:
    """
    Copies each process's, and each sequential process's, external-alias
    script (AdditionalSpecs.externalAlias, see AdditionalSpecsEditor.tsx
    and script_generation.py's _additional_specs_str, which writes it into
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

    # A sequential process may have an external alias too
    for process in [*program.processes, *program.seqProcesses]:
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


class RevisionConflict(Exception):
    """
    A save that names a revision of the program metadata other than the one
    the home directory holds: someone else saved the program since it was
    loaded. `revision` is the one it holds.
    """

    def __init__(self, revision: int):
        super().__init__(
            "The program changed on disk since it was loaded (another tab or "
            "another client of the backend saved it). Load it again to see "
            "those changes: saving now would discard them."
        )
        self.revision = revision


def _saved_revision(home_dir: str) -> int | None:
    """
    The revision of the program metadata in `home_dir`, 0 for metadata that
    records none or cannot be read, or None when there is no program
    metadata there.
    """
    if not (Path(home_dir).expanduser() / METADATA_DIRNAME / PROGRAM_FILENAME).is_file():
        return None
    revision = (read_raw_metadata(home_dir) or {}).get("revision", 0)
    return revision if isinstance(revision, int) else 0


@contextmanager
def _metadata_lock(home_dir: Path):
    metadata_dir = home_dir / METADATA_DIRNAME
    metadata_dir.mkdir(parents=True, exist_ok=True)
    with open(metadata_dir / LOCK_FILENAME, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _same_metadata(program_path: Path, program: Program) -> bool:
    """
    Whether the program metadata at `program_path` holds `program`, apart
    from its revision and its home directory, which loading replaces.
    """
    try:
        saved = Program.model_validate_json(program_path.read_text())
    except (OSError, ValueError):
        return False
    ignored = {"revision", "homeDir"}
    return saved.model_dump(exclude=ignored) == program.model_dump(exclude=ignored)


@dataclass
class SavedProgram:
    program_path: Path
    script_path: Path
    revision: int


def save(home_dir: str, program: Program) -> SavedProgram:
    """
    Save `program` into `home_dir`: its program metadata with the next
    revision, its generated script, the files of its relative external
    aliases (see copy_ext_alias_files), and, when it was renamed, the
    removal of the script with its old name.

    The script is generated first, so that a program that script generation
    refuses (ValueError, NotImplementedError) leaves the home directory as it
    was. A save that would leave the program metadata as it is (apart from
    its revision and home directory) keeps its revision, whatever revision
    the program names: it overwrites nobody's work. Any other save into the
    program's own home directory is refused with RevisionConflict unless the
    program metadata there holds the revision the program was loaded with
    (`program.revision`); a save into another directory replaces
    what is there, as a first save does. The comparison and the writes happen
    under a lock on the program metadata, so that two saves arriving together
    cannot both pass the comparison.
    """
    script = script_generation.generate_script(program)

    home = Path(home_dir).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    program_path = home / METADATA_DIRNAME / PROGRAM_FILENAME

    with _metadata_lock(home):
        current = _saved_revision(home_dir)

        if current is not None and _same_metadata(program_path, program):
            revision = current
        else:
            if current is not None and same_dir(home_dir, program.homeDir) and current != program.revision:
                raise RevisionConflict(current)

            # Before the metadata is replaced, since it is the only record
            # of the old name.
            delete_stale_script(home_dir, program.name)

            revision = (current or 0) + 1
            saved = program.model_copy(update={"revision": revision, "homeDir": str(home)})
            temp_path = program_path.with_suffix(".json.tmp")
            temp_path.write_text(saved.model_dump_json(indent=2))
            os.replace(temp_path, program_path)

        script_path = home / f"{program.name}.sh"
        script_path.write_text(script)

    copy_ext_alias_files(program, home_dir)

    return SavedProgram(program_path=program_path, script_path=script_path, revision=revision)

