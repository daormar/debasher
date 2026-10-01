import pydantic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import persistence, program_import, run_guard, saving, script_generation
from ..models import Program

router = APIRouter(prefix="/api/programs", tags=["programs"])


class SaveProgramRequest(BaseModel):
    outputDir: str
    program: Program


class SaveProgramResponse(BaseModel):
    path: str
    scriptPath: str
    # The revision of the program metadata just written.
    revision: int


class LoadProgramRequest(BaseModel):
    inputDir: str


class ImportProgramRequest(BaseModel):
    scriptPath: str
    debasherModDir: str = ""


class GetAllEnvVarsRequest(BaseModel):
    program: Program


class GetAllEnvVarsResponse(BaseModel):
    envVars: dict[str, str]


@router.post("/save", response_model=SaveProgramResponse)
def save_program_to_dir(request: SaveProgramRequest) -> SaveProgramResponse:
    """
    Serialize the whole program into a hidden directory inside
    `request.outputDir`, creating the output directory if needed. Refused
    while there is a run in progress in the program's output directory, or
    in the one that the metadata already saved there names (see run_guard),
    and, for a save into the program's own home directory, when the program
    metadata there holds another revision than the program's, with a
    conflict whose detail has the code "revision" (see persistence.save).
    """
    if not request.outputDir.strip():
        raise HTTPException(status_code=400, detail="outputDir must not be empty")

    if persistence.same_dir(request.outputDir, request.program.outputDir):
        raise HTTPException(
            status_code=400,
            detail=(
                "outputDir (where the program is saved) must not be the same "
                "directory as the program's execution output directory: "
                "running the program would then mix engine-internal files "
                "into the saved program, and resetting the execution "
                "directory would delete the saved program along with them."
            ),
        )

    run_guard.refuse_while_running(request.program, "save the program", request.outputDir)

    saved = saving.save_or_refuse(request.outputDir, request.program)

    return SaveProgramResponse(
        path=str(saved.program_path), scriptPath=str(saved.script_path), revision=saved.revision
    )


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


@router.post("/all-envvars", response_model=GetAllEnvVarsResponse)
def get_all_envvars(request: GetAllEnvVarsRequest) -> GetAllEnvVarsResponse:
    """
    Every variable newly bound while sourcing the program's current
    preamble (see script_generation.get_all_envvars), recomputed live
    each time this is called, e.g. every time the Env vars editor's
    read-only "module-defined" section is opened, rather than cached
    against whatever was true when the program was last imported.
    """
    return GetAllEnvVarsResponse(envVars=script_generation.get_all_envvars(request.program))
