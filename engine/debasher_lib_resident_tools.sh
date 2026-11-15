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

####################################
# TOOLS FOR RESIDENT PROGRAMS      #
####################################
#
# What the tools that act on a resident program from outside it share
# (debasher_stop_resident, debasher_snapshot_resident,
# debasher_reset_resident, debasher_inspect_resident): loading the program
# from its output directory, finding its nodes and its Supervisor, the
# files of a node, and writing a trigger into the control ports of every
# node. Sourced by those tools after debasher_lib, never by debasher_lib
# itself.

########
debasher::_resident_tool_now_secs()
{
    date +%s
}

########
# Waits until $1 (a file path) exists, or $2 (an epoch second) passes.
debasher::_resident_tool_wait_for_file()
{
    local path=$1
    local deadline=$2
    while [ ! -e "${path}" ]; do
        if [ "$(debasher::_resident_tool_now_secs)" -ge "${deadline}" ]; then
            return 1
        fi
        "${SLEEP}" 0.2
    done
    return 0
}

########
# Loads the program whose output directory is $1 (its module, scheduler and
# processes, into DEBASHER_PROGRAM_PROCESSES), from the command line file
# that debasher_exec left there. Returns 1, with an error naming the tool $2,
# if the program is not a resident one.
debasher::_resident_tool_load_program()
{
    local absdirname=$1
    local toolname=$2
    local command_line_file="${absdirname}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"

    local pfile
    pfile=$(debasher::_get_abspfile_from_command_line_file "${command_line_file}") || return 1
    local orig_outdir
    orig_outdir=$(debasher::_get_orig_outdir_from_command_line_file "${command_line_file}") || return 1
    if debasher::_dirnames_are_equal "${orig_outdir}" "${absdirname}"; then
        :
    else
        echo "Warning: program output directory was moved (original directory: ${orig_outdir})" >&2
    fi

    debasher::load_debasher_module "$pfile" || return 1
    debasher::_set_scheduler_of_run "${absdirname}" || return 1
    debasher::_resolve_program_type "${pfile}" || return 1

    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        echo "Error: ${pfile} is not a resident program (${toolname} is only for those)" >&2
        return 1
    fi

    debasher::_exec_program_func_for_module "${pfile}"
}

########
# A node is a process name, or <process>:<idx> for one task of an array
# process (the same identity a Supervisor's NODE_PORTS gives it). The
# functions below give the files of a node, which for a task carry its
# index the way the engine names them (<process>_<idx>.id).
debasher::_resident_tool_node_processname()
{
    echo "${1%%:*}"
}

debasher::_resident_tool_node_task_idx()
{
    case "$1" in
        *:*) echo "${1#*:}" ;;
        *) echo "" ;;
    esac
}

debasher::_resident_tool_node_id_filename()
{
    local absdirname=$1
    local node=$2
    local processname=$(debasher::_resident_tool_node_processname "${node}")
    local idx=$(debasher::_resident_tool_node_task_idx "${node}")
    if [ -z "${idx}" ]; then
        debasher::_get_processid_filename "${absdirname}" "${processname}"
    else
        debasher::_get_array_taskid_filename "${absdirname}" "${processname}" "${idx}"
    fi
}

debasher::_resident_tool_node_finished_filename()
{
    local absdirname=$1
    local node=$2
    local processname=$(debasher::_resident_tool_node_processname "${node}")
    local idx=$(debasher::_resident_tool_node_task_idx "${node}")
    if [ -z "${idx}" ]; then
        debasher::_get_process_finished_filename "${absdirname}" "${processname}"
    else
        debasher::_get_task_finished_filename "${absdirname}" "${processname}" "${idx}"
    fi
}

# The path of $3 in the process's own directory, as the node's runtime
# names it (see _get_execdir_entry in engine/debasher_runtime_transport.py):
# "<name>_<idx>" for a task, "<name>" otherwise.
debasher::_resident_tool_node_execdir_entry()
{
    local absdirname=$1
    local node=$2
    local name=$3
    local processname=$(debasher::_resident_tool_node_processname "${node}")
    local idx=$(debasher::_resident_tool_node_task_idx "${node}")
    local execdir=$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")
    if [ -z "${idx}" ]; then
        echo "${execdir}/${name}"
    else
        echo "${execdir}/${name}_${idx}"
    fi
}

########
# The number of tasks of process $2, from the script the scheduler wrote
# for it before launching any of them (its DEBASHER_NUM_TASKS line), so
# that tasks not started yet are counted too. Waits for the script until
# the deadline $3, since a program can still be starting up.
debasher::_resident_tool_num_tasks_of_process()
{
    local absdirname=$1
    local processname=$2
    local deadline=$3
    local script_file
    script_file=$(debasher::_get_script_filename "${absdirname}" "${processname}")
    if ! debasher::_resident_tool_wait_for_file "${script_file}" "${deadline}"; then
        echo "Error: ${processname} was never launched (no ${script_file})" >&2
        return 1
    fi
    local line
    while IFS= read -r line; do
        case "${line}" in
            DEBASHER_NUM_TASKS=*)
                echo "${line#DEBASHER_NUM_TASKS=}"
                return 0
                ;;
        esac
    done < "${script_file}"
    echo "Error: ${script_file} does not say how many tasks ${processname} has" >&2
    return 1
}

########
# Prints the nodes of process $2, in the output directory $1, one per line:
# the process itself if it has one task, <process>:<idx> for each task of
# one of several. Waits for its script until the deadline $3. Returns 1,
# with an error, if the script does not come or does not give the number
# of tasks.
debasher::_resident_tool_list_nodes_of_process()
{
    local absdirname=$1
    local processname=$2
    local deadline=$3

    local num_tasks
    # From the script, so that a task not started yet counts
    num_tasks=$(debasher::_resident_tool_num_tasks_of_process "${absdirname}" "${processname}" "${deadline}") || return 1
    # A process of one task is a node named by its process alone
    if [ "${num_tasks}" -eq 1 ]; then
        echo "${processname}"
        return 0
    fi
    local idx
    for (( idx = 0; idx < num_tasks; idx++ )); do
        echo "${processname}:${idx}"
    done
}

########
# Finds the Supervisor and the nodes of the program whose output directory
# is $1, among the processes of DEBASHER_PROGRAM_PROCESSES. Sets the
# variable named $4 to the process name of the Supervisor (empty if the
# program has none) and fills the array named $5 with the nodes, minus
# those in the comma-separated list $2. Waits for the script of each
# process until the deadline $3. Returns 1, with an error, on a process it
# cannot classify, on a second Supervisor, or on a script that does not
# come in time.
debasher::_resident_tool_find_supervisor_and_nodes()
{
    local absdirname=$1
    local excluded_csv=$2
    local deadline=$3
    local -n found_supervisor_ref=$4
    local -n found_nodes_ref=$5

    local -A excluded=()
    if [ -n "${excluded_csv}" ]; then
        # IFS=... read, not "local IFS=,": local only scopes a variable to
        # this function, not to the one statement that needs the comma as
        # a separator, and a leaked IFS of "," broke word-splitting in
        # every function called afterwards, including
        # debasher::_classify_resident_process_role below.
        local -a names=()
        IFS=',' read -ra names <<< "${excluded_csv}"
        local name
        for name in "${names[@]}"; do
            excluded["${name}"]=1
        done
    fi

    found_supervisor_ref=""
    found_nodes_ref=()

    local processname role process_nodes node
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        # The classifier of debasher::_validate_resident_program_processes
        role=$(debasher::_classify_resident_process_role "${processname}") || {
            echo "Error: cannot classify process ${processname} (not a resident program?)" >&2
            return 1
        }
        case "${role}" in
            supervisor)
                if [ -n "${found_supervisor_ref}" ]; then
                    echo "Error: a resident program can have at most one Supervisor process, but both ${found_supervisor_ref} and ${processname} are" >&2
                    return 1
                fi
                found_supervisor_ref="${processname}"
                ;;
            fbpprocess)
                # -x <process> leaves out every task of the process
                if [ -n "${excluded[${processname}]+x}" ]; then
                    continue
                fi
                process_nodes=$(debasher::_resident_tool_list_nodes_of_process "${absdirname}" "${processname}" "${deadline}") || return 1
                while IFS= read -r node; do
                    # -x <process>:<idx> leaves out one task
                    if [ -z "${excluded[${node}]+x}" ]; then
                        found_nodes_ref+=("${node}")
                    fi
                done <<< "${process_nodes}"
                ;;
            *)
                echo "Error: process ${processname} does not derive from FBPProcess or Supervisor" >&2
                return 1
                ;;
        esac
    done
}

########
# Returns 0 if the process of some node of the array named $2, in the
# output directory $1, is running.
debasher::_resident_tool_some_node_is_running()
{
    local absdirname=$1
    local -n running_nodes_ref=$2

    local node
    for node in "${running_nodes_ref[@]}"; do
        if debasher::_process_is_in_progress "${absdirname}" "$(debasher::_resident_tool_node_processname "${node}")"; then
            return 0
        fi
    done
    return 1
}

########
# The line of the trigger $1 (start_snapshot or shutdown), numbered with the
# epoch $2.
debasher::_resident_tool_trigger_json()
{
    local command=$1
    local epoch=$2
    echo "{\"type\": \"INTERACT\", \"payload\": {\"command\": \"${command}\", \"args\": {\"epoch\": ${epoch}}}}"
}

########
# Writes the trigger $3, numbered with the epoch $4, into every port listed
# in the control ports file of each node of the array named $2, in the
# output directory $1 (most nodes list none, see the Glossary entry
# "control ports file" of the design doc). Returns 1, with an error, on a
# node whose control ports file does not come before the deadline $5, or on
# a write that cannot be done within 5 seconds; the first error ends it,
# and the ports after it get nothing.
debasher::_resident_tool_trigger_every_node()
{
    local absdirname=$1
    local -n triggered_nodes_ref=$2
    local command=$3
    local epoch=$4
    local deadline=$5

    local trigger_json
    trigger_json=$(debasher::_resident_tool_trigger_json "${command}" "${epoch}")

    local node cp_file fifo
    for node in "${triggered_nodes_ref[@]}"; do
        cp_file=$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" control_ports)
        # A program can still be starting up when this runs
        if ! debasher::_resident_tool_wait_for_file "${cp_file}" "${deadline}"; then
            echo "Error: ${node} never wrote its control_ports file" >&2
            return 1
        fi
        while IFS= read -r fifo; do
            [ -n "${fifo}" ] || continue
            # A control port fed from outside whose node is down has no
            # reader, and the open would block for ever
            if ! "${TIMEOUT}" 5 "${BASH}" -c 'echo "$1" > "$2"' _ "${trigger_json}" "${fifo}"; then
                echo "Error: could not write the ${command} trigger to ${fifo}" >&2
                return 1
            fi
        done < "${cp_file}"
    done
}

########
# Returns 0 if node $2 has a checkpoint of the epoch $3 or of a later one:
# the round numbered $3 closed at it, or a newer round did, whose checkpoint
# is at least as recent a point to recover from. A newer round replaces an
# open one, and pruning can take the checkpoint of $3 away once newer ones
# exist.
debasher::_resident_tool_node_has_checkpoint_since()
{
    local absdirname=$1
    local node=$2
    local epoch=$3

    local checkpoints_dir
    checkpoints_dir=$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" checkpoints)
    local path name
    for path in "${checkpoints_dir}"/*.json; do
        name="${path##*/}"
        name="${name%.json}"
        if [[ "${name}" =~ ^[0-9]+$ ]] && [ "${name}" -ge "${epoch}" ]; then
            return 0
        fi
    done
    return 1
}
