"""
Saving a program from an endpoint: persistence.save, with its refusals
answered as HTTP errors, for "Save" and for the requests that save the
program before they run it.
"""

from fastapi import HTTPException

from . import persistence
from .models import Program

# The code of the conflict with which a request that writes the program
# metadata answers when the metadata holds another revision than the one
# the program names (see persistence.save).
REVISION_CONFLICT = "revision"


def save_or_refuse(home_dir: str, program: Program) -> persistence.SavedProgram:
    """
    Save `program` into `home_dir` (see persistence.save). A save that the
    revision of the program metadata refuses is a conflict whose detail has
    the code "revision", the revision held and the message; a program that
    script generation refuses is a bad request, or not implemented for what
    it does not handle yet. Either way nothing is written.
    """
    try:
        return persistence.save(home_dir, program)
    except persistence.RevisionConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"code": REVISION_CONFLICT, "revision": conflict.revision, "message": str(conflict)},
        )
    except NotImplementedError as err:
        raise HTTPException(status_code=501, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
