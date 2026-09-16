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
# their own environment (--disable-schedulers is also set, since SGE/Slurm
# make no sense inside a container), and programs run as the "debasher"
# user's home directory, which is not persisted unless you mount a volume.

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
        autoconf automake libtool libltdl-dev build-essential \
        bash python3 gawk graphviz ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .

# Not using ./reconf: its preflight check looks for a "libtool" binary,
# which Debian's libtool package doesn't ship (only libtoolize, which is
# what autoreconf actually needs and uses under the hood).
#
# --disable-frontend: this stage has no npm, and the built frontend is
# copied in separately from the frontend-builder stage below.
# --disable-schedulers: SGE/Slurm are meaningless inside a container.
RUN autoreconf -i -I m4 --force \
    && ./configure --disable-frontend --disable-schedulers --prefix=/usr/local \
    && make \
    && make install DESTDIR=/out

########################################################################
# Stage 3: runtime
########################################################################
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash python3 python3-venv gawk graphviz \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash debasher

COPY --from=builder /out/usr/local /usr/local
COPY --from=frontend-builder /src/frontend/dist/ /usr/local/share/debasher/web/

RUN python3 -m venv /opt/debasher-venv \
    && /opt/debasher-venv/bin/pip install --no-cache-dir \
         -r /usr/local/share/debasher/api/requirements.txt
ENV PATH="/opt/debasher-venv/bin:${PATH}"

USER debasher
WORKDIR /home/debasher

EXPOSE 8000
ENTRYPOINT ["debasher_webui"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
