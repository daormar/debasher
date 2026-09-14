from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .. import file_inspection, persistence

router = APIRouter(prefix="/api/program-files", tags=["program-files"])


def resolve_within(home_dir: str, rel_path: str) -> Path:
    """
    Resolves `rel_path` against `home_dir`, refusing anything that
    would escape it (including through a symlink, since `resolve()`
    follows them) or that touches a DeBasher-reserved name anywhere
    along the way. An empty `rel_path` resolves to `home_dir` itself.

    Raises ValueError (turned into a 400 by every caller below) on any
    violation — never returns a path outside `home_dir`.
    """
    if not home_dir.strip():
        raise ValueError("homeDir must not be empty")

    resolved_home = Path(home_dir).expanduser().resolve()

    if not rel_path:
        return resolved_home

    if Path(rel_path).is_absolute():
        raise ValueError(f"{rel_path!r} must be a relative path")

    candidate = (resolved_home / rel_path).resolve()

    try:
        parts = candidate.relative_to(resolved_home).parts
    except ValueError:
        raise ValueError(f"{rel_path!r} escapes the program's home directory")

    if any(persistence.is_reserved_name(part) for part in parts):
        raise ValueError(f"{rel_path!r} refers to a reserved DeBasher file or directory")

    return candidate


def _is_protected_script(target: Path, home: Path, program_name: str) -> bool:
    """
    True for the program's own generated `<programName>.sh`, and only
    that file, at the top level of `home` — the one entry the panel
    shows but must never let the user delete, move, or overwrite.
    """
    try:
        parts = target.relative_to(home).parts
    except ValueError:
        return False

    return len(parts) == 1 and parts[0] == f"{program_name}.sh"


class FileEntry(BaseModel):
    name: str
    # Relative to homeDir, posix-style ("/" separators regardless of
    # server OS — this app only targets Linux, but slashes are cheap to
    # be explicit about since the frontend round-trips this value back
    # as a request path).
    path: str
    type: Literal["file", "dir"]
    readonly: bool
    children: list[FileEntry] | None = None


def _build_tree(dir_path: Path, rel_prefix: str, script_name: str) -> list[FileEntry]:
    entries: list[FileEntry] = []

    try:
        children = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return entries

    for child in children:
        if persistence.is_reserved_name(child.name):
            continue

        rel_path = f"{rel_prefix}{child.name}"
        is_dir = child.is_dir()
        is_symlink = child.is_symlink()

        entries.append(
            FileEntry(
                name=child.name,
                path=rel_path,
                type="dir" if is_dir else "file",
                readonly=(not is_dir and rel_prefix == "" and child.name == script_name),
                # Never descend into a symlinked directory: it could
                # point anywhere, including outside homeDir.
                children=(
                    _build_tree(child, f"{rel_path}/", script_name)
                    if is_dir and not is_symlink
                    else None
                ),
            )
        )

    return entries


class FileTreeResponse(BaseModel):
    entries: list[FileEntry]


def _tree_response(home_dir: str, program_name: str) -> FileTreeResponse:
    home = Path(home_dir).expanduser().resolve()
    if not home.is_dir():
        return FileTreeResponse(entries=[])
    return FileTreeResponse(entries=_build_tree(home, "", f"{program_name}.sh"))


class FileTreeRequest(BaseModel):
    homeDir: str
    programName: str


@router.post("/tree", response_model=FileTreeResponse)
def get_file_tree(request: FileTreeRequest) -> FileTreeResponse:
    """
    Lists everything under `request.homeDir` except DeBasher-reserved
    entries (see persistence.is_reserved_name), for the "Program files"
    panel. The generated `<programName>.sh` is included but flagged
    readonly=True; everything else is a plain user-managed file or dir.
    """
    if not request.homeDir.strip():
        raise HTTPException(status_code=400, detail="homeDir must not be empty")

    return _tree_response(request.homeDir, request.programName)


class FileContentRequest(BaseModel):
    homeDir: str
    path: str


class FileContentResponse(BaseModel):
    kind: Literal["file", "binary", "missing"]
    content: str | None = None


@router.post("/content", response_model=FileContentResponse)
def get_file_content(request: FileContentRequest) -> FileContentResponse:
    """
    Returns one file's text content, for the panel's read-only preview
    of the generated `.sh` (or any other text file the user selects).
    """
    try:
        resolved = resolve_within(request.homeDir, request.path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    if not resolved.is_file():
        return FileContentResponse(kind="missing")

    if file_inspection.looks_binary(resolved):
        return FileContentResponse(kind="binary")

    try:
        content = file_inspection.read_text_capped(resolved)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not read {request.path!r}: {e}")

    return FileContentResponse(kind="file", content=content)


class MkdirRequest(BaseModel):
    homeDir: str
    programName: str
    path: str


@router.post("/mkdir", response_model=FileTreeResponse)
def make_directory(request: MkdirRequest) -> FileTreeResponse:
    if not request.path:
        raise HTTPException(status_code=400, detail="path must not be empty")

    try:
        target = resolve_within(request.homeDir, request.path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise HTTPException(status_code=400, detail=f"{request.path!r} already exists")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not create {request.path!r}: {e}")

    return _tree_response(request.homeDir, request.programName)


class WriteContentRequest(BaseModel):
    homeDir: str
    programName: str
    path: str
    content: str


@router.post("/write-content", response_model=FileTreeResponse)
def write_file_content(request: WriteContentRequest) -> FileTreeResponse:
    """
    Overwrites an existing file's content, for the panel's in-place
    editor. Refuses the protected `<programName>.sh` and any path that
    doesn't already name a file — this isn't a way to create one.
    """
    if not request.path:
        raise HTTPException(status_code=400, detail="path must not be empty")

    try:
        target = resolve_within(request.homeDir, request.path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    home = Path(request.homeDir).expanduser().resolve()
    if _is_protected_script(target, home, request.programName):
        raise HTTPException(
            status_code=400, detail="Cannot edit the program's generated script"
        )

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"{request.path!r} does not exist")

    try:
        target.write_text(request.content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not write {request.path!r}: {e}")

    return _tree_response(request.homeDir, request.programName)


class DeleteRequest(BaseModel):
    homeDir: str
    programName: str
    path: str


@router.post("/delete", response_model=FileTreeResponse)
def delete_entry(request: DeleteRequest) -> FileTreeResponse:
    if not request.path:
        raise HTTPException(status_code=400, detail="path must not be empty")

    try:
        target = resolve_within(request.homeDir, request.path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    home = Path(request.homeDir).expanduser().resolve()
    if _is_protected_script(target, home, request.programName):
        raise HTTPException(
            status_code=400, detail="Cannot delete the program's generated script"
        )

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"{request.path!r} does not exist")

    try:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not delete {request.path!r}: {e}")

    return _tree_response(request.homeDir, request.programName)


class MoveRequest(BaseModel):
    homeDir: str
    programName: str
    srcPath: str
    dstPath: str


@router.post("/move", response_model=FileTreeResponse)
def move_entry(request: MoveRequest) -> FileTreeResponse:
    """
    Renames or moves a file/dir within homeDir — covers both "rename
    in place" (same parent, new name) and "reorganize into a folder"
    (new parent).
    """
    if not request.srcPath or not request.dstPath:
        raise HTTPException(status_code=400, detail="srcPath and dstPath must not be empty")

    try:
        src = resolve_within(request.homeDir, request.srcPath)
        dst = resolve_within(request.homeDir, request.dstPath)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    home = Path(request.homeDir).expanduser().resolve()
    if _is_protected_script(src, home, request.programName) or _is_protected_script(
        dst, home, request.programName
    ):
        raise HTTPException(
            status_code=400, detail="Cannot move the program's generated script"
        )

    if not src.exists():
        raise HTTPException(status_code=404, detail=f"{request.srcPath!r} does not exist")

    if dst.exists():
        raise HTTPException(status_code=400, detail=f"{request.dstPath!r} already exists")

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not move {request.srcPath!r}: {e}")

    return _tree_response(request.homeDir, request.programName)


@router.post("/upload", response_model=FileTreeResponse)
async def upload_files(
    homeDir: str = Form(...),
    programName: str = Form(...),
    path: str = Form(""),
    files: list[UploadFile] = File(...),
) -> FileTreeResponse:
    """
    Uploads one or more files into `path` (relative to homeDir, ""
    meaning homeDir itself), creating it if needed. Unfiltered by file
    type or extension on purpose: this is also how an external-alias
    script gets into a program's home directory when the program
    wasn't built by importing one (see copy_ext_alias_files, which only
    runs when program.sourceDir is set).
    """
    try:
        target_dir = resolve_within(homeDir, path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    home = Path(homeDir).expanduser().resolve()

    destinations: list[tuple[Path, UploadFile]] = []
    for upload in files:
        filename = Path(upload.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")

        if persistence.is_reserved_name(filename):
            raise HTTPException(
                status_code=400, detail=f"{filename!r} is a reserved DeBasher name"
            )

        dest = target_dir / filename
        if _is_protected_script(dest, home, programName):
            raise HTTPException(
                status_code=400,
                detail=f"{filename!r} would overwrite the program's generated script",
            )

        destinations.append((dest, upload))

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for dest, upload in destinations:
            with dest.open("wb") as f:
                shutil.copyfileobj(upload.file, f)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not save uploaded file: {e}")

    return _tree_response(homeDir, programName)
