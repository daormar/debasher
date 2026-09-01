from pathlib import Path

from . import script_generation
from .models import Program

# Directory (inside the user-chosen output directory) where the program
# is serialized. Hidden, following the convention of tool directories
# like .git.
METADATA_DIRNAME = ".debasher"

PROGRAM_FILENAME = "program.json"


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

    Raises FileNotFoundError if that file doesn't exist.
    """
    program_path = Path(input_dir).expanduser() / METADATA_DIRNAME / PROGRAM_FILENAME

    if not program_path.is_file():
        raise FileNotFoundError(
            f"No program found at {program_path} "
            f"(expected a {METADATA_DIRNAME}/{PROGRAM_FILENAME} file in the given directory)"
        )

    return Program.model_validate_json(program_path.read_text())


def resolve_script_path(script_path: str) -> Path:
    """
    Resolve `script_path` to an existing file.

    Raises FileNotFoundError if it doesn't exist.
    """
    resolved_script_path = Path(script_path).expanduser()

    if not resolved_script_path.is_file():
        raise FileNotFoundError(f"No such file: {resolved_script_path}")

    return resolved_script_path
