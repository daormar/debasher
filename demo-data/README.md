Bind-mounted into the container at `/data` (see `docker-compose.yml`).

Put real input files here, or point a program's home directory (`homeDir`,
set from the UI's save dialog) at a path under `/data` to have its output
land here too, visible from the host.

Each time the container starts, it copies the example programs of
`data/webui_programs` that are not here yet into `webui_programs/` (see
`DOCKER.md`); `.gitignore` keeps those copies out of git.

This directory has to be `chmod 777` (git does not keep that, so run it
once after cloning): the container runs as a non-root `debasher` user (uid
1000), which is very likely a different uid than your host user, so a plain
bind mount would otherwise deny it write access. Do not rely on this for
anything that needs real permission boundaries; it's fine for a local demo,
not for a multi-user or production setup.
