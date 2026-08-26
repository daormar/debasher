from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/processes", tags=["processes"])


class ValidateProcessNameRequest(BaseModel):
    name: str


class ValidateProcessNameResponse(BaseModel):
    valid: bool


@router.post("/validate-name", response_model=ValidateProcessNameResponse)
def validate_process_name(request: ValidateProcessNameRequest) -> ValidateProcessNameResponse:
    """
    Validate a process name.

    Stub: always valid.

    TODO: replace with real validation logic, e.g. checking naming
    rules and/or uniqueness within the workflow.
    """
    return ValidateProcessNameResponse(valid=True)


class SuggestProcessNamesRequest(BaseModel):
    preamble: str


class SuggestProcessNamesResponse(BaseModel):
    names: list[str]


@router.post("/suggest-names", response_model=SuggestProcessNamesResponse)
def suggest_process_names(request: SuggestProcessNamesRequest) -> SuggestProcessNamesResponse:
    """
    Suggest process names based on the workflow's preamble.

    Stub: always returns an empty list.

    TODO: replace with real logic that inspects `request.preamble`
    (e.g. functions/commands it defines) to suggest names.
    """
    return SuggestProcessNamesResponse(names=[])
