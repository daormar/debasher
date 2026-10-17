"""
The program on disk: its artifact in the home directory (see "The artifact:
the topology file and the process files" in doc/design_doc_webui.md), the
topology file program.yaml and the files it names, with the generated script
beside them; the local state of the editor under .debasher/; and the
program metadata of before the artifact, .debasher/program.json, which is
read when a home directory holds no topology file and replaced by the
artifact at the next save.
"""

import fcntl
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from . import script_generation, topology
from .models import Program
from .topology import TOPOLOGY_FILENAME, Topology, TopologyError

# Directory (inside the home directory) of what belongs to the editor on
# this machine and not to the program: the lock and the local state. Hidden,
# following the convention of tool directories like .git.
METADATA_DIRNAME = ".debasher"

# The program metadata of before the artifact: version 0 of the artifact,
# read when there is no topology file and removed by the save that writes
# one.
PROGRAM_FILENAME = "program.json"

# The local state: the output directory of the program on this machine.
LOCAL_FILENAME = "local.json"

# The lock file that a save holds while it compares and writes the artifact
# (see save).
LOCK_FILENAME = "program.lock"


def is_reserved_name(name: str) -> bool:
    """
    True for a file/directory name DeBasher itself manages inside a
    program's home directory: the hidden .debasher directory, a
    dot-prefixed engine file (.debasher_webui_run.log, .conda,
    .sched_opts, .exec_context.sh, ...),
    a __dunder__-wrapped engine directory (__exec__, __graphs__,
    __fifos__), or command_line.sh, the one engine-written name that
    follows neither convention.

    This is a rule, not a hardcoded list, so it also covers any future
    engine-internal file added under the same naming convention. The
    program-files browser (see routers/program_files.py) must never
    show, descend into, or write to anything this matches. The topology
    file is not reserved: the panel shows it, read-only, as it shows the
    generated script.
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


def _home(home_dir: str) -> Path:
    return Path(home_dir).expanduser()


def read_raw_metadata(home_dir: str) -> dict | None:
    """
    The program metadata of before the artifact in `home_dir` as plain
    JSON, so that metadata the program model would refuse can still be
    read, or None when it is absent or is not a JSON object.
    """
    metadata_path = _home(home_dir) / METADATA_DIRNAME / PROGRAM_FILENAME
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return None
    return metadata if isinstance(metadata, dict) else None


def read_local_state(home_dir: str) -> dict:
    """The local state of the editor for the program in `home_dir`, {} when
    there is none or it cannot be read."""
    try:
        state = json.loads((_home(home_dir) / METADATA_DIRNAME / LOCAL_FILENAME).read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def saved_output_dir(home_dir: str) -> str:
    """
    The output directory that the program in `home_dir` had when it was
    last saved: the one of its local state, or, for a program still saved
    as program metadata, the one the metadata records; "" when there is
    none.
    """
    state = read_local_state(home_dir)
    if "outputDir" in state:
        return str(state.get("outputDir") or "")
    return str((read_raw_metadata(home_dir) or {}).get("outputDir", "") or "")


# --- the artifact on disk ------------------------------------------------------


@dataclass
class Artifact:
    """The artifact as read from a home directory: the text of the topology
    file, and the text of every file it names that exists, by path."""

    topology_text: str
    topology: Topology
    files: dict[str, str] = field(default_factory=dict)


def named_files(topology: Topology) -> list[str]:
    """The paths of every file a topology names: the process files, the
    scripts, the tasks files and the method files, in their order."""
    paths = []
    for process in [*topology.processes.values(), *topology.seq_processes.values()]:
        for path in (process.code, process.script, getattr(process, "tasks", None)):
            if path:
                paths.append(path)
        paths.extend(getattr(process, "methods", {}).values())
    return paths


def read_artifact(home_dir: str) -> Artifact | None:
    """
    The artifact in `home_dir`, or None when the directory has no topology
    file. Raises TopologyError when the topology file cannot be read. A
    file the topology names and that does not exist is left out, for
    join to report when it matters.
    """
    home = _home(home_dir)
    topology_path = home / TOPOLOGY_FILENAME
    if not topology_path.is_file():
        return None
    text = topology_path.read_text()
    loaded = topology.loads(text)
    files = {}
    for path in named_files(loaded):
        file_path = home / path
        if file_path.is_file():
            files[path] = file_path.read_text()
    return Artifact(topology_text=text, topology=loaded, files=files)


def artifact_digest(topology_text: str, files: dict[str, str]) -> str:
    """The digest of an artifact: of the text of the topology file and of
    every file it names, by path."""
    digest = hashlib.sha256()
    for path, text in [(TOPOLOGY_FILENAME, topology_text), *sorted(files.items())]:
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def saved_digest(home_dir: str) -> str | None:
    """
    The digest of the artifact in `home_dir` (see artifact_digest), of the
    text of the topology file alone when it cannot be read, or of the
    program metadata of before the artifact when that is what the
    directory holds; None when it holds neither.
    """
    home = _home(home_dir)
    topology_path = home / TOPOLOGY_FILENAME
    if topology_path.is_file():
        try:
            artifact = read_artifact(home_dir)
        except TopologyError:
            return artifact_digest(topology_path.read_text(), {})
        return artifact_digest(artifact.topology_text, artifact.files)
    metadata_path = home / METADATA_DIRNAME / PROGRAM_FILENAME
    if metadata_path.is_file():
        return hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    return None


def load_program(input_dir: str) -> Program:
    """
    The program saved in `input_dir`: from its artifact, or from the
    program metadata of before the artifact when the directory has no
    topology file.

    The program's home directory is the directory it is loaded from, as
    an absolute path, whatever was recorded when it was saved: a home
    directory that was copied or moved, or one shipped with DeBasher
    (data/webui_programs), goes on being saved and run where it now is.
    The output directory comes from the local state, so a program opened
    in a new place has none until the user sets one. The digest of what
    was read goes with the program, for the next write to name.

    Raises FileNotFoundError when the directory holds neither, and
    TopologyError when the artifact cannot be read.
    """
    home_dir = _home(input_dir).resolve()
    artifact = read_artifact(str(home_dir))
    if artifact is not None:
        program = topology.join(artifact.topology, artifact.files)
        program.homeDir = str(home_dir)
        program.outputDir = str(read_local_state(str(home_dir)).get("outputDir") or "")
        program.digest = artifact_digest(artifact.topology_text, artifact.files)
        return program

    program_path = home_dir / METADATA_DIRNAME / PROGRAM_FILENAME
    if not program_path.is_file():
        raise FileNotFoundError(
            f"No program found at {home_dir} "
            f"(expected a {TOPOLOGY_FILENAME} file, or a {METADATA_DIRNAME}/{PROGRAM_FILENAME} "
            "file, in the given directory)"
        )
    text = program_path.read_text()
    program = Program.model_validate_json(text)
    program.homeDir = str(home_dir)
    program.digest = hashlib.sha256(text.encode()).hexdigest()
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


# --- saving --------------------------------------------------------------------


def delete_stale_script(output_dir: str, new_name: str) -> None:
    """
    If a program was already saved to `output_dir` under a different
    name (the program can be renamed in the editor after being saved),
    remove that now-orphaned <old_name>.sh before writing the new one,
    otherwise renaming a program leaves a stale script sitting alongside
    the current one on every subsequent save.

    Called by save before it replaces the topology file, since that is
    the only record of what the program used to be named (the program
    metadata of before the artifact, for a program still saved as one). A
    missing or unreadable file just means there's no prior save to clean
    up after, not an error.
    """
    home = _home(output_dir)
    old_name = None
    topology_path = home / TOPOLOGY_FILENAME
    if topology_path.is_file():
        try:
            old_name = topology.loads(topology_path.read_text()).name
        except (OSError, TopologyError):
            old_name = None
    else:
        old_name = (read_raw_metadata(output_dir) or {}).get("name")

    if not old_name or old_name == new_name:
        return

    stale_script_path = home / f"{old_name}.sh"
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


class DigestConflict(Exception):
    """
    A write that names a digest of the artifact other than the one the
    home directory holds: someone else wrote the program since it was
    loaded, through the backend, by hand or through git. `digest` is the
    one it holds.
    """

    def __init__(self, digest: str):
        super().__init__(
            "The program changed on disk since it was loaded (another tab, another "
            "client of the backend, or an edit of its files). Load it again to see "
            "those changes: saving now would discard them."
        )
        self.digest = digest


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


def _same_text(path: Path, text: str) -> bool:
    try:
        return path.is_file() and path.read_text() == text
    except OSError:
        return False


def _write_text(path: Path, text: str) -> None:
    """Writes `text` whole: into a file beside `path` first, moved over it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(text)
    os.replace(temp_path, path)


def _same_artifact(home: Path, topology_text: str, files: dict[str, str], output_dir: str) -> bool:
    """Whether the artifact in `home` already holds what a save would write,
    and its local state the output directory."""
    if not _same_text(home / TOPOLOGY_FILENAME, topology_text):
        return False
    if any(not _same_text(home / path, text) for path, text in files.items()):
        return False
    return saved_output_dir(str(home)) == (output_dir or "")


@dataclass
class SavedProgram:
    program_path: Path
    script_path: Path
    digest: str


def save(home_dir: str, program: Program) -> SavedProgram:
    """
    Save `program` into `home_dir`: its artifact (the topology file, and
    every file it names that the editor writes, each only when its content
    changed, so that a file that holds what it should keeps its
    modification time), its local state when the output directory
    changed, its generated script, the files of its relative external
    aliases (see copy_ext_alias_files), and, when it was renamed, the
    removal of the script with its old name. A program still saved as
    program metadata of before the artifact loses that file: the home
    directory never holds both forms.

    The script is generated first, so that a program that script generation
    refuses (ValueError, NotImplementedError) leaves the home directory as it
    was. A save that would leave the artifact and the local state as they
    are keeps the digest, whatever digest the program names: it overwrites
    nobody's work. Any other save into the program's own home directory is
    refused with DigestConflict unless the artifact there holds the digest
    the program was loaded with (`program.digest`); a save into another
    directory replaces what is there, as a first save does. The comparison
    and the writes happen under a lock on the home directory, so that two
    saves arriving together cannot both pass the comparison.
    """
    script = script_generation.generate_script(program)
    taken_apart = topology.split(program)
    topology_text = topology.dumps(taken_apart.topology)
    files = taken_apart.files

    home = _home(home_dir)
    home.mkdir(parents=True, exist_ok=True)

    topology_path = home / TOPOLOGY_FILENAME

    with _metadata_lock(home):
        current = saved_digest(home_dir)

        if current is None or not _same_artifact(home, topology_text, files, program.outputDir):
            if current is not None and same_dir(home_dir, program.homeDir) and current != program.digest:
                raise DigestConflict(current)

            # Before the topology file is replaced, since it is the only
            # record of the old name.
            delete_stale_script(home_dir, program.name)

            for path, text in files.items():
                if not _same_text(home / path, text):
                    _write_text(home / path, text)
            _write_text(topology_path, topology_text)

            state = read_local_state(home_dir)
            if str(state.get("outputDir") or "") != (program.outputDir or ""):
                _write_text(
                    home / METADATA_DIRNAME / LOCAL_FILENAME,
                    json.dumps(state | {"outputDir": program.outputDir or ""}, indent=2) + "\n",
                )

            old_metadata = home / METADATA_DIRNAME / PROGRAM_FILENAME
            if old_metadata.is_file():
                old_metadata.unlink()

        # The scripts are part of the digest, so they are copied before it
        # is read: a copy that brings a script the artifact lacked changes it
        copy_ext_alias_files(program, home_dir)
        digest = saved_digest(home_dir)

        script_path = home / f"{program.name}.sh"
        script_path.write_text(script)

    return SavedProgram(program_path=topology_path, script_path=script_path, digest=digest)
