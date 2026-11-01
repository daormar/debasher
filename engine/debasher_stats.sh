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
    echo "debasher_stats gets statistics about program processes"
    echo "type \"debasher_stats --help\" to get usage information"
}

########
usage()
{
    echo "debasher_stats            -d <string> [-p <string>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name whose statistics should be obtained"
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
# Prints the status and the elapsed time of each process of the run in the
# output directory, or of the one given with -p
print_stats_of_run()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    # The processes and the scheduler of the run, as the run left them in
    # the output directory: the module is not loaded, since it may have
    # changed since the run, and nothing here depends on where the output
    # directory was when the program ran
    debasher::_read_run_for_tool "${absdirname}" "${given_processname:-}" || return 1

    # Iterate over the program processes
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        # Only the process given with -p, if any
        if [ ${p_given} -eq 1 ] && [ "${given_processname}" != "${processname}" ]; then
            continue
        fi

        # Check process status
        local status=$(debasher::_get_process_status "${absdirname}" ${processname})

        # Get elapsed time if process finished
        elapsed_time=$(debasher::_get_elapsed_time_for_process "${absdirname}" ${processname})

        # Print status
        echo "PROCESS: $processname ; STATUS: $status ; ELAPSED_TIME(s): ${elapsed_time}"
    done
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

print_stats_of_run "${pdir}"

exit $?
