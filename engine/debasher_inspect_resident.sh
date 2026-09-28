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
#
# Prints, as one JSON object, what one node of a resident program keeps in
# its execdir: its checkpoints, its input log, its halted marker and its
# node info file, and, for a launcher node, the state of its batch runs. It
# only reads: it writes nothing, takes no lock and sends nothing to the
# node, so it works the same on a live program as on a stopped one.
#
# This script finds the node in its program, and the state of its task;
# debasher_inspect_node reads its files.
#
# Exit codes: 0 once it has printed; 1 is a usage or setup error (bad
# arguments, a directory that is not a resident program's, a process or a
# task index that it refuses, an epoch that the node does not retain, and
# the like).

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_lib_resident_tools || exit 1

########
print_desc()
{
    echo "debasher_inspect_resident prints what a node of a resident program keeps"
    echo "type \"debasher_inspect_resident --help\" to get usage information"
}

########
usage()
{
    echo "debasher_inspect_resident -d <string> -p <string> [-t <int>] <command>"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name"
    echo "-t <int>                  Index of task array for process"
    echo "--help                    Display this help and exit"
    echo ""
    echo "Commands:"
    echo "summary                   The state of the node, and the figures that"
    echo "                          warn of a coming failure"
    echo "checkpoint <int>          The checkpoint of an epoch that the node retains"
    echo "log [--port <string>] [--last <int>]"
    echo "                          The latest records of the input log (100 by"
    echo "                          default), or of one port"
    echo "runs                      The batch runs of a launcher node"
}

########
read_pars()
{
    d_given=0
    p_given=0
    t_given=0
    command_args=()
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
                      processname=$1
                      p_given=1
                  fi
                  ;;
            "-t") shift
                  if [ $# -ne 0 ]; then
                      task_idx=$1
                      t_given=1
                  fi
                  ;;
            *) # The command and its own arguments, which debasher_inspect_node
               # checks
               command_args=("$@")
               break
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

    if [ ${p_given} -eq 0 ]; then
        echo "Error! -p parameter not given!" >&2
        exit 1
    fi

    if [ ${t_given} -eq 1 ] && [[ ! "${task_idx}" =~ ^[0-9]+$ ]]; then
        echo "Error! -t must be a task index" >&2
        exit 1
    fi

    if [ ${#command_args[@]} -eq 0 ]; then
        echo "Error! no command given (summary, checkpoint, log or runs)" >&2
        exit 1
    fi
}

########
# Echoes the node of process $2 that -t names: the process itself, or
# <process>:<idx> for a task of an array process (see
# debasher::_resident_tool_node_processname). Returns 1, with an error, if
# -t is missing for an array process, given for any other, or not below its
# number of tasks.
node_of_process()
{
    local absdirname=$1
    local processname=$2

    local num_tasks
    num_tasks=$(debasher::_resident_tool_num_tasks_of_process "${absdirname}" "${processname}" "$(debasher::_resident_tool_now_secs)") || return 1

    if [ "${num_tasks}" -eq 1 ]; then
        if [ ${t_given} -eq 1 ]; then
            echo "Error: ${processname} is not an array process, -t does not apply" >&2
            return 1
        fi
        echo "${processname}"
        return 0
    fi

    if [ ${t_given} -eq 0 ]; then
        echo "Error: ${processname} is an array process of ${num_tasks} tasks: -t has to name one" >&2
        return 1
    fi
    if [ "${task_idx}" -ge "${num_tasks}" ]; then
        echo "Error: ${processname} has ${num_tasks} tasks, there is no task ${task_idx}" >&2
        return 1
    fi
    echo "${processname}:${task_idx}"
}

########
# Echoes the state of the task of node $2, from its own .id and .finished,
# the files that debasher_status reads for a whole process: alive while the
# process in its .id exists, otherwise finished with a .finished, down with
# an .id and no .finished, and not_launched with no .id yet.
task_state_of_node()
{
    local absdirname=$1
    local node=$2

    local id_file=$(debasher::_resident_tool_node_id_filename "${absdirname}" "${node}")
    local finished_file=$(debasher::_resident_tool_node_finished_filename "${absdirname}" "${node}")

    if [ -f "${id_file}" ]; then
        local id
        id=$("${CAT}" "${id_file}")
        if debasher::_id_exists "$(debasher::_get_global_id "${id}")"; then
            echo "alive"
            return 0
        fi
    fi
    if [ -f "${finished_file}" ]; then
        echo "finished"
    elif [ -f "${id_file}" ]; then
        echo "down"
    else
        echo "not_launched"
    fi
}

########
inspect_resident_node()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    debasher::_resident_tool_load_program "${absdirname}" debasher_inspect_resident || return 1

    if [ -z "${DEBASHER_PROGRAM_PROCESSES[${processname}]+x}" ]; then
        echo "Error: the program in ${dirname} has no process ${processname}" >&2
        return 1
    fi

    local role
    role=$(debasher::_classify_resident_process_role "${processname}") || return 1
    if [ "${role}" = "supervisor" ]; then
        echo "Error: ${processname} is the Supervisor, which keeps no node state: what it knows is in its log (debasher_get_sched_out)" >&2
        return 1
    fi

    local script_file=$(debasher::_get_script_filename "${absdirname}" "${processname}")
    if [ ! -f "${script_file}" ]; then
        echo "Error: ${processname} was never launched in ${dirname}" >&2
        return 1
    fi

    local node
    node=$(node_of_process "${absdirname}" "${processname}") || return 1
    local idx=$(debasher::_resident_tool_node_task_idx "${node}")

    local -a task_opt=()
    if [ -n "${idx}" ]; then
        task_opt=(--task-idx "${idx}")
    fi

    "${debasher_libexecdir}"/debasher_inspect_node \
        --process "${processname}" \
        "${task_opt[@]}" \
        --task-state "$(task_state_of_node "${absdirname}" "${node}")" \
        --execdir "$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")" \
        --process-outdir "$(debasher::_get_process_outdir_given_dirname "${absdirname}" "${processname}")" \
        --debasher-status "${debasher_bindir}/debasher_status" \
        "${command_args[@]}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

inspect_resident_node "${pdir}"

exit $?
