import pydantic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import persistence, program_import
from ..models import Program

router = APIRouter(prefix="/api/programs", tags=["programs"])


class SaveProgramRequest(BaseModel):
    outputDir: str
    program: Program


class SaveProgramResponse(BaseModel):
    path: str
    scriptPath: str


class LoadProgramRequest(BaseModel):
    inputDir: str


class ImportProgramRequest(BaseModel):
    scriptPath: str
    debasherModDir: str = ""


@router.post("/save", response_model=SaveProgramResponse)
def save_program_to_dir(request: SaveProgramRequest) -> SaveProgramResponse:
    """
    Serialize the whole program into a hidden directory inside
    `request.outputDir`, creating the output directory if needed.
    """
    if not request.outputDir.strip():
        raise HTTPException(status_code=400, detail="outputDir must not be empty")

    # Must run before save_program, which is what overwrites the
    # metadata file this reads the previous name from.
    persistence.delete_stale_script(request.outputDir, request.program.name)

    program_path = persistence.save_program(request.outputDir, request.program)

    try:
        script_path = persistence.save_script(request.outputDir, request.program)
    except NotImplementedError as err:
        raise HTTPException(status_code=501, detail=str(err))

    persistence.copy_ext_alias_files(request.program, request.outputDir)

    return SaveProgramResponse(path=str(program_path), scriptPath=str(script_path))


@router.post("/load", response_model=Program)
def load_program_from_dir(request: LoadProgramRequest) -> Program:
    """
    Read a program previously saved into `request.inputDir` via `/save`.
    """
    if not request.inputDir.strip():
        raise HTTPException(status_code=400, detail="inputDir must not be empty")

    try:
        return persistence.load_program(request.inputDir)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except pydantic.ValidationError as err:
        raise HTTPException(
            status_code=400, detail=f"Invalid program data in {request.inputDir!r}: {err}"
        )


@router.post("/import", response_model=Program)
def import_program(request: ImportProgramRequest) -> Program:
    """
    Import a program from an existing Bash script, by running
    debasher_doc_mod over it and parsing the Markdown it generates (see
    program_import.py for what can and can't be recovered this way).
    """
    if not request.scriptPath.strip():
        raise HTTPException(status_code=400, detail="scriptPath must not be empty")

    try:
        resolved_script_path = persistence.resolve_script_path(request.scriptPath)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))

    try:
        return program_import.import_program_from_script(
            resolved_script_path, request.debasherModDir
        )
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/{program_id}", response_model=Program)
def get_program(program_id: str) -> Program:
    """
    Load a program by id.

    TODO: replace this stub with a real call into core/, e.g.:
        return core.load_program(program_id)
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.put("/{program_id}")
def save_program(program_id: str, program: Program) -> dict[str, str]:
    """
    Persist a program.

    TODO: replace this stub with a real call into core/, e.g.:
        core.save_program(program_id, program)
    """
    raise HTTPException(status_code=501, detail="Not implemented yet")
