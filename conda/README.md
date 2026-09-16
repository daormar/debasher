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

No autoconf/automake/libtool either: the dist tarball already ships the
generated `configure` script and `Makefile.in` files (`EXTRA_DIST` in the
root `Makefile.am`), so plain `make` is enough.

## Cutting a release for this recipe

1. From a clean checkout, at the commit/tag you're releasing:
   ```bash
   ./reconf && ./configure && make dist-vendored
   ```
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

```bash
mamba create -n bioconda-test -c conda-forge -c bioconda conda-build bioconda-utils -y
conda activate bioconda-test
# swap source: url: for a local "url: file:///path/to/debasher-<version>.tar.gz"
# with a matching sha256 first, since the real release asset won't exist yet
conda-build conda/ --croot /tmp/cbuild -c conda-forge --override-channels
```

Watch out for stray `npm` on your `PATH` (nvm, an apt-installed Node,
etc.): if the source tarball wasn't built with `make dist-vendored` (no
`frontend/dist/.vendored` marker), `configure` will try to use whatever
`npm` it finds instead of failing loudly, and an incompatible one (e.g. too
old for this project's Vite version) will fail the build in a way that has
nothing to do with the recipe itself.
