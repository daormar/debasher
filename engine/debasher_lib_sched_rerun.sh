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

################################################
# SCHEDULER FUNCTIONS RELATED TO PROCESS RERUN #
################################################

########
debasher::_mark_process_as_rerun()
{
    local processname=$1
    local reason=$2

    if [ "${DEBASHER_RERUN_PROCESSES[${processname}]}" = "" ]; then
        DEBASHER_RERUN_PROCESSES[${processname}]=${reason}
    else
        local curr_val="${DEBASHER_RERUN_PROCESSES[${processname}]}"
        if [[ ",$curr_val," != *",$reason,"* ]]; then
            DEBASHER_RERUN_PROCESSES[${processname}]="${curr_val},${reason}"
        fi
    fi
}

########
debasher::_num_processes_marked_as_rerun()
{
    echo "${#DEBASHER_RERUN_PROCESSES[@]}"
}

########
debasher::_there_are_processes_to_rerun()
{
    local num_procs_rerun="${#DEBASHER_RERUN_PROCESSES[@]}"

    if (( num_procs_rerun > 0 )); then
        return 0
    else
        return 1
    fi
}

########
debasher::_get_rerun_processes_as_string()
{
    local result=""
    for processname in "${!DEBASHER_RERUN_PROCESSES[@]}"; do
        if [ "${result}" = "" ]; then
            result=${processname}
        else
            result="${result},${processname}"
        fi
    done

    echo ${result}
}

########
debasher::_process_marked_as_rerun()
{
    local processname=$1

    if [ "${DEBASHER_RERUN_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        return 0
    fi
}

########
debasher::_define_rerun_processes_due_to_input_changes()
{
    # Read input parameters
    local program_opts_file=$1
    local old_program_opts_file=$2

    # Obtain processes with input change
    local changed_procs
    changed_procs=`"${debasher_libexecdir}"/debasher_compare_opts --changed "${old_program_opts_file}" "${program_opts_file}" 2>/dev/null`

    # Iterate processes with input change
    while IFS= read -r proc; do
        [ -z "$proc" ] && continue
        debasher::_mark_process_as_rerun "${proc}" "${DEBASHER_INPUT_CHANGE_RERUN_REASON}"
    done <<< "${changed_procs}"

    # Obtain new processes
    local new_procs
    new_procs=`"${debasher_libexecdir}"/debasher_compare_opts --new "${old_program_opts_file}" "${program_opts_file}" 2>/dev/null`

    # Iterate over new processes
    while IFS= read -r proc; do
        [ -z "$proc" ] && continue
        debasher::_mark_process_as_rerun "${proc}" "${DEBASHER_NEW_PROC_RERUN_REASON}"
    done <<< "${new_procs}"
}

########
debasher::_define_forced_rerun_processes()
{
    local processname
    for processname in "${!DEBASHER_FINAL_PROCESS_SPEC[@]}"; do
        # Get process spec
        local process_spec="${DEBASHER_FINAL_PROCESS_SPEC[${processname}]}"

        # Register process as forced to rerun if appliable
        local process_forced=`debasher::_extract_force_from_process_spec "$process_spec" "force"`
        if [ ${process_forced} = "yes" ]; then
            DEBASHER_FORCED_RERUN_PROCESSES+="${PROCESSNAME}"
            debasher::_mark_process_as_rerun $processname ${DEBASHER_FORCED_RERUN_REASON}
        fi
    done
}

########
debasher::_check_script_is_older_than_modules()
{
    local script_filename=$1

    # Check if script exists
    if [ -f "${script_filename}" ]; then
        # script exists
        script_older=0
        local mod
        for mod in "${!DEBASHER_PROGRAM_MODULES[@]}"; do
            fullmod="${DEBASHER_PROGRAM_MODULES[$mod]}"
            if [ "${script_filename}" -ot "${fullmod}" ]; then
                script_older=1
                echo "Warning: ${script_filename} is older than module ${fullmod}" >&2
            fi
        done
        # Return value
        if [ "${script_older}" -eq 1 ]; then
            return 0
        else
            return 1
        fi
    else
        # script does not exist
        echo "Warning: ${script_filename} does not exist" >&2
        return 0
    fi
}

########
debasher::_define_rerun_processes_due_to_code_update()
{
    # Read input parameters
    local dirname=$1

    # Read information about the processes to be executed
    local processname
    for processname in "${DEBASHER_PROGRAM_PROCESSES[@]}"; do
        # Extract process information
        local status=`debasher::_get_process_status "${dirname}" "${processname}"`
        local script_filename=`debasher::_get_script_filename "${dirname}" "${processname}"`

        # Handle checkings depending of process status
        if [ "${status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]; then
            if check_script_is_older_than_modules "${script_filename}"; then
                echo "Warning: last execution of process ${processname} used outdated modules">&2
                debasher::_mark_process_as_rerun "$processname" "${DEBASHER_OUTDATED_CODE_RERUN_REASON}"
            fi
        fi

        if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
            if check_script_is_older_than_modules "${script_filename}"; then
                echo "Warning: current execution of process ${processname} is using outdated modules">&2
            fi
        fi
    done
}

########
debasher::_define_rerun_processes_due_to_proc_status_of_fifo_user_owner()
{
    # Read input parameters
    local dirname=$1

    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        # Obtain user process name
        local fifo_user=${DEBASHER_FIFO_USERS["${augm_fifoname}"]}
        local user_procname="${fifo_user%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

        # Obtain user process status
        local user_status=`debasher::_get_process_status ${dirname} "${user_procname}"`

        # Obtain owner process name
        local fifo_owner=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
        local owner_procname="${fifo_owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

        # Obtain owner process status
        local owner_status=`debasher::_get_process_status ${dirname} "${owner_procname}"`

        # If fifo user process is finished but fifo owner is not, or viceversa, then
        # mark both processes as rerun
        if [[ "${user_status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}"  && "${owner_status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" ]]; then
            debasher::_mark_process_as_rerun "${user_procname}" "${DEBASHER_PROC_STATUS_FIFO_RERUN_REASON}"
            debasher::_mark_process_as_rerun "${owner_procname}" "${DEBASHER_PROC_STATUS_FIFO_RERUN_REASON}"
        fi

        if [[ "${user_status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}"  && "${owner_status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]]; then
            debasher::_mark_process_as_rerun "${user_procname}" "${DEBASHER_PROC_STATUS_FIFO_RERUN_REASON}"
            debasher::_mark_process_as_rerun "${owner_procname}" "${DEBASHER_PROC_STATUS_FIFO_RERUN_REASON}"
        fi
    done
}

########
debasher::_propagate_rerun_mark_due_to_fifos_iter()
{
    # Read input parameters
    local dirname=$1

    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        # Obtain user process name
        local fifo_user=${DEBASHER_FIFO_USERS["${augm_fifoname}"]}
        local user_procname="${fifo_user%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

        # Obtain owner process name
        local fifo_owner=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
        local owner_procname="${fifo_owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

        # Mark fifo owner process as rerun if the user is already marked
        if debasher::_process_marked_as_rerun "${user_procname}"; then
            debasher::_mark_process_as_rerun "${owner_procname}" "${DEBASHER_PROPAGATE_FIFO_RERUN_REASON}"
        fi

        # Mark fifo user process as rerun if the owner is already marked
        if debasher::_process_marked_as_rerun "${owner_procname}"; then
            debasher::_mark_process_as_rerun "${user_procname}" "${DEBASHER_PROPAGATE_FIFO_RERUN_REASON}"
        fi
    done
}

########
debasher::_propagate_rerun_mark_due_to_deps_iter()
{
    # Iterate over all processes
    for processname in "${!DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED[@]}"; do
        local deps=${DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED[${processname}]}

        # Iterate over process dependencies
        local -a deps_array
        IFS="${DEBASHER_PROCESSDEPS_SEP_COMMA}" read -ra deps_array <<< "$deps"
        local proc
        for proc in "${deps_array[@]}"; do
            # If dependency is marked to rerun, mark the dependent
            # process and break loop
            if debasher::_process_marked_as_rerun "${proc}"; then
                debasher::_mark_process_as_rerun "${processname}" "${DEBASHER_PROPAGATE_DEPS_RERUN_REASON}"
                break
            fi
        done
    done
}

########
debasher::_propagate_rerun_processes()
{
    # Read input parameters
    local dirname=$1

    local prev_marked_procs=0
    local num_marked_procs=`debasher::_num_processes_marked_as_rerun`

    while (( prev_marked_procs < num_marked_procs )); do
        debasher::_propagate_rerun_mark_due_to_deps_iter
        debasher::_propagate_rerun_mark_due_to_fifos_iter "${dirname}"
        prev_marked_procs=${num_marked_procs}
        num_marked_procs=`debasher::_num_processes_marked_as_rerun`
    done
}
