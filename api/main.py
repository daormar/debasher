from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import workflows

app = FastAPI(title="Workflow API")

# API routes must be registered before mounting static files,
# otherwise the static mount at "/" would shadow them.
app.include_router(workflows.router)

# Serve the built frontend (frontend/dist) if it exists.
# During development with `npm run dev`, this directory usually
# won't be built yet — that's fine, the mount is skipped.
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
