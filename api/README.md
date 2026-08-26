# API (FastAPI)

Backend for the project: exposes the workflow API and, in production,
serves the built frontend as well.

## Development

Create a virtual environment and install the dependencies into it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then, from the repository root (with the virtual environment still
activated):

```bash
uvicorn api.main:app --reload
```

The frontend dev server (`frontend/`, `npm run dev`) proxies `/api/*`
requests to this server on its default port (8000).

When you're done, leave the virtual environment with:

```bash
deactivate
```

It can be re-entered later with the same `source .venv/bin/activate`
command — there's no need to recreate it, only re-run
`pip install -r requirements.txt` after dependencies change.

## Production

`make install` installs this server and the built frontend as plain
files — it does not install the server's Python dependencies, since
doing that from `make install` would reach outside the package's
`DESTDIR` and commonly fails on systems that protect the system
Python (PEP 668).

Create a virtual environment and install the dependencies into it
once (the file is installed alongside the rest of the API; the
launcher below prints its exact installed path if the dependencies
are missing when you try to run it):

```bash
python3 -m venv /path/to/debasher-venv
/path/to/debasher-venv/bin/pip install -r <pkgdatadir>/api/requirements.txt
```

Then launch the installed server with that virtual environment
activated:

```bash
source /path/to/debasher-venv/bin/activate
debasher_webui [--host <address>] [--port <port>]
```

`debasher_webui` runs whatever `python3` is first on `PATH`, so an
activated virtual environment is picked up automatically. If
activating isn't practical (e.g. launching from a systemd unit), point
it at the interpreter directly instead:

```bash
DEBASHER_WEBUI_PYTHON=/path/to/debasher-venv/bin/python3 debasher_webui
```

It serves both the API and the frontend build (installed to
`<pkgdatadir>/web`) from a single process — no separate frontend
server is needed in production.

`debasher_webui` runs in the foreground until stopped (e.g. with
`Ctrl-C`, or however the process is managed — systemd, a process
supervisor, etc.). Once it has stopped, leave the virtual environment
with:

```bash
deactivate
```
