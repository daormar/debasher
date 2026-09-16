Bind-mounted into the container at `/data` (see `docker-compose.yml`).

Put real input files here, or point a program's home directory (`homeDir`,
set from the UI's save dialog) at a path under `/data` to have its output
land here too, visible from the host.

This directory is `chmod 777` on purpose: the container runs as a non-root
`debasher` user (uid 1000), which is very likely a different uid than your
host user, so a plain bind mount would otherwise deny it write access. Do
not rely on this for anything that needs real permission boundaries; it's
fine for a local demo, not for a multi-user or production setup.
