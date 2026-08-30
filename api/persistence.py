from pathlib import Path

from . import script_generation
from .models import Workflow

# Directory (inside the user-chosen output directory) where the workflow
# is serialized. Hidden, following the convention of tool directories
# like .git.
METADATA_DIRNAME = ".debasher"

WORKFLOW_FILENAME = "workflow.json"


def save_workflow(output_dir: str, workflow: Workflow) -> Path:
    """
    Serialize `workflow` into <output_dir>/.debasher/workflow.json,
    creating `output_dir` (and the hidden directory) if needed.

    Returns the path to the written file.
    """
    resolved_output_dir = Path(output_dir).expanduser()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    metadata_dir = resolved_output_dir / METADATA_DIRNAME
    metadata_dir.mkdir(parents=True, exist_ok=True)

    workflow_path = metadata_dir / WORKFLOW_FILENAME
    workflow_path.write_text(workflow.model_dump_json(indent=2))

    return workflow_path


def save_script(output_dir: str, workflow: Workflow) -> Path:
    """
    Generate `workflow`'s Bash script via `script_generation.generate_script`
    and write it to <output_dir>/<workflow.name>.sh, creating `output_dir`
    if needed.

    Returns the path to the written file.
    """
    resolved_output_dir = Path(output_dir).expanduser()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    script_path = resolved_output_dir / f"{workflow.name}.sh"
    script_path.write_text(script_generation.generate_script(workflow))

    return script_path


def load_workflow(input_dir: str) -> Workflow:
    """
    Read and deserialize <input_dir>/.debasher/workflow.json.

    Raises FileNotFoundError if that file doesn't exist.
    """
    workflow_path = Path(input_dir).expanduser() / METADATA_DIRNAME / WORKFLOW_FILENAME

    if not workflow_path.is_file():
        raise FileNotFoundError(
            f"No workflow found at {workflow_path} "
            f"(expected a {METADATA_DIRNAME}/{WORKFLOW_FILENAME} file in the given directory)"
        )

    return Workflow.model_validate_json(workflow_path.read_text())


def resolve_script_path(script_path: str) -> Path:
    """
    Resolve `script_path` to an existing file.

    Raises FileNotFoundError if it doesn't exist.
    """
    resolved_script_path = Path(script_path).expanduser()

    if not resolved_script_path.is_file():
        raise FileNotFoundError(f"No such file: {resolved_script_path}")

    return resolved_script_path
