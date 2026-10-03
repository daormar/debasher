#!/bin/bash
# Prints the address of the web UI of the DeBasher demo image (see
# Dockerfile and DOCKER.md) with its token, run from the host with:
#
#   docker compose exec debasher webui-url
#
# debasher_webui prints that address once, when it starts, which the logs of
# a container started in the background keep among the rest; this reads it
# again, at any time, from the token file that debasher_webui leaves for each
# port it listens on. The port is that of the container: with another port
# on the host (-p 9000:8000), change it in the address.

set -euo pipefail

if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    dir="${XDG_RUNTIME_DIR}/debasher"
else
    dir="${HOME}/.debasher/run"
fi

shopt -s nullglob
token_files=("${dir}"/webui-*.token)
if [ ${#token_files[@]} -eq 0 ]; then
    echo "Error: the web UI is not running in this container (no token file in ${dir})" >&2
    exit 1
fi

for token_file in "${token_files[@]}"; do
    port=${token_file##*/webui-}
    port=${port%.token}
    token=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["token"])' "${token_file}")
    echo "http://localhost:${port}/#token=${token}"
done
