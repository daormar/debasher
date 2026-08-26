import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import processes, workflows

app = FastAPI(title="Workflow API")

# API routes must be registered before mounting static files,
# otherwise the static mount at "/" would shadow them.
app.include_router(workflows.router)
app.include_router(processes.router)

# Serve the built frontend if it exists. The installed `debasher_webui`
# launcher sets DEBASHER_WEBUI_STATIC_DIR to the installed location
# (<pkgdatadir>/web); outside of that, fall back to the repo-relative
# frontend/dist path used during development with `npm run build`. During
# `npm run dev` neither may exist yet — that's fine, the mount is skipped.
static_dir = os.environ.get("DEBASHER_WEBUI_STATIC_DIR")
frontend_dist = (
    Path(static_dir)
    if static_dir
    else Path(__file__).resolve().parent.parent / "frontend" / "dist"
)
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
