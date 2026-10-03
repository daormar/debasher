# API (FastAPI)

Backend for the project: exposes the workflow API and, in production,
serves the built frontend as well.

## Development

From the repository root, create a virtual environment and install the
dependencies into it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
```

### Running the web UI from the sources

The server obeys only the requests that carry its token
(`Authorization: Bearer <token>`), and refuses to start without one (see
"Access to the backend: the token" in `doc/design_doc_webui.md`). To work on
the server and the editor at once, use two terminals.

In the first one, from the repository root, with the virtual environment
activated, choose a token and start the server, which reloads its code on
every change:

```bash
export DEBASHER_WEBUI_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
echo "$DEBASHER_WEBUI_TOKEN"
uvicorn api.main:app --reload
```

The token stays the same while uvicorn reloads the code. In the second one,
start the dev server of the editor, which serves it from its sources on port
5173 and forwards `/api/*` to the server on port 8000, with the token that the
page sends and none of its own:

```bash
cd frontend
npm install        # once, and after the dependencies change
npm run dev
```

Then open, once, the address of the editor with the token:

```
http://localhost:5173/#token=<the token printed above>
```

The page keeps the token in the browser, for every tab of that address, so
it is not needed again while the token stays the same. If the server is
started again with another token, the editor says so: open the address with
the new token in the same tab.

uvicorn started by hand writes no token file, so `debasher_mcp`, and with it
Claude Code (`debasher_claude`), cannot find the token. To work with Claude
Code on the sources, start the server as the installed `debasher_webui`
does, instead of the first terminal above:

```bash
python3 -m api.serve [--host <address>] [--port <port>]
```

It does not reload its code on a change. It takes the token of
`DEBASHER_WEBUI_TOKEN`, or draws one when the variable is unset, prints the
address of the web interface with it, and writes the token file that
`debasher_mcp` reads; with a built frontend (`npm run build`), that address
serves the editor too, on port 8000. Under the dev server, open
`http://localhost:5173/#token=<the token it printed>` instead.

When you're done, leave the virtual environment with:

```bash
deactivate
```

It can be re-entered later with the same `source .venv/bin/activate`
command: there's no need to recreate it, only to re-run
`pip install -r api/requirements.txt` after dependencies change.

### Tests

The tests of the API need these same dependencies (pydantic 2 among
them), so `make check` has to run them with the pytest of this virtual
environment rather than that of the system. Install the development
dependencies into it (`api/requirements-dev.txt`: those of the server
plus pytest, and coverage and radon for code analysis) and tell
`./configure` which pytest to use:

```bash
.venv/bin/pip install -r api/requirements-dev.txt
./configure PYTEST="$PWD/.venv/bin/pytest"
```

Running `./configure` with the virtual environment activated finds the
same pytest first on `PATH`. A pytest whose Python has an older pydantic
skips the test modules that need pydantic 2, and says why.

`make crap` runs the Python suites of the API and of the engine again
under coverage and lists the functions whose CRAP score (cyclomatic
complexity weighed against test coverage) is above 30, then does the same
for the frontend (see `frontend/README.md`). It is not part of
`make check`; see `test/utils/README.md` for the details.

## Production

`make install` installs this server and the built frontend as plain
files; it does not install the server's Python dependencies, since
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
debasher_webui [--host <address>] [--port <port>] [--token <token>]
```

It prints the address of the web interface, which holds the token that
every request has to carry (`http://<host>:<port>/#token=<token>`). The
token is new at every start, unless `DEBASHER_WEBUI_TOKEN` or
`--token` gives one.

`debasher_webui` runs whatever `python3` is first on `PATH`, so an
activated virtual environment is picked up automatically. If
activating isn't practical (e.g. launching from a systemd unit), point
it at the interpreter directly instead:

```bash
DEBASHER_WEBUI_PYTHON=/path/to/debasher-venv/bin/python3 debasher_webui
```

It serves both the API and the frontend build (installed to
`<pkgdatadir>/web`) from a single process: no separate frontend
server is needed in production.

`debasher_webui` runs in the foreground until stopped (e.g. with
`Ctrl-C`, or however the process is managed: systemd, a process
supervisor, etc.). Once it has stopped, leave the virtual environment
with:

```bash
deactivate
```
