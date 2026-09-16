#!/bin/bash
set -euo pipefail

# No --disable-schedulers: Slurm tool names are resolved via PATH at *run*
# time, not baked in at build time (see configure.ac), so this package
# works whether or not the machine building it has Slurm installed, and
# correctly picks up Slurm on whatever cluster it's later installed on.
#
# No --disable-frontend: this source tarball is expected to be one built
# with "make dist-vendored", which already contains a prebuilt
# frontend/dist/. configure.ac falls back to installing it as-is when
# npm isn't found (it won't be, here), so the frontend still gets
# installed without needing npm/network access during this build.
./configure --prefix="${PREFIX}"
make -j"${CPU_COUNT}"
make install

# Automake's own python_PYTHON byte-compilation (the "Byte-compiling
# python modules" step above) writes .pyc/__pycache__ under $PREFIX.
# conda-build's post-build cleanup pass then trips on one of those
# (FileNotFoundError in conda_build/post.py's rm_pyc, looking for a
# .pyc under the placeholder-padded build prefix that isn't where it
# expects) regardless of the python version or PYTHONDONTWRITEBYTECODE.
# We don't need the bytecode cache (two small runtime scripts, Python
# recompiles on first import anyway), so just remove it ourselves before
# conda-build gets a chance to look at it.
find "${PREFIX}" -name '__pycache__' -type d -exec rm -rf {} +
