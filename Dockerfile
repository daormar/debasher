# DeBasher demo image: engine + API + web UI in a single container.
#
# Build:
#   docker build -t debasher-demo .
# Run:
#   docker run --rm --name debasher-demo -p 8000:8000 debasher-demo
# then open the address with the token that it prints (or that
# `docker exec debasher-demo webui-url` gives).
#
# This image is meant for demoing/evaluating DeBasher, not for production
# use: it has no docker-in-docker support for processes that run in their
# own docker container, and neither the "debasher" user's home directory
# nor the demo directory, /data, is persisted unless you mount a volume
# (docker-compose.yml mounts both). Processes run on the built-in
# scheduler, since the image has no Slurm.
#
# Conda is there (Miniforge, under /opt/conda), so that a run with conda
# support creates the environments of its processes. They are kept in the
# home directory of the "debasher" user, so that one created once survives
# a restart and a rebuild when that directory is a volume. Conda doubles
# the size of the image; to leave it out, build with
# --build-arg WITH_CONDA=no.
#
# The web UI prints the address to open, with its token, when it starts:
# see the logs of the container, or run webui-url in it at any time.
#
# On each start, docker-entrypoint.sh copies the example programs of
# data/webui_programs that are not there yet into /data/webui_programs.
#
# Claude Code runs inside the container, where the directories and the token
# of the web UI are (see DOCKER.md): install-claude-code installs it once, in
# the home directory of the "debasher" user, and the Help menu of the web UI
# gives the `docker compose exec` command that starts it on a program.

########################################################################
# Stage 1: frontend (Vite needs a newer Node than Debian bookworm ships)
########################################################################
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

########################################################################
# Stage 2: engine + API, built the normal autotools way
########################################################################
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        autoconf automake build-essential \
        bash python3 gawk graphviz ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .

# The frontend and the MCP server built in the frontend-builder stage, as a
# release tarball made with "make dist-vendored" carries them (the .vendored
# marker): configure then installs them, with the launchers of the MCP server
# and of Claude Code (debasher_mcp, debasher_claude) and the plugin of
# DeBasher, without looking for npm, which this stage does not have.
COPY --from=frontend-builder /src/frontend/dist/ frontend/dist/
COPY --from=frontend-builder /src/frontend/mcp/dist/ frontend/mcp/dist/
RUN touch frontend/dist/.vendored

# make clean: a source tree that was built on the host carries its built
# scripts (engine/debasher_exec, ...), newer than their .sh sources, and
# with the host's prefix and tool paths written into them. Without
# removing them, make would install them as they are.
# CONDA_CMD: the conda of the runtime stage, which this stage does not
# have, so configure finds none; given to make, it goes into the built
# scripts all the same. Without conda it stays empty, and a process that
# activates an environment fails saying that there is no conda.
ARG WITH_CONDA=yes
RUN if [ "${WITH_CONDA}" = yes ]; then conda_cmd=/opt/conda/bin/conda; else conda_cmd=; fi \
    && ./reconf \
    && ./configure --prefix=/usr/local \
    && make clean \
    && make CONDA_CMD="${conda_cmd}" \
    && make install DESTDIR=/out

########################################################################
# Stage 3: runtime
########################################################################
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash python3 python3-venv gawk graphviz procps \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash debasher \
    && mkdir /data && chown debasher:debasher /data

# Miniforge: conda with conda-forge as its only channel, for the machine
# the image is built on (x86_64 or aarch64). It stays owned by root: the
# environments and the packages they download go to the home directory of
# "debasher" (CONDA_ENVS_DIRS, CONDA_PKGS_DIRS below). Left out with
# WITH_CONDA=no.
ARG WITH_CONDA=yes
RUN if [ "${WITH_CONDA}" = yes ]; then \
        curl -fsSL -o /tmp/miniforge.sh \
            "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh" \
        && bash /tmp/miniforge.sh -b -p /opt/conda \
        && rm /tmp/miniforge.sh \
        && /opt/conda/bin/conda clean -afy; \
    fi
ENV CONDA_ENVS_DIRS=/home/debasher/.conda/envs
ENV CONDA_PKGS_DIRS=/home/debasher/.conda/pkgs

COPY --from=builder /out/usr/local /usr/local
# The Node.js that the MCP server (debasher_mcp) is built for, a single
# binary that needs nothing but the C and C++ runtime of Debian.
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node

RUN python3 -m venv /opt/debasher-venv \
    && /opt/debasher-venv/bin/pip install --no-cache-dir \
         -r /usr/local/share/debasher/api/requirements.txt
# ~/.local/bin: where install-claude-code puts Claude Code (claude).
ENV PATH="/home/debasher/.local/bin:/opt/debasher-venv/bin:${PATH}"
# The Help menu gives the command that starts Claude Code on a program run
# through `docker compose exec`, inside this container, where the directories
# and the token file of the web UI are, and the one that installs it there.
ENV DEBASHER_WEBUI_CLAUDE_CODE_PREFIX="docker compose exec -it debasher"
ENV DEBASHER_WEBUI_CLAUDE_CODE_INSTALL="docker compose exec -it debasher install-claude-code"

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker-install-claude-code.sh /usr/local/bin/install-claude-code
COPY docker-webui-url.sh /usr/local/bin/webui-url

USER debasher
WORKDIR /home/debasher

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
