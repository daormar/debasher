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

########
print_desc()
{
    echo "debasher_test runs the business tests of a program"
    echo "Usage: debasher_test <prgdir>"
    echo "Notes: <prgdir> is a program directory: a directory whose base name is <name> and that holds the"
    echo "       program file <name>.sh; its tests are in <prgdir>/test, the files *.bats (run with bats) and"
    echo "       test_*.py (run with pytest)"
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
name=$("${BASENAME}" "${prgdir}")
pfile="${prgdir}/${name}.sh"
if [ ! -f "${pfile}" ]; then
    fail_to_run "${prgdir} is not a program directory: it has no program file ${name}.sh"
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
# the engine (those of libexec for the node harness) and its Python
# modules. Nothing is written into the program directory: pytest runs
# without its cache and without bytecode
export DEBASHER_TEST_PFILE="${pfile}"
export DEBASHER_BATS_HELPERS="${debasher_pkglibdir}/debasher_bats_helpers"
export PATH="${debasher_bindir}:${PATH}"
export DEBASHER_LIBEXECDIR="${debasher_libexecdir}"
export PYTHONPATH="${debasher_pythondir}:${debasher_pkgpythondir}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1

cd "${prgdir}" || fail_to_run "cannot change to ${prgdir}"

status=0
if [ ${#bats_files[@]} -gt 0 ]; then
    "${bats_tool}" "${bats_files[@]}" || status=1
fi
if [ ${#pytest_files[@]} -gt 0 ]; then
    "${pytest_tool}" -p no:cacheprovider "${pytest_files[@]}" || status=1
fi
exit ${status}
