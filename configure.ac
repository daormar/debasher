#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.71])
AC_INIT([debasher],[2.0.dev0],[daniel.ortiz@ub.edu])
AC_CONFIG_MACRO_DIR([m4])
AM_INIT_AUTOMAKE([foreign subdir-objects])
AM_PATH_PYTHON([3])

# Checks for programs.
AC_PATH_PROGS(PYTHON, python)
AC_PATH_PROGS(RSCRIPT, Rscript)
AC_PATH_PROGS(PERL, perl)
AC_PATH_PROGS(GROOVY, groovy)
AC_PATH_PROGS(ECHO, echo)
AC_PATH_PROGS(SPLIT, split)
AC_PATH_PROGS(CAT, cat)
AC_PATH_PROGS(CP, cp)
AC_PATH_PROGS(RM_CMD, rm)
AC_PATH_PROGS(MV, mv)
AC_PATH_PROGS(CUT, cut)
AC_PATH_PROGS(SED, sed)
AC_PATH_PROGS(TR, tr)
AC_PATH_PROGS(GREP, grep)
AC_PATH_PROGS(UNIQ, uniq)
AC_PATH_PROGS(HEAD, head)
AC_PATH_PROGS(TAIL, tail)
AC_PATH_PROGS(DIFF, diff)
AC_PATH_PROGS(FIND, find)
AC_PATH_PROGS(LN, ln)
AC_PATH_PROGS(WC, wc)
AC_PATH_PROGS(BASENAME, basename)
AC_PATH_PROGS(DIRNAME, dirname)
AC_PATH_PROGS(REALPATH, realpath)
AC_PATH_PROGS(MKDIR, mkdir)
AC_PATH_PROGS(MKTEMP, mktemp)
AC_PATH_PROGS(MKFIFO, mkfifo)
AC_PATH_PROGS(FLOCK, flock)
AC_PATH_PROGS(TEE, tee)
AC_PATH_PROGS(GZIP, gzip)
AC_PATH_PROGS(SLEEP, sleep)
AC_PATH_PROGS(TIMEOUT, timeout gtimeout)
AC_PATH_PROGS(SEQ, seq)
AC_PATH_PROGS(SSH, ssh)

# Slurm tool names: resolved via PATH at *run* time (engine/debasher_lib_sched.sh
# and debasher_lib_sched_slurm.sh use "command -v" on these, not a baked-in
# absolute path), since a package built in one place (e.g. a bioconda build
# sandbox with no Slurm at all) may run on a cluster whose Slurm installation
# lives somewhere else entirely. Baking whatever path (if any) happened to be
# on the build machine would be wrong, not just unhelpful, for a relocatable
# package.
SBATCH="sbatch"
SRUN="srun"
SCANCEL="scancel"
SQUEUE="squeue"
SACCT="sacct"
SCONTROL="scontrol"
AC_SUBST(SBATCH)
AC_SUBST(SRUN)
AC_SUBST(SCANCEL)
AC_SUBST(SQUEUE)
AC_SUBST(SACCT)
AC_SUBST(SCONTROL)

AC_PATH_PROGS(WGET, wget)
AC_PATH_PROGS(PANDOC, pandoc)
AC_PATH_PROGS(JAVA, java)

# Unit-testing tools (optional: their absence only skips that part of
# `make check`, it never fails the build)
AC_PATH_PROGS(BATS, bats)
AM_CONDITIONAL([HAVE_BATS], [test -n "$BATS"])
# The Python suites need the dependencies of the API (api/requirements.txt,
# pydantic 2 among them), which usually live in a virtual environment: its
# pytest is given with ./configure PYTEST=<venv>/bin/pytest, or found first
# on the PATH when the environment is activated for ./configure.
AC_ARG_VAR([PYTEST], [pytest to run the Python test suites with, e.g. that of the virtual environment of api/README.md])
AC_PATH_PROGS(PYTEST, pytest)
AM_CONDITIONAL([HAVE_PYTEST], [test -n "$PYTEST"])

# BASH may already be set in the shell, if the admin then changes the
# the /bin/sh symlink to a non-bash shell, then the installation will
# break
unset BASH
AC_PATH_PROGS(BASH, bash, "no", [$PATH:/bin:/usr/bin:/usr/sbin])
if test x$BASH = "xno"; then
    AC_MSG_ERROR([bash is required])
fi

# Check the version of the bash found above, which runs every script of
# the package (its path is their shebang), not that of the shell running
# configure, which may be another shell or another bash
AC_MSG_CHECKING([whether $BASH is version 4.3 or newer])
bash_major_version=`"$BASH" -c 'echo "${BASH_VERSINFO[[0]]}"'`
bash_minor_version=`"$BASH" -c 'echo "${BASH_VERSINFO[[1]]}"'`
if test "$bash_major_version" -lt 4 || { test "$bash_major_version" -eq 4 && test "$bash_minor_version" -lt 3; }; then
   AC_MSG_RESULT([no, $bash_major_version.$bash_minor_version])
   AC_MSG_ERROR([bash version 4.3 or above is required; put a newer bash first in the PATH])
else
   AC_MSG_RESULT([yes, $bash_major_version.$bash_minor_version])
fi

# Check conda: its executable, from which debasher::conda_activate loads
# the shell functions of conda when a shell does not have them. It is the
# one given with ./configure CONDA_CMD=..., or else the one that the conda
# shell functions of this shell point to (CONDA_EXE, or _CONDA_EXE in
# older versions), or else the first conda program in the PATH. conda
# itself is usually a shell function, which a program search cannot see.
# The variable is not called CONDA, which some environments (the runners
# of GitHub Actions) set to the directory where conda is installed.
AC_ARG_VAR([CONDA_CMD], [conda executable, from which processes load the shell functions of conda])
if test -z "$CONDA_CMD"; then
  for conda_candidate in "$CONDA_EXE" "$_CONDA_EXE"; do
    if test -n "$conda_candidate" && test -f "$conda_candidate" && test -x "$conda_candidate"; then
      CONDA_CMD=$conda_candidate
      break
    fi
  done
fi
AC_PATH_PROGS(CONDA_CMD, conda)
if test -n "$CONDA_CMD" && ! { test -f "$CONDA_CMD" && test -x "$CONDA_CMD"; }; then
  AC_MSG_WARN([$CONDA_CMD is not a conda executable, ignored])
  CONDA_CMD=
fi
if test -z "$CONDA_CMD"; then
  AC_MSG_WARN([conda was not found: a process cannot activate a conda environment; give it with ./configure CONDA_CMD=<conda executable>])
fi

# Check that docker is available
unset DOCKER
AC_PATH_PROGS(DOCKER, docker, "no")
if test x$DOCKER = "xno"; then
    AC_MSG_WARN([docker is required])
fi

# Check that dot (from graphviz) is available
unset DOT
AC_PATH_PROGS(DOT, dot, "no")
if test x$DOT = "xno"; then
    AC_MSG_ERROR([graphviz library is required])
fi

# Search awk

## GAWK
AC_PATH_PROG(GAWK, gawk, no)
if test "$GAWK" = no; then

   ## NAWK
   AC_PATH_PROG(NAWK, nawk, no)
   if test "$NAWK" = no; then

        ## MAWK
	AC_PATH_PROG(MAWK, mawk, no)
        if test "$MAWK" = no; then
	      AWK=awk
        else
              # mawk found
              AWK=$MAWK
        fi
   else
        # nawk found
        AWK=$NAWK
   fi
else
        # gawk found
        AWK=$GAWK
fi

AC_SUBST(AWK)

AC_SUBST(USE_SOURCE_OPT)

# check awk delete array
AC_MSG_CHECKING(whether awk supports delete array )
USE_FAST_DELETE="no"
echo "" | $AWK '{ a[[1]]=1; delete a; if (a[[1]]!=0) exit (1) }' && USE_FAST_DELETE="yes"
if test ${USE_FAST_DELETE} = "yes"; then
   AC_MSG_RESULT(yes)
else
   AC_MSG_RESULT(no)
fi

AC_SUBST(USE_FAST_DELETE)

# Search sort and check parameters
AC_PATH_PROGS(SORT,sort)

echo -n "checking whether sort accepts -S <buffsize>... "
echo "" | ${SORT} -S 131072 >/dev/null 2>&1
if test $? -eq 0; then
   sortpars="-S 131072"
   echo "yes"
else
   sortpars=""
   echo "no"
fi
AC_SUBST(sortpars)

echo -n "checking whether sort accepts -T <dir>... "
echo "" | ${SORT} -T /tmp >/dev/null 2>&1
if test $? -eq 0; then
   sortT="yes"
   echo "yes"
else
   sortT="no"
   echo "no"
fi
AC_SUBST(sortT)

echo -n "checking whether sort accepts -m... "
echo "" | ${SORT} -m >/dev/null 2>&1
if test $? -eq 0; then
   sortm="yes"
   echo "yes"
else
   sortm="no"
   echo "no"
fi
AC_SUBST(sortm)


# Checks for doxygen
AC_PATH_PROG(DOXYGEN,doxygen)

AC_ARG_ENABLE([frontend],
  [AS_HELP_STRING([--disable-frontend], [do not build/install the React Flow web interface])],
  [enable_frontend=$enableval], [enable_frontend=yes])

dnl A prebuilt frontend/dist/ present in the source tree means this is a
dnl "make dist-vendored" release tarball (see the root Makefile.am and
dnl frontend/Makefile.am's dist-hook): always prefer installing that
dnl as-is over probing for npm, so the build is deterministic regardless
dnl of whatever npm (if any, and whatever version) happens to be on the
dnl PATH of the machine building the package, e.g. a bioconda build,
dnl which has no network access and shouldn't need npm at all.
AS_IF([test "x$enable_frontend" != xno], [
  AS_IF([test -f "$srcdir/frontend/dist/.vendored"], [
    AC_MSG_NOTICE([a prebuilt frontend/dist/ is present: installing it as-is, without invoking npm])
  ], [
    AC_PATH_PROG([NPM], [npm])
    AS_IF([test -z "$NPM"], [
      AC_MSG_WARN([npm not found and no prebuilt frontend/dist/ present; skipping frontend])
      enable_frontend=no
    ], [
      dnl npm runs under whatever node comes first in the PATH when make
      dnl runs (its "#!" line is "env node"), not the one it was installed
      dnl with, as when nvm installs a Node.js that is not the default one
      dnl of the shell. Find the node next to npm first, and have the
      dnl frontend's Makefile put its directory first in the PATH of every
      dnl npm command, so that the build does not depend on the PATH of the
      dnl shell that runs make. A NODE given to configure is kept.
      npm_bindir=`AS_DIRNAME(["$NPM"])`
      AC_PATH_PROG([NODE], [node], [], [$npm_bindir$PATH_SEPARATOR$PATH])
      AS_IF([test -z "$NODE"], [
        AC_MSG_ERROR([npm was found, but no node; give NODE=/path/to/node, or --disable-frontend])
      ])
      dnl The oldest Node.js that the build and the tests of the frontend
      dnl run on: vite asks for 20.19 or 22.12 and newer, and vitest, which
      dnl make check runs, for 22.12 and newer.
      node_min_version=22.12
      AC_MSG_CHECKING([whether $NODE is Node.js $node_min_version or newer])
      AS_IF(["$NODE" -e '
          const [[major, minor]] = process.versions.node.split(".").map(Number);
          const [[min_major, min_minor]] = process.argv[[1]].split(".").map(Number);
          process.exit(major > min_major || (major === min_major && minor >= min_minor) ? 0 : 1);
        ' "$node_min_version" >/dev/null 2>&1], [
        AC_MSG_RESULT([yes])
      ], [
        AC_MSG_RESULT([no, `"$NODE" --version 2>/dev/null`])
        AC_MSG_ERROR([the frontend needs Node.js $node_min_version or newer; put one first in the PATH, give NODE=/path/to/node, or --disable-frontend])
      ])
      NODE_BINDIR=`AS_DIRNAME(["$NODE"])`
    ])
  ])
])
AC_SUBST([NODE_BINDIR])
dnl INSTALL_FRONTEND: a web/ directory should end up installed, whether
dnl built fresh (BUILD_FRONTEND, below) or copied from a prebuilt
dnl frontend/dist/ already present in the source tree.
AM_CONDITIONAL([INSTALL_FRONTEND], [test "x$enable_frontend" != xno])
dnl BUILD_FRONTEND: npm is available, so frontend/dist/ should be
dnl (re)built from source rather than installed as-is.
AM_CONDITIONAL([BUILD_FRONTEND], [test -n "$NPM"])

AC_CONFIG_FILES([Makefile m4/Makefile engine/Makefile api/Makefile frontend/Makefile doc/Makefile data/Makefile data/programs/Makefile data/webui_programs/Makefile data/conda_envs/Makefile test/Makefile test/engine/Makefile test/api/Makefile])
AC_OUTPUT
