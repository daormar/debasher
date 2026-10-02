# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

# *- bash -*

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 2

########
print_desc()
{
    echo "debasher_test runs the business tests of a program"
    echo "Usage: debasher_test [--conda-support] [--docker-support] <prgdir>"
    echo "Notes: <prgdir> is a program directory: a directory that holds a program and its tests; the program"
    echo "       file is <prgdir>/<name>.sh, where <name> is the name that the metadata of the web UI"
    echo "       (<prgdir>/.debasher/program.json) gives, or, without that metadata, the only *.sh file at the"
    echo "       top of <prgdir>; the tests are in <prgdir>/test, the files *.bats (run with bats) and"
    echo "       test_*.py (run with pytest)"
    echo "       --conda-support and --docker-support create the conda environments and pull the docker images"
    echo "       of the processes before the tests, as debasher_exec does before a run"
    echo "       DEBASHER_BATS and DEBASHER_PYTEST, when set, give the bats and the pytest to run instead of"
    echo "       those that configure found"
    echo "       exit status: 0 every test passed, 1 a test failed, 2 the tests could not be run, 77 no tests"
}

########
# The exit status when the program has no tests, the one with which
# Automake marks a skipped test
NO_TESTS_STATUS=77

########
# Reports an error that keeps the tests from running, and exits
fail_to_run()
{
    echo "debasher_test: $*" >&2
    exit 2
}

########

conda_support=0
docker_support=0
while [ $# -gt 1 ]; do
    case $1 in
        --conda-support)
            conda_support=1
            ;;
        --docker-support)
            docker_support=1
            ;;
        *)
            break
            ;;
    esac
    shift
done

if [ "${1:-}" = "--help" ]; then
    print_desc
    exit 0
fi

if [ $# -ne 1 ]; then
    print_desc >&2
    exit 2
fi

if [ ! -d "$1" ]; then
    fail_to_run "$1 is not a directory"
fi
prgdir=$("${REALPATH}" "$1") || fail_to_run "cannot resolve $1"

# The program file: the one that the metadata of the web UI names, the
# directory being free to have any name, or else the only *.sh file at
# the top of the directory, since other scripts may live beside it
if [ -f "$(debasher::_get_ui_program_metadata_fname "${prgdir}")" ]; then
    name=$(debasher::_get_ui_program_name "${prgdir}") \
        || fail_to_run "cannot read the name of the program from $(debasher::_get_ui_program_metadata_fname "${prgdir}")"
    pfile="${prgdir}/${name}.sh"
    if [ ! -f "${pfile}" ]; then
        fail_to_run "${prgdir} names the program ${name}, and has no program file ${name}.sh"
    fi
else
    shopt -s nullglob
    scripts=("${prgdir}"/*.sh)
    shopt -u nullglob
    case ${#scripts[@]} in
        0)
            fail_to_run "${prgdir} is not a program directory: it has no *.sh file at its top"
            ;;
        1)
            pfile=${scripts[0]}
            ;;
        *)
            names=("${scripts[@]##*/}")
            fail_to_run "${prgdir} has several *.sh files at its top (${names[*]}): cannot tell which one is the program"
            ;;
    esac
fi

# The test files, each kind in the order of its names
testdir="${prgdir}/test"
shopt -s nullglob
bats_files=("${testdir}"/*.bats)
pytest_files=("${testdir}"/test_*.py)
shopt -u nullglob
if [ ${#bats_files[@]} -eq 0 ] && [ ${#pytest_files[@]} -eq 0 ]; then
    echo "debasher_test: no tests in ${testdir}"
    exit ${NO_TESTS_STATUS}
fi

########
# Creates the conda environments and pulls the docker images of the
# processes of the program, as debasher_exec --conda-support and
# --docker-support do before a run, so that a test of a process finds
# them. The logs of conda go to a temporary directory, since there is no
# output directory, which is removed unless creating an environment failed.
prepare_environments()
{
    DEBASHER_QUIET_MODULE_LOADING=1
    debasher::load_debasher_module "${pfile}" >&2 || fail_to_run "cannot load ${pfile}"
    debasher::_exec_program_func_for_module "${pfile}" >&2 || fail_to_run "cannot define the program of ${pfile}"

    if [ ${conda_support} -eq 1 ]; then
        DEBASHER_CONDA_DIR=$("${MKTEMP}" -d -t debasher_test_conda.XXXXXX) || fail_to_run "cannot create a temporary directory"
        debasher::_prepare_conda_envs \
            || fail_to_run "cannot create the conda environments of the program (see ${DEBASHER_CONDA_DIR})"
        "${RM}" -rf "${DEBASHER_CONDA_DIR}"
    fi
    if [ ${docker_support} -eq 1 ]; then
        debasher::_pull_docker_imgs || fail_to_run "cannot pull the docker images of the program"
    fi
}

# The test tools, checked before any test runs
bats_tool=${DEBASHER_BATS:-${BATS}}
pytest_tool=${DEBASHER_PYTEST:-${PYTEST}}
if [ ${#bats_files[@]} -gt 0 ] && [ -z "${bats_tool}" ]; then
    fail_to_run "the program has bats tests, and bats was not found: set DEBASHER_BATS"
fi
if [ ${#pytest_files[@]} -gt 0 ] && [ -z "${pytest_tool}" ]; then
    fail_to_run "the program has pytest tests, and pytest was not found: set DEBASHER_PYTEST"
fi

# What the tests need: the program file, the test helpers, the tools of
# the engine (those of libexec for the node harness), the conda that
# configure found and the Python modules of the engine. Nothing is written into the program directory: pytest runs
# without its cache and without bytecode
export DEBASHER_TEST_PFILE="${pfile}"
export DEBASHER_BATS_HELPERS="${debasher_pkglibdir}/debasher_bats_helpers"
export PATH="${debasher_bindir}:${PATH}"
export DEBASHER_LIBEXECDIR="${debasher_libexecdir}"
export DEBASHER_CONDA="${CONDA_CMD}"
export PYTHONPATH="${debasher_pythondir}:${debasher_pkgpythondir}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1

if [ ${conda_support} -eq 1 ] || [ ${docker_support} -eq 1 ]; then
    prepare_environments
fi

cd "${prgdir}" || fail_to_run "cannot change to ${prgdir}"

status=0
if [ ${#bats_files[@]} -gt 0 ]; then
    "${bats_tool}" "${bats_files[@]}" || status=1
fi
if [ ${#pytest_files[@]} -gt 0 ]; then
    "${pytest_tool}" -p no:cacheprovider "${pytest_files[@]}" || status=1
fi
exit ${status}
