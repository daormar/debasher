# Docker demo image

`Dockerfile` packages the engine, API and web UI into a single container for
demoing/evaluating DeBasher. It is not meant for production use: it has no
conda/docker-in-docker support for processes that need their own
environment, and the Slurm scheduler backend is disabled, since it makes
no sense inside a container.

## Build and run

```bash
docker compose up --build -d
docker compose exec debasher webui-url
```

The first command builds the image (again, if the code changed) and starts
the container in the background (`-d`). The second prints the address of
the web interface to open in the browser, which holds the token that every
request has to carry:

```
http://localhost:8000/#token=<token>
```

The container prints the same address when it starts, but with `-d` that
goes to its logs (`docker compose logs debasher`), not to the terminal;
without `-d`, `docker compose up --build` shows it, and runs until Ctrl-C.
`webui-url` reads it again at any time.

Without compose:

```bash
docker build -t debasher-demo .
docker run --rm --name debasher-demo -p 8000:8000 debasher-demo
```

which prints the address in the terminal (`docker exec debasher-demo
webui-url` gives it as well).

The token is new at every start of the container; to keep the same one,
set `DEBASHER_WEBUI_TOKEN` (`-e DEBASHER_WEBUI_TOKEN=...`, or under
`environment:` in `docker-compose.yml`). The address names the port inside
the container: with another port on the host (`-p 9000:8000`), change it in
the address. Only one container can take a port of the host: stop the one
of compose (`docker compose down`) before `docker run` on the same port.

`docker-compose.yml` mounts a named volume at `/home/debasher`, so programs
created through the UI survive container restarts and rebuilds. Without
compose (plain `docker run`), add `-v debasher-home:/home/debasher` yourself
to get the same persistence, or accept that data disappears when the
container is removed.

## Example programs shipped in the image

`data/programs/*.sh` (`debasher_hello_world.sh`, `debasher_conda_example.sh`,
etc.) get installed by `make install` under
`/usr/local/share/debasher/programs/` inside the image, so they're there to
poke at without needing to import anything. They're plain `.sh` source, not
saved `.debasher/program.json` projects, so use the UI's "Import" flow (not
"Load") to open one; point it at a path under that directory, e.g.
`/usr/local/share/debasher/programs/debasher_hello_world.sh`.

## Programs built with the web UI

The programs of `data/webui_programs/` (`webui_running_sum`, `webui_fifo_sum`,
etc.) are installed under `/usr/local/share/debasher/webui_programs/`, which
the `debasher` user cannot write to. So that they can be changed and run in
place, `docker-entrypoint.sh`, the entry point of the image, copies each of
them into `/data/webui_programs/` every time the container starts, before it
launches the web UI. Open one with the UI's "Load program" (not "Import"),
e.g. `/data/webui_programs/webui_running_sum`.

A program already present under `/data/webui_programs/` is never
overwritten, so the changes made to it are kept across restarts; delete its
directory to get the shipped version back on the next start. A program added
to `data/webui_programs/` (and to its `Makefile.am`, which is what installs
it) appears there once the image is rebuilt and the container restarted. The
copies land side by side, as they are installed, so that
`webui_batch_launcher` still finds `webui_batch_greet` by its relative path.

With compose, `/data` is `./demo-data` on the host, so the copies show up at
`./demo-data/webui_programs/`, which `demo-data/.gitignore` keeps out of git.
Without compose, `/data` is a directory of the container, lost when the
container is removed; set `DEBASHER_DEMO_DIR` (`-e DEBASHER_DEMO_DIR=...`) to
copy them somewhere else.

## Claude Code

Claude Code runs inside the container, next to the web UI, where it finds
each program under the same path as the web UI (`/data/my-program`, not
`./demo-data/my-program`) and the token of the web UI. It sees only the
container and what is mounted into it, never the rest of your computer.

Claude Code is not part of the image, so building the image does not
install it: it is installed afterwards, once, into the running container.
The steps, from the directory of `docker-compose.yml`:

1. Build and start the container, and open the web UI (see "Build and
   run"):

   ```bash
   docker compose up --build -d
   docker compose exec debasher webui-url
   ```

2. Install Claude Code in the container, only the first time:

   ```bash
   docker compose exec -it debasher install-claude-code
   ```

   It runs the official installer of Claude Code, which puts it in the home
   directory of the `debasher` user, on the `debasher-home` volume, so it
   stays installed across restarts and rebuilds of the image (until the
   volume is removed, with `docker compose down -v`), and updates itself.

3. Save a program in the web UI and choose "Claude Code..." in its Help
   menu, which gives a command such as:

   ```bash
   docker compose exec -it debasher debasher_claude --home-dir /data/my-program --url http://127.0.0.1:8000
   ```

   Run it in a terminal, from the directory of `docker-compose.yml`. On its
   first start, Claude Code asks you to log in: inside the container there
   is no browser, so it shows an address to open in the browser of your
   computer and asks for the code that it gives. The login is kept on the
   same volume.

From then on, only step 3 is needed (with the container running). The URL
of the command names the web UI from inside the container, with the port of
the container, whatever port you map it to on the host.

Without compose, run both commands through `docker exec -it debasher-demo`
(the `--name` given to `docker run`) instead of
`docker compose exec -it debasher`.

## Working with real data

`docker-compose.yml` also bind-mounts `./demo-data` (on the host) to `/data`
(in the container). Use it for real bioinformatics input files, or for a
program's output: in the UI's save dialog, set the program's home directory
(`homeDir`) to a path under `/data` (e.g. `/data/my-program`) instead of
under `/home/debasher`, and its generated script and any output files it
writes will be visible from the host at `./demo-data/my-program`.

`homeDir` is an arbitrary absolute path typed in that dialog; the API server
writes there directly on its own (the container's) filesystem, so it only
works for paths that exist inside the container, whether that's the
`/home/debasher` volume, `/data`, or another mount you add.

`demo-data/` has to be writable by everyone: the container runs as a
non-root `debasher` user (uid 1000), almost certainly a different uid than
your host user, so a plain bind mount would otherwise deny it write access.
Git does not keep the permissions of a directory, so after cloning, run
once, before the first `docker compose up`:

```bash
chmod 777 demo-data
```

That's fine for a local demo; don't rely on it where real permission
boundaries matter.

If you'd rather not set up a bind mount at all, the UI's "Program files"
panel (in the toolbar, once a program has a `homeDir`) lets you browse,
upload, edit and download files straight from the browser, over
`/api/program-files/*`. That works with any `homeDir`, including one under
the `/home/debasher` named volume, at the cost of going through the browser
for every file instead of using the host's file manager/editor directly.

## Stopping the container

```bash
docker compose down
```

Stops and removes the container, but keeps the `debasher-home` named volume
(and `./demo-data`, which lives on the host anyway), so anything saved
through the UI is still there next time you run `docker compose up`. Add
`-v` (`docker compose down -v`) to also delete that volume.

To stop without removing, so a later `docker compose start` is quicker:
`docker compose stop`.

Without compose: `docker stop <container>` (and `docker rm <container>` too,
unless you started it with `--rm`, in which case it's removed automatically
on stop).

## How the image is built

Three stages:

1. `frontend-builder` (`node:22-bookworm-slim`): `npm ci && npm run build`,
   since the project's Vite/React frontend needs a newer Node than Debian
   bookworm ships.
   The build makes the MCP server (`debasher_mcp`) as well.
2. `builder` (`debian:bookworm-slim`): builds engine + API the normal
   autotools way (`./reconf`, `./configure`, `make clean`, `make`,
   `make install DESTDIR=/out`). `make clean` removes the scripts that a
   build on the host left in the source tree, which hold the host's prefix
   and tool paths and would otherwise be installed as they are.
   This stage has no npm: it takes the frontend and the MCP server built in
   stage 1 as a prebuilt frontend (`frontend/dist/.vendored`, as a release
   tarball made with `make dist-vendored` carries it), which `configure`
   installs as it is, with `debasher_mcp`, `debasher_claude` and the plugin
   of DeBasher for Claude Code.
3. `runtime` (`debian:bookworm-slim`): copies what stage 2 installed,
   creates a Python venv and `pip install`s `api/requirements.txt` into it,
   adds the Node.js of stage 1 for the MCP server and `install-claude-code`
   (see "Claude Code"), and runs `docker-entrypoint.sh` (see "Programs
   built with the web UI") as a non-root `debasher` user.

## Updating the image after a code change

```bash
docker compose up --build -d
```

Docker's layer cache means this usually doesn't redo the whole build:

- Changes under `frontend/src/` (or other frontend sources) invalidate the
  `frontend-builder` stage from the `COPY frontend/ ./` step onward
  (`npm run build` reruns); `npm ci` only reruns if `package.json` or
  `package-lock.json` changed.
- Changes under `engine/` or `api/` invalidate the `builder` stage's
  `COPY . .` step, so `autoreconf`/`configure`/`make`/`make install` rerun.
  This is fast since there's nothing to compile (pure bash/Python).
- Changes to `api/requirements.txt` invalidate the `pip install` step in the
  final stage.

If you add a new file under `api/` or `api/routers/`, add it to
`dist_api_DATA` / `dist_routers_DATA` in `api/Makefile.am` too. `make
install` only installs files listed there; a file that's only added to git
gets silently left out of the image (this bit us once: `api/routers/program_files.py`
and several other modules existed in the repo but were missing from that
list, so the installed API failed to import).
