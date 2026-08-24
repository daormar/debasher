from pathlib import Path

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
