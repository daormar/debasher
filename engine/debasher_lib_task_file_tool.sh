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

########################################
# THE TOOLS THAT SHOW A FILE OF A TASK #
########################################

# debasher_get_stdout and debasher_get_sched_out are one tool that shows a
# file of a process or of a task of an array, the standard output of its
# process function or the log that the scheduler wrote for it. Each calls
# debasher::_task_file_tool with the kind of file. The path of the file
# depends only on the output directory, the process and the task, not on
# the scheduler of the run, which is therefore not read.

# The kinds of file
DEBASHER_TASK_FILE_KIND_STDOUT="stdout"
DEBASHER_TASK_FILE_KIND_SCHED_OUT="sched_out"

########
# Prints the name of the tool that shows the given kind of file
debasher::_task_file_tool_name()
{
    local kind=$1

    case "${kind}" in
        "${DEBASHER_TASK_FILE_KIND_STDOUT}") echo "debasher_get_stdout" ;;
        "${DEBASHER_TASK_FILE_KIND_SCHED_OUT}") echo "debasher_get_sched_out" ;;
    esac
}

########
# Prints what the given kind of file holds, as the texts of the tool say it
debasher::_task_file_kind_desc()
{
    local kind=$1

    case "${kind}" in
        "${DEBASHER_TASK_FILE_KIND_STDOUT}") echo "stdout" ;;
        "${DEBASHER_TASK_FILE_KIND_SCHED_OUT}") echo "scheduler output" ;;
    esac
}

########
debasher::_task_file_tool_print_desc()
{
    local kind=$1
    local toolname=$(debasher::_task_file_tool_name "${kind}")

    echo "${toolname} gets $(debasher::_task_file_kind_desc "${kind}") for a given process"
    echo "type \"${toolname} --help\" to get usage information"
}

########
debasher::_task_file_tool_usage()
{
    local kind=$1
    local toolname=$(debasher::_task_file_tool_name "${kind}")

    printf "%-26s-d <string> -p <string> [-t <int>]\n" "${toolname}"
    echo "                          [--watch] [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name whose $(debasher::_task_file_kind_desc "${kind}") should be displayed"
    echo "-t <int>                  Index of task array for process"
    echo "--watch                   Follow the file as it grows (tail -f) instead of"
    echo "                          printing its current contents and exiting"
    echo "--help                    Display this help and exit"
}

########
# Prints the file of the given kind of the process, or of its task when an
# index is given, in the output directory
debasher::_get_task_file_name()
{
    local kind=$1
    local absdirname=$2
    local process=$3
    local task_idx=$4

    # A process with a single task has one file, named after the process;
    # each task of an array has its own
    local opt_array_size=1
    if [ -n "${task_idx}" ]; then
        opt_array_size=2
    fi

    case "${kind}" in
        "${DEBASHER_TASK_FILE_KIND_STDOUT}")
            debasher::_get_process_stdout_filename "${absdirname}" "${process}" "${opt_array_size}" "${task_idx}"
            ;;
        "${DEBASHER_TASK_FILE_KIND_SCHED_OUT}")
            debasher::_get_process_schedout_filename "${absdirname}" "${process}" "${opt_array_size}" "${task_idx}"
            ;;
    esac
}

########
# The tool that shows the file of the given kind of a process or a task:
# reads the options in "$@", and prints the file, or follows it with
# --watch. Returns 1 when the options are wrong or the file is missing.
debasher::_task_file_tool()
{
    local kind=$1
    shift

    if [ $# -eq 0 ]; then
        debasher::_task_file_tool_print_desc "${kind}"
        return 1
    fi

    local pdir="" process="" task_idx="" watch=0
    local d_given=0 p_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") debasher::_task_file_tool_usage "${kind}"
                      return 0
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-p") shift
                  if [ $# -ne 0 ]; then
                      process=$1
                      p_given=1
                  fi
                  ;;
            "-t") shift
                  if [ $# -ne 0 ]; then
                      task_idx=$1
                  fi
                  ;;
            "--watch") watch=1
                       ;;
        esac
        shift
    done

    if [ ${d_given} -eq 0 ]; then
        echo "Error! -d parameter not given!" >&2
        return 1
    fi
    if [ ! -d "${pdir}" ]; then
        echo "Error! program directory does not exist" >&2
        return 1
    fi
    if [ ! -f "${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}" ]; then
        echo "Error! ${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME} file is missing" >&2
        return 1
    fi
    if [ ${p_given} -eq 0 ]; then
        echo "Error! -p parameter not given!" >&2
        return 1
    fi

    # The file is found in the given output directory, so neither the
    # program file nor where the output directory was when the program ran
    # matter
    local absdirname=$(debasher::_get_absolute_path "${pdir}")
    local fname=$(debasher::_get_task_file_name "${kind}" "${absdirname}" "${process}" "${task_idx}")
    if [ ! -f "${fname}" ]; then
        echo "Error: $(debasher::_task_file_kind_desc "${kind}") file for process ${process} could not be found!" >&2
        return 1
    fi

    if [ ${watch} -eq 1 ]; then
        "${TAIL}" -f "${fname}"
    else
        "${CAT}" "${fname}"
    fi
}
