# bioconda recipe

`meta.yaml` and `build.sh` here are a working draft of the recipe to submit
to [bioconda-recipes](https://github.com/bioconda/bioconda-recipes) (as
`recipes/debasher/meta.yaml` there, bioconda recipes aren't consumed from
this repo directly). They install the engine, the FastAPI backend and the
built React Flow UI (`debasher_webui`), all from a single package.

## Why this needs a special release tarball

A plain `make dist` tarball needs `npm` to build the frontend, and
bioconda's build sandbox has no network access, so it can't run `npm ci`.
`source: url:` here must instead point at a tarball built with `make
dist-vendored` (see the root `Makefile.am`), which embeds an already-built
`frontend/dist/` plus a `.vendored` marker file. `configure.ac` checks for
that marker and, when present, installs that prebuilt frontend as-is
without ever looking for `npm` (see the comment there), so `build.sh` ends
up being just:

```bash
./configure --prefix="${PREFIX}"
make -j"${CPU_COUNT}"
make install
```

No autoconf/automake either: the dist tarball already ships the generated
`configure` script and `Makefile.in` files (`EXTRA_DIST` in the root
`Makefile.am`), so plain `make` is enough.

## Tool paths and the noarch package

`configure` writes the absolute path of each tool it finds (`bash` in the
shebang, `sed`, `flock`, `dot`, ...) into the scripts it builds. For a
single `noarch: generic` package that runs on Linux and on macOS, each of
those paths has to point inside the environment where the package is
installed:

- The tools the engine needs (Bash 4.3 or newer, the GNU coreutils,
  findutils, sed, grep and gawk, diffutils, gzip, `flock` from util-linux,
  Graphviz) are `host` requirements, not only `run` ones, so `configure`
  finds them under `$PREFIX`, which conda rewrites on install. Otherwise it
  would take the build machine's own, which on macOS would be Bash 3.2 and
  BSD tools, or a path that does not exist at all.
- The optional tools (`Rscript`, `perl`, `groovy`, `java`, `docker`, `ssh`,
  `wget`, `pandoc`) are not requirements of the package. `build.sh`
  presets their autoconf cache variables to bare names, so they are looked
  up in the `PATH` at run time, as the Slurm commands are.

Python is a host requirement for the same reason, and the engine's Python
modules go to `lib/debasher/python/`, a directory that does not depend on
the version of Python. `conda_build_config.yaml` relaxes conda-build's
`pin_run_as_build` for Python, which would otherwise tie the package to
the minor version of Python it was built with (`util-linux` is built per
Python version, so Python is always in the host environment anyway).

`run_test.sh` checks that no installed script holds a path outside the
environment, runs a few example programs to their end, and starts the web
UI's server and loads a program through its API.

## Cutting a release for this recipe

1. From a clean checkout, at the commit/tag you're releasing:
   ```bash
   ./reconf && ./configure && make dist-vendored
   ```
   This needs npm (Node.js 22.12 or newer) in the `PATH`, to build the
   frontend that the tarball carries.
2. Upload the resulting `debasher-<version>.tar.gz` as a GitHub release
   asset at `https://github.com/daormar/debasher/releases/tag/v<version>`
   (the URL `meta.yaml` expects).
3. `sha256sum debasher-<version>.tar.gz` and put that value (not the one
   currently in `meta.yaml`, which is from a local test build) into
   `source: sha256:`.
4. Bump `{% set version = "..." %}` and reset `build: number: 0` if this
   is a new upstream version (bump just `number` for a rebuild of the same
   version).

## HPC (Slurm) support

`configure.ac` bakes the Slurm tool names (`SBATCH`, `SRUN`, ...) in as
bare command names rather than absolute paths, and
`engine/debasher_lib_sched.sh` / `debasher_lib_sched_slurm.sh` resolve them
via `command -v` at run time rather than trusting what `configure` saw on
the build machine. So this package works correctly whether or not Slurm
was present when bioconda built it: a `conda install`ed copy on an HPC
login node with Slurm on `PATH` uses it, and one on a laptop without Slurm
falls back to the builtin scheduler, exactly as a from-source build would.

## Testing locally

The release asset that `meta.yaml` names does not exist before the
release, so `make_local_recipe.sh` writes a copy of the recipe whose source
is a local tarball, with its sha256:

```bash
mamba create -n bioconda-test -c conda-forge -c bioconda conda-build bioconda-utils -y
conda activate bioconda-test
conda/make_local_recipe.sh debasher-<version>.tar.gz /tmp/recipe
conda-build /tmp/recipe --croot /tmp/cbuild -c conda-forge --override-channels
```

Every requirement comes from conda-forge, so the bioconda channel is not
needed here, and leaving it out keeps the solver's memory use down
(conda-build with both channels can need more than 4 GB). If the test
phase still runs out of memory, build with `--no-test` and test as below.

The package is noarch, so the one bioconda builds on Linux is the one
that macOS users install. To check it on a Mac, or with a Python other
than the build's, install it into a new environment and run
`run_test.sh` there, with `PREFIX` set to the environment:

```bash
conda create -n debasher-test -c /tmp/cbuild -c conda-forge debasher curl python=3.11
conda activate debasher-test
PREFIX="$CONDA_PREFIX" bash conda/run_test.sh
```

The workflow `.github/workflows/conda.yml` does all of this on every push:
it builds the tarball and the package on Linux, running the recipe's test,
and then installs the package on macOS, on Apple silicon and on Intel,
with Python 3.11, and runs `run_test.sh` there, without Homebrew's GNU
tools in the `PATH`, so that the package has to bring its own.

Watch out for stray `npm` on your `PATH` (nvm, an apt-installed Node,
etc.): if the source tarball wasn't built with `make dist-vendored` (no
`frontend/dist/.vendored` marker), `configure` will try to use whatever
`npm` it finds instead of failing loudly, and an incompatible one (e.g. too
old for this project's Vite version) will fail the build in a way that has
nothing to do with the recipe itself.
