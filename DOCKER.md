# Docker demo image

`Dockerfile` packages the engine, API and web UI into a single container for
demoing/evaluating DeBasher. It is not meant for production use: it has no
conda/docker-in-docker support for processes that need their own
environment, and the Slurm scheduler backend is disabled, since it makes
no sense inside a container.

## Build and run

```bash
docker compose up --build -d
```

or without compose:

```bash
docker build -t debasher-demo .
docker run --rm -p 8000:8000 debasher-demo
```

Then open http://localhost:8000/.

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

`demo-data/` is `chmod 777` in this repo on purpose: the container runs as a
non-root `debasher` user (uid 1000), almost certainly a different uid than
your host user, so a plain bind mount would otherwise deny it write access.
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
2. `builder` (`debian:bookworm-slim`): builds engine + API the normal
   autotools way (`autoreconf`, `./configure --disable-frontend
   --disable-schedulers`, `make`, `make install DESTDIR=/out`).
   `--disable-frontend` is used because this stage has no npm; the frontend
   built in stage 1 is copied in separately instead.
3. `runtime` (`debian:bookworm-slim`): copies the installed engine/API from
   stage 2 and the built frontend from stage 1, creates a Python venv and
   `pip install`s `api/requirements.txt` into it, and runs as a non-root
   `debasher` user.

Note: the image runs `autoreconf -i -I m4 --force` directly rather than the
repo's `./reconf` script, because `reconf`'s preflight check looks for a
`libtool` binary that Debian's `libtool` package doesn't ship (only
`libtoolize`, which is what `autoreconf` actually needs).

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
