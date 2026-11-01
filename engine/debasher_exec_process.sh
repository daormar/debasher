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
. "${debasher_pkglibdir}"/debasher_lib || exit 1

########
print_desc()
{
    echo "debasher_exec_process executes a program process"
    echo "Usage: debasher_exec_process [-q] <prgfile> <processname> [-- [<process_opts>] ]"
    echo "Notes: if \`[-- [<process_opts>] ]\` is not given, the tool shows process information and exits"
    echo "       a relative <prgfile> is looked for in the current directory and then in the directories of DEBASHER_MOD_DIR"
    echo "       -q drops the progress messages of the tool, so that the standard error holds only what the"
    echo "       module and the process write, and errors"
    echo "       when the process is executed, the tool exits with the status of the process function"
}

########
# Prints a progress message of the tool on the standard error, unless -q
# was given
_exec_process_progress()
{
    if [ "${_exec_process_quiet}" -eq 0 ]; then
        echo "$@" >&2
    fi
}

########

_exec_process_quiet=0
if [ "${1:-}" = "-q" ]; then
    _exec_process_quiet=1
    DEBASHER_QUIET_MODULE_LOADING=1
    shift
fi

if [ $# -lt 2 ]; then
    print_desc
    exit 1
fi

# Read parameters, resolving the program file to an absolute path (it
# may be found through DEBASHER_MOD_DIR)
pfile=$(debasher::_resolve_pfile "$1") || exit 1
shift
processname=$1
shift

_exec_process_progress "Loading debasher modules..."
debasher::load_debasher_module "${pfile}" || exit 1
_exec_process_progress ""

_exec_process_progress "Executing program function given in module..."
# A program that does not prepare would stop a run before it launches
# anything, so a process test of it does not pass either
debasher::_exec_program_func_for_module "${pfile}" >&2 || {
    echo "Error: the _program method of ${pfile} failed" >&2
    exit 1
}
_exec_process_progress ""

# Only a process or a sequential process of the program is run: any other
# name, such as that of a function of the module or of the engine, is
# refused. A sequential process is accepted, since its function is what a
# step runs, and this is the only way to run it on its own
if [[ -v 'DEBASHER_SEQ_PROCESSES["${processname}"]' ]]; then
    if [ $# -eq 0 ]; then
        echo "${processname} is a sequential process of the program, which has no options"
        exit 0
    fi
elif [[ ! -v 'DEBASHER_PROGRAM_PROCESSES["${processname}"]' ]]; then
    echo "Error: ${processname} is neither a process nor a sequential process of the program: give the full name of one of them, as the program adds it" >&2
    exit 1
fi

if [ $# -eq 0 ]; then
    _exec_process_progress "Showing documentation for process ${processname}..."
    showmeths=0
    showmethswithcode=0
    showvars=0
    showvarswithvalues=0
    showopts=1
    showopthnd=0
    showimpl=0
    showspecs=0
    debasher::_show_process_documentation "${processname}" "${showmeths}" "${showmethswithcode}" "${showvars}" "${showvarswithvalues}" "${showopts}" "${showopthnd}" "${showimpl}" "${showspecs}"
else
    if [ "$1" = "--" ]; then
        shift
        _exec_process_progress "Executing: ${processname} $*"
        # The status of the process function, so that a caller (such as a
        # process test) can tell one failure of the process from another
        "${processname}" "$@"
        exit $?
    else
        print_desc >&2
        exit 1
    fi
fi
