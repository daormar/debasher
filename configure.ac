#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.71])
AC_INIT([debasher],[1.0],[daniel.ortiz@ub.edu])
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

# Extract BASH major and minor versions
if test -n "$BASH_VERSION"; then
   AC_MSG_CHECKING(for a bash shell with version >= 4.3)
   # Extract major and minor version numbers from BASH_VERSION
   bash_major_version=$(echo "$BASH_VERSION" | cut -d'.' -f1)
   bash_minor_version=$(echo "$BASH_VERSION" | cut -d'.' -f2)
   if (( bash_major_version < 4 || (bash_major_version == 4 && bash_minor_version < 3) )); then
      AC_MSG_ERROR([bash version 4.3 or above is required])
   else
      AC_MSG_RESULT(yes)
   fi
fi

# Check conda (conda is defined as a function so AC_PATH_PROGS may be
# inadequate for checking)
AC_MSG_CHECKING(for conda)
if command -v conda > /dev/null 2>&1; then
  AC_MSG_RESULT(yes)
else
  if ! test -z "$_CONDA_EXE"; then
    AC_MSG_RESULT(yes)
  else
    AC_MSG_RESULT(no)
    AC_MSG_WARN([conda may not be available, check that there is a working conda installation])
  fi
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

# Adds an extra argument to configure (disable schedulers)
AC_MSG_CHECKING(whether to disable job schedulers)
AC_ARG_ENABLE(schedulers,[  --disable-schedulers   disable job schedulers], disable_schedulers=yes,
              disable_schedulers=no)

# Yes, schedulers are enabled
if test "$disable_schedulers" = "yes"; then
   AC_MSG_RESULT(yes)
else
   AC_MSG_RESULT(no)
fi
AC_SUBST(DISABLE_SCHEDULERS,$disable_schedulers)

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
    ])
  ])
])
dnl INSTALL_FRONTEND: a web/ directory should end up installed, whether
dnl built fresh (BUILD_FRONTEND, below) or copied from a prebuilt
dnl frontend/dist/ already present in the source tree.
AM_CONDITIONAL([INSTALL_FRONTEND], [test "x$enable_frontend" != xno])
dnl BUILD_FRONTEND: npm is available, so frontend/dist/ should be
dnl (re)built from source rather than installed as-is.
AM_CONDITIONAL([BUILD_FRONTEND], [test -n "$NPM"])

AC_CONFIG_FILES([Makefile m4/Makefile engine/Makefile api/Makefile frontend/Makefile doc/Makefile data/Makefile data/programs/Makefile data/webui_programs/Makefile data/conda_envs/Makefile test/Makefile test/engine/Makefile test/api/Makefile])
AC_OUTPUT
