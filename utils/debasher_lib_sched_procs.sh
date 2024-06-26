# DeBasher package
# Copyright (C) 2019-2024 Daniel Ortiz-Mart\'inez
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

############################################
# SCHEDULER FUNCTIONS RELATED TO PROCESSES #
############################################

########
get_processid_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/$processname.${PROCESSID_FEXT}"
}

########
get_array_taskid_filename()
{
    local execdir=$1
    local processname=$2
    local idx=$3

    echo "${execdir}/${processname}_${idx}.${ARRAY_TASKID_FEXT}"
}

########
get_array_taskid()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get exec dir
    local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    file=`get_array_taskid_filename "${dirname}" ${processname} ${idx}`
    if [ -f "${file}" ]; then
        "${CAT}" "$file"
    else
        echo ${INVALID_ARRAY_TID}
    fi
}

########
get_process_finished_filename_prefix()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}"
}

########
get_process_finished_filename()
{
    local dirname=$1
    local processname=$2

    # Get prefix
    local prefix=`get_process_finished_filename_prefix "${dirname}" "${processname}"`

    echo "${prefix}.${FINISHED_PROCESS_FEXT}"
}

########
get_task_finished_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get prefix
    local prefix=`get_process_finished_filename_prefix "${dirname}" "${processname}"`

    echo "${prefix}_${idx}.${FINISHED_PROCESS_FEXT}"
}

########
apply_deptype_to_processids()
{
    # Initialize variables
    local processids=$1
    local deptype=$2

    # Apply deptype
    local result=""
    local separator=`get_processdeps_separator ${processids}`
    if [ "${separator}" = "" ]; then
        local processids_blanks=${processids}
    else
        local processids_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processids}`
    fi
    local id
    for id in ${processids_blanks}; do
        if [ -z "" ]; then
            result=${deptype}:${id}
        else
            result=${result}"${separator}"${deptype}:${id}
        fi
    done

    echo $result
}

########
get_list_of_pending_tasks_in_array()
{
    # NOTE: a pending task here is just one that is not finished
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Create associative map containing completed jobs
    local -A completed_tasks
    local finished_filename_pref=`get_process_finished_filename_prefix "${dirname}" ${processname}`
    local file
    for file in "${finished_filename_pref}"_*.${FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$FINISHED_PROCESS_FEXT}"
            completed_tasks[${id}]="1"
        fi
    done

    # Create string enumerating pending tasks
    local pending_tasks=""
    local idx=0
    while [ $idx -lt ${array_size} ]; do
        if [ -z "${completed_tasks[${idx}]}" ]; then
            if [ -z "${pending_tasks}" ]; then
                pending_tasks=${idx}
            else
                pending_tasks="${pending_tasks},${idx}"
            fi
        fi
        idx=$((idx + 1))
    done

    echo ${pending_tasks}
}

########
get_num_array_tasks()
{
    local dirname=$1
    local processname=$2
    local finished_filename_pref=`get_process_finished_filename_prefix "${dirname}" ${processname}`

    local num_tasks=0
    for file in "${finished_filename_pref}"*.${FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks=`"${AWK}" '{print $NF}' "${file}"`
            break
        fi
    done

    echo "${num_tasks}"
}

########
get_num_tasks_completed()
{
    local dirname=$1
    local processname=$2
    local finished_filename_pref=`get_process_finished_filename_prefix "${dirname}" ${processname}`

    local num_tasks_completed=0
    for file in "${finished_filename_pref}"*.${FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks_completed=$((num_tasks_completed + 1))
        fi
    done

    echo "${num_tasks_completed}"
}

########
get_task_array_list()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local num_completed_tasks=`get_num_tasks_completed "${dirname}" "${processname}"`
    if [ "${num_completed_tasks}" -eq 0 ]; then
        # No tasks were completed, return list containing all of them
        local last_task_idx=$((array_size - 1))
        echo "0-${last_task_idx}"
    else
        # Some tasks were completed, return list containing pending ones
        get_list_of_pending_tasks_in_array "${dirname}" "${processname}" "${array_size}"
    fi
}

########
update_process_completion_signal()
{
    local dirname=$1
    local processname=$2
    local status=$3

    # If process will be reexecuted, file signaling process completion should
    # be removed. Additionally, this action should be registered in a
    # specific associative array
    local finished_filename_pref=`get_process_finished_filename_prefix "${dirname}" ${processname}`
    if [ "${status}" = "${REEXEC_PROCESS_STATUS}" ]; then
        "${RM}" -f "${finished_filename_pref}"*.${FINISHED_PROCESS_FEXT}
        DEBASHER_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]=1
    fi
}

########
clean_process_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            clean_process_files_slurm "$dirname" "$processname" "$array_size"
            ;;
    esac
}

########
write_process_id_info_to_file()
{
    local dirname=$1
    local processname=$2
    local id_info=$3
    local filename=`get_processid_filename "${dirname}" ${processname}`

    echo ${id_info} > "$filename"
}

########
read_process_id_info_from_file()
{
    local dirname=$1
    local processname=$2

    # Return id for process
    local filename=`get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        "${CAT}" "$filename"
    else
        echo ${INVALID_SID}
    fi
}

########
read_ids_from_files()
{
    local dirname=$1
    local processname=$2
    local ids

    # Return id for process
    local filename=`get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        ids=`"${CAT}" "$filename"`
    fi

    # Get exec dir
    local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    # Return ids for array tasks if any
    local id
    for taskid_file in "${execdir}"/${processname}_*.${ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            id=`"${CAT}" "${taskid_file}"`
            if [ -z "${ids}" ]; then
                ids=$id
            else
                ids="${ids} ${id}"
            fi
        fi
    done

    echo ${ids}
}

########
mark_process_as_reexec()
{
    local processname=$1
    local reason=$2

    if [ "${DEBASHER_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        DEBASHER_REEXEC_PROCESSES[${processname}]=${reason}
    else
        local curr_val=DEBASHER_REEXEC_PROCESSES[${processname}]
        DEBASHER_REEXEC_PROCESSES[${processname}]="${curr_val},${reason}"
    fi
}

########
get_reexec_processes_as_string()
{
    local result=""
    for processname in "${!DEBASHER_REEXEC_PROCESSES[@]}"; do
        if [ "${result}" = "" ]; then
            result=${processname}
        else
            result="${result},${processname}"
        fi
    done

    echo ${result}
}

########
process_should_be_reexec()
{
    local processname=$1

    if [ "${DEBASHER_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        if [ "${DEBASHER_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]}" = "" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
signal_process_completion()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local idx=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    else
        local finished_filename=`get_task_finished_filename "${dirname}" ${processname} ${idx}`
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    fi
}

########
get_signal_process_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local taskidx_varname=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        echo "echo \"Finished task idx: 0 ; Total: $total\" > `get_process_finished_filename "${dirname}" ${processname}`"
    else
        echo "echo \"Finished task idx: \${${taskidx_varname}} ; Total: $total\" > \`get_task_finished_filename \"${dirname}\" ${processname} \${${taskidx_varname}}\`"
    fi
}

########
stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Launch process
    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            slurm_stop_process ${ids_info} || return 1
            ;;
        ${BUILTIN_SCHEDULER})
            builtin_sched_stop_process ${ids_info} || return 1
            ;;
    esac
}

########
process_is_in_progress()
{
    local dirname=$1
    local processname=$2
    local ids=`read_ids_from_files "$dirname" "$processname"`

    # Iterate over ids
    for id in ${ids}; do
        # Get global id (when executing multiple attempts, multiple ids
        # will be associated to a given process)
        local global_id=`get_global_id "${id}"`
        if id_exists "${global_id}"; then
            return 0
        fi
    done

    return 1
}

########
get_launched_array_task_ids()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    # Return ids for array tasks if any
    local taskid_file
    for taskid_file in "${execdir}"/${processname}_*.${ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            "${CAT}" "${taskid_file}"
        fi
    done

}

########
get_finished_array_task_indices()
{
    local dirname=$1
    local processname=$2

    local finished_filename_pref=`get_process_finished_filename_prefix "${dirname}" ${processname}`
    local file
    for file in "${finished_filename_pref}"_*.${FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$FINISHED_PROCESS_FEXT}"
            echo ${id}
        fi
    done
}

########
array_task_is_finished()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Check if finished task file exists
    local finished_filename=`get_task_finished_filename "${dirname}" ${processname} "${idx}"`
    if [ ! -f "${finished_filename}" ]; then
        return 1
    fi
}

########
process_is_finished()
{
    local dirname=$1
    local processname=$2

    local num_tasks_completed=`get_num_tasks_completed "${dirname}" "${processname}"`

    if [ "${num_tasks_completed}" -eq 0 ]; then
        return 1
    else
        local num_tasks=`get_num_array_tasks "${dirname}" "${processname}"`
        if [ "${num_tasks_completed}" -eq "${num_tasks}" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
process_is_unfinished_but_runnable()
{
    local dirname=$1
    local processname=$2

    # Check status depending on the scheduler
    local sched=`get_scheduler`
    local exit_code
    case $sched in
        ${SLURM_SCHEDULER})
            # UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS status is not
            # considered for SLURM scheduler, since task arrays are
            # executed as a single job
            return 1
            ;;
        ${BUILTIN_SCHEDULER})
            process_is_unfinished_but_runnable_builtin_sched "${dirname}" "${processname}"
            exit_code=$?
            return ${exit_code}
        ;;
    esac
}

########
get_elapsed_time_from_logfile()
{
    local log_filename=$1
    local start_date=`get_process_start_date "${log_filename}"`
    local finish_date=`get_process_finish_date "${log_filename}"`

    # Obtain difference
    if [ ! -z "${start_date}" -a ! -z "${finish_date}" ]; then
        local start_date_secs=`date -d "${finish_date}" +%s`
        local finish_date_secs=`date -d "${start_date}" +%s`
        echo $(( start_date_secs - finish_date_secs ))
    else
        echo "${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}"
    fi
}

########
get_elapsed_time_for_process()
{
    local dirname=$1
    local processname=$2

    # Get name of log file
    local sched=`get_scheduler`
    local log_filename
    case $sched in
        ${SLURM_SCHEDULER})
            get_elapsed_time_for_process_slurm "${dirname}" "${processname}"
            ;;
        ${BUILTIN_SCHEDULER})
            get_elapsed_time_for_process_builtin "${dirname}" "${processname}"
            ;;
    esac
}

########
get_process_status()
{
    local dirname=$1
    local processname=$2
    local script_filename=`get_script_filename "${dirname}" ${processname}`

    if [ -f "${script_filename}" ]; then
        if process_is_in_progress "$dirname" "$processname"; then
            echo "${INPROGRESS_PROCESS_STATUS}"
            return ${INPROGRESS_PROCESS_EXIT_CODE}
        fi

        # Check if process should be reexecuted
        if process_should_be_reexec "$processname"; then
            echo "${REEXEC_PROCESS_STATUS}"
            return ${REEXEC_PROCESS_EXIT_CODE}
        fi

        if process_is_finished "$dirname" "$processname"; then
            echo "${FINISHED_PROCESS_STATUS}"
            return ${FINISHED_PROCESS_EXIT_CODE}
        else
            if process_is_unfinished_but_runnable "$dirname" "$processname"; then
                echo "${UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}"
                return ${UNFINISHED_BUT_RUNNABLE_PROCESS_EXIT_CODE}
            fi
        fi

        echo "${UNFINISHED_PROCESS_STATUS}"
        return ${UNFINISHED_PROCESS_EXIT_CODE}
    else
        echo "${TODO_PROCESS_STATUS}"
        return ${TODO_PROCESS_EXIT_CODE}
    fi
}
