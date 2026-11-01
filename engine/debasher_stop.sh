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
    echo "debasher_stop stops program execution"
    echo "type \"debasher_stop --help\" to get usage information"
}

########
usage()
{
    echo "debasher_stop             -d <string> [-p <string>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name to be stopped"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    p_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 0
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-p") shift
                  if [ $# -ne 0 ]; then
                      given_processname=$1
                      p_given=1
                  fi
                  ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${d_given} -eq 0 ]; then
        echo "Error! -d parameter not given!" >&2
        exit 1
    else
        if [ ! -d "${pdir}" ]; then
            echo "Error! program directory does not exist" >&2
            exit 1
        fi

        if [ ! -f "${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}" ]; then
            echo "Error! ${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME} file is missing" >&2
            exit 1
        fi
    fi
}

########
# Stops one process of the run in the output directory absdirname: a process
# in progress is stopped through the scheduler of the run; of one that is
# not running, the built-in scheduler ends what a task that ended without
# returning from its process function may have left in its process group
# (background jobs, mirror taps). Prints the status of the process and its
# ids, and returns 1 when the stop failed.
stop_process_of_run()
{
    local absdirname=$1
    local processname=$2

    local status=$(debasher::_get_process_status "${absdirname}" "${processname}")

    # The ids of the tasks that may still run: the id of a task that has
    # ended may name another process by now
    local ids_info
    ids_info=$(debasher::_read_ids_of_unfinished_tasks "${absdirname}" "${processname}")

    if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        echo "PROCESS: ${processname} ; STATUS: ${status} ; SCHED_IDS: ${ids_info} (Stopping...)"
        debasher::_stop_process "${ids_info}"
    else
        echo "PROCESS: ${processname} ; STATUS: ${status} ; SCHED_IDS: ${ids_info} (The process is not running)"
        if [ "$(debasher::_get_scheduler)" = "${DEBASHER_BUILTIN_SCHEDULER}" ]; then
            debasher::_builtin_sched_stop_process "${ids_info}"
        fi
    fi
}

########
# Stops the run in the output directory, or only the process given with -p.
# Returns 1 when the run could not be read or a stop failed, after trying
# every process.
stop_run()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    # The processes and the scheduler of the run, as the run left them in
    # the output directory: the module is not loaded, since it may have
    # changed since the run, and nothing here depends on where the output
    # directory was when the program ran
    debasher::_read_run_for_tool "${absdirname}" "${given_processname:-}" || return 1

    # Stop the debasher_exec of the run first, if it still runs, so that it
    # launches nothing once its processes are stopped. Not when a single
    # process is stopped: the rest of the program goes on
    if [ ${p_given} -eq 0 ]; then
        debasher::_stop_run_scheduler "${absdirname}" || return 1
    fi

    local exit_code=0
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        if [ ${p_given} -eq 1 ] && [ "${given_processname}" != "${processname}" ]; then
            continue
        fi
        stop_process_of_run "${absdirname}" "${processname}" || exit_code=1
    done

    return ${exit_code}
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

stop_run "${pdir}"

exit $?
