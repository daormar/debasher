from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fs", tags=["fs"])


class FsEntry(BaseModel):
    name: str
    path: str
    type: Literal["dir", "file"]


class ListDirsRequest(BaseModel):
    path: str = ""
    # When set, files are listed alongside directories (optionally
    # narrowed by `extensions`), for a file picker such as Import
    # program's script path. Directories are always listed, since
    # they're how the browser navigates regardless of what's selected.
    includeFiles: bool = False
    extensions: list[str] | None = None


class ListDirsResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntry]


def _list_entries(
    target: Path, include_files: bool, extensions: list[str] | None
) -> list[FsEntry]:
    entries: list[FsEntry] = []
    lowered_extensions = [ext.lower() for ext in extensions] if extensions else None

    try:
        children = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return entries

    for child in children:
        try:
            is_dir = child.is_dir()
        except OSError:
            # Unreadable/broken entry (e.g. a dangling symlink): skip it
            # rather than failing the whole listing.
            continue

        if is_dir:
            entries.append(FsEntry(name=child.name, path=str(child), type="dir"))
        elif include_files:
            if lowered_extensions and not any(
                child.name.lower().endswith(ext) for ext in lowered_extensions
            ):
                continue
            entries.append(FsEntry(name=child.name, path=str(child), type="file"))

    return entries


@router.post("/list-dirs", response_model=ListDirsResponse)
def list_dirs(request: ListDirsRequest) -> ListDirsResponse:
    """
    Lists the immediate contents of `request.path` (the server
    process's home directory when empty): directories always, plus
    files when `includeFiles` is set (optionally filtered to
    `extensions`, e.g. [".sh"]). Backs both the directory-only picker
    (Load program) and the file picker (Import program's script path).
    Unlike program_files.py's endpoints, this isn't sandboxed to a
    single program's home directory: it lets the user navigate
    anywhere the server process can read, the same as a desktop
    file-open dialog.
    """
    target = (
        Path(request.path).expanduser().resolve()
        if request.path.strip()
        else Path.home()
    )

    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"{str(target)!r} is not a directory")

    parent = target.parent
    return ListDirsResponse(
        path=str(target),
        parent=str(parent) if parent != target else None,
        entries=_list_entries(target, request.includeFiles, request.extensions),
    )
