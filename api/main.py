import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import token_auth
from .routers import execution, fs_browse, processes, program_files, programs, webui

# The pages that FastAPI adds to describe the API are turned off: whatever the
# backend serves without the token is the page of the web UI alone.
app = FastAPI(title="Program API", docs_url=None, redoc_url=None, openapi_url=None)

# API routes must be registered before mounting static files,
# otherwise the static mount at "/" would shadow them.
app.include_router(programs.router)
app.include_router(processes.router)
app.include_router(execution.router)
app.include_router(program_files.router)
app.include_router(fs_browse.router)
app.include_router(webui.router)

# Serve the built frontend if it exists. The installed `debasher_webui`
# launcher sets DEBASHER_WEBUI_STATIC_DIR to the installed location
# (<pkgdatadir>/web); outside of that, fall back to the repo-relative
# frontend/dist path used during development with `npm run build`. During
# `npm run dev` neither may exist yet: that's fine, the mount is skipped.
static_dir = os.environ.get("DEBASHER_WEBUI_STATIC_DIR")
frontend_dist = (
    Path(static_dir)
    if static_dir
    else Path(__file__).resolve().parent.parent / "frontend" / "dist"
)
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

# Every request but those for the page has to carry the token of the backend,
# which refuses to start without one.
app.add_middleware(
    token_auth.TokenAuthMiddleware,
    token=token_auth.token_from_env(),
    hosts=token_auth.allowed_hosts(
        os.environ.get(token_auth.HOST_ENV_VAR, token_auth.DEFAULT_HOST)
    ),
    pages=token_auth.page_paths(frontend_dist),
)
