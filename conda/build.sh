#!/bin/bash
set -euo pipefail

# The tools that the engine needs are host requirements (see meta.yaml),
# so configure finds them under $PREFIX and writes paths that conda
# relocates. Put $PREFIX/bin first, so that neither $BUILD_PREFIX nor the
# build machine's own tools can win.
export PATH="${PREFIX}/bin:${PATH}"

# Optional tools, which are not requirements of the package: the
# interpreters of processes written in R, Perl or Groovy, Docker for
# processes that run in a container, and a few more. configure would
# write the path where the build machine has one, or nothing where it
# has none; either way, wrong where the package runs. Presetting the
# cache variable of each makes configure keep a bare name instead, which
# is then looked up in the PATH at run time, as the Slurm commands are
# (see configure.ac).
optional_tools=(
    ac_cv_path_RSCRIPT=Rscript
    ac_cv_path_PERL=perl
    ac_cv_path_GROOVY=groovy
    ac_cv_path_JAVA=java
    ac_cv_path_DOCKER=docker
    ac_cv_path_SSH=ssh
    ac_cv_path_WGET=wget
    ac_cv_path_PANDOC=pandoc
)

# The engine's Python modules: by default automake installs them into
# lib/python3.X/site-packages, 3.X being the Python of this build, while
# the package runs with any Python 3 (see conda_build_config.yaml). The
# installed scripts name that directory by its absolute path, so it can
# be one that does not depend on the version.
python_dirs=(
    am_cv_python_pythondir="${PREFIX}/lib/debasher/python"
    am_cv_python_pyexecdir="${PREFIX}/lib/debasher/python"
)

# No --disable-frontend: this source tarball is expected to be one built
# with "make dist-vendored", which already contains a prebuilt
# frontend/dist/ and a marker that makes configure install it as it is,
# without looking for npm, which this build has no network access for.
./configure --prefix="${PREFIX}" "${optional_tools[@]}" "${python_dirs[@]}"
make -j"${CPU_COUNT}"
make install

# Automake byte-compiles the engine's Python modules into __pycache__
# directories under $PREFIX. They are not needed (Python compiles them
# again on first import), and a noarch package must not carry bytecode
# of the Python it was built with.
find "${PREFIX}" -name '__pycache__' -type d -exec rm -rf {} +
