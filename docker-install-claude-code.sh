#!/bin/bash
# Installs Claude Code for the "debasher" user of the DeBasher demo image
# (see Dockerfile and DOCKER.md), run once from the host with:
#
#   docker compose exec -it debasher install-claude-code
#
# Claude Code is not part of the image: this runs its official installer,
# which puts it under ~/.local, in the home directory of the user, a volume
# that docker-compose.yml keeps across restarts and rebuilds of the image,
# so it is installed once. Claude Code updates itself from then on. It asks
# to log in on its first start, which keeps the login in the same volume.

set -euo pipefail

if command -v claude >/dev/null 2>&1; then
    echo "Claude Code is already installed: $(claude --version)"
    exit 0
fi

curl -fsSL https://claude.ai/install.sh | bash

echo ""
echo "Claude Code is installed. Start it on a program with the command that"
echo "\"Claude Code...\" in the Help menu of the web UI gives."
