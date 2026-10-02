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

# Bash library that a process test (a bats test of the business logic of
# one process of a program, run by debasher_test) loads with
# `load "${DEBASHER_BATS_HELPERS}"`. It is sourced into the shell of the
# test, so it defines functions, and sets no variables of its own.

# A process test tells the standard error of a process from its output
# with `run --separate-stderr`, a flag of bats 1.5.0, which warns about it
# unless the tests declare that they need that version
bats_require_minimum_version 1.5.0

########
# Runs the process `processname` of the program file DEBASHER_TEST_PFILE,
# on its own and outside any run, with the options that follow, as
# debasher_exec_process does: its standard output and standard error are
# those of the process, and its status is that of the process function.
debasher_process()
{
    if [ -z "${DEBASHER_TEST_PFILE:-}" ]; then
        echo "debasher_process: DEBASHER_TEST_PFILE is not set: run the tests with debasher_test, or set it to the program file" >&2
        return 1
    fi
    if [ $# -lt 1 ]; then
        echo "Usage: debasher_process <processname> [<process_opts>]" >&2
        return 1
    fi

    local processname=$1
    shift
    debasher_exec_process -q "${DEBASHER_TEST_PFILE}" "${processname}" -- "$@"
}

########
# Skips the test, with the reason, when the conda environment `env_name`
# (a name, or an absolute path) does not exist on this machine, so that a
# test of a process that activates it is skipped rather than failed where
# conda or the environment is missing. The conda executable is the one
# that the conda shell functions point to (CONDA_EXE), or else the one that
# configure found, which debasher_test exports as DEBASHER_CONDA.
debasher_skip_without_conda_env()
{
    local env_name=$1
    local conda_exe=${CONDA_EXE:-${DEBASHER_CONDA:-}}

    if [ -z "${conda_exe}" ] || [ ! -f "${conda_exe}" ] || [ ! -x "${conda_exe}" ]; then
        skip "conda was not found"
    fi
    if ! "${conda_exe}" env list 2> /dev/null \
            | awk -v env="${env_name}" '$1 == env || $NF == env { found = 1 } END { exit !found }'; then
        skip "the conda environment ${env_name} does not exist"
    fi
}
