# DeBasher demo image: engine + API + web UI in a single container.
#
# Build:
#   docker build -t debasher-demo .
# Run:
#   docker run --rm -p 8000:8000 debasher-demo
# then open http://localhost:8000/
#
# This image is meant for demoing/evaluating DeBasher, not for production
# use: it has no conda/docker-in-docker support for processes that need
# their own environment, and neither the "debasher" user's home directory
# nor the demo directory, /data, is persisted unless you mount a volume
# (docker-compose.yml mounts both). Processes run on the built-in
# scheduler, since the image has no Slurm.
#
# On each start, docker-entrypoint.sh copies the example programs of
# data/webui_programs that are not there yet into /data/webui_programs.

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

# --disable-frontend: this stage has no npm, and the built frontend is
# copied in separately from the frontend-builder stage below.
#
# make clean: a source tree that was built on the host carries its built
# scripts (engine/debasher_exec, ...), newer than their .sh sources, and
# with the host's prefix and tool paths written into them. Without
# removing them, make would install them as they are.
RUN ./reconf \
    && ./configure --disable-frontend --prefix=/usr/local \
    && make clean \
    && make \
    && make install DESTDIR=/out

########################################################################
# Stage 3: runtime
########################################################################
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash python3 python3-venv gawk graphviz procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash debasher \
    && mkdir /data && chown debasher:debasher /data

COPY --from=builder /out/usr/local /usr/local
COPY --from=frontend-builder /src/frontend/dist/ /usr/local/share/debasher/web/

RUN python3 -m venv /opt/debasher-venv \
    && /opt/debasher-venv/bin/pip install --no-cache-dir \
         -r /usr/local/share/debasher/api/requirements.txt
ENV PATH="/opt/debasher-venv/bin:${PATH}"
# The Help menu gives no command to start Claude Code: the directories of
# the container are not those of the computer where it would run.
ENV DEBASHER_WEBUI_CLAUDE_CODE=no

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER debasher
WORKDIR /home/debasher

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
