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

############################################
# SCHEDULER FUNCTIONS RELATED TO PROCESSES #
############################################

########
debasher::_get_processid_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/$processname.${DEBASHER_PROCESSID_FEXT}"
}

########
debasher::_get_array_taskid_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get exec dir
    local execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}_${idx}.${DEBASHER_ARRAY_TASKID_FEXT}"
}

########
debasher::_get_array_taskid()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    file=`debasher::_get_array_taskid_filename "${dirname}" ${processname} ${idx}`
    if [ -f "${file}" ]; then
        "${CAT}" "$file"
    else
        echo ${DEBASHER_INVALID_ARRAY_TID}
    fi
}

########
debasher::_get_process_finished_filename_prefix()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}"
}

########
debasher::_get_process_finished_filename()
{
    local dirname=$1
    local processname=$2

    # Get prefix
    local prefix=`debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}"`

    echo "${prefix}.${DEBASHER_FINISHED_PROCESS_FEXT}"
}

########
debasher::_get_task_finished_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get prefix
    local prefix=`debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}"`

    echo "${prefix}_${idx}.${DEBASHER_FINISHED_PROCESS_FEXT}"
}

########
debasher::_apply_deptype_to_processids()
{
    # Initialize variables
    local processids=$1
    local deptype=$2

    # Apply deptype
    local result=""
    local separator=`debasher::_get_processdeps_separator ${processids}`
    if [ "${separator}" = "" ]; then
        local processids_blanks=${processids}
    else
        local processids_blanks=`debasher::_replace_str_elem_sep_with_blank "${separator}" ${processids}`
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
debasher::_get_list_of_pending_tasks_in_array()
{
    # NOTE: a pending task here is just one that is not finished
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Create associative map containing completed jobs
    local -A completed_tasks
    local finished_filename_pref=`debasher::_get_process_finished_filename_prefix "${dirname}" ${processname}`
    local file
    for file in "${finished_filename_pref}"_*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$DEBASHER_FINISHED_PROCESS_FEXT}"
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
debasher::_get_num_array_tasks()
{
    local dirname=$1
    local processname=$2
    local finished_filename_pref=`debasher::_get_process_finished_filename_prefix "${dirname}" ${processname}`

    local num_tasks=0
    for file in "${finished_filename_pref}"*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks=`"${AWK}" '{print $NF}' "${file}"`
            break
        fi
    done

    echo "${num_tasks}"
}

########
debasher::_get_num_tasks_completed()
{
    local dirname=$1
    local processname=$2
    local finished_filename_pref=`debasher::_get_process_finished_filename_prefix "${dirname}" ${processname}`

    local num_tasks_completed=0
    for file in "${finished_filename_pref}"*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks_completed=$((num_tasks_completed + 1))
        fi
    done

    echo "${num_tasks_completed}"
}

########
debasher::_get_task_array_list()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local num_completed_tasks=`debasher::_get_num_tasks_completed "${dirname}" "${processname}"`
    if [ "${num_completed_tasks}" -eq 0 ]; then
        # No tasks were completed, return list containing all of them
        local last_task_idx=$((array_size - 1))
        echo "0-${last_task_idx}"
    else
        # Some tasks were completed, return list containing pending ones
        debasher::_get_list_of_pending_tasks_in_array "${dirname}" "${processname}" "${array_size}"
    fi
}

########
debasher::_reset_process_completion_signal()
{
    local dirname=$1
    local processname=$2

    local finished_filename_pref=`debasher::_get_process_finished_filename_prefix "${dirname}" ${processname}`
    "${RM}" -f "${finished_filename_pref}"*.${DEBASHER_FINISHED_PROCESS_FEXT}
}

########
debasher::_clean_process_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local sched=`debasher::_get_scheduler`
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_clean_process_files_slurm "$dirname" "$processname" "$array_size"
            ;;
    esac
}

########
debasher::_write_process_id_info_to_file()
{
    local dirname=$1
    local processname=$2
    local id_info=$3
    local filename=`debasher::_get_processid_filename "${dirname}" ${processname}`

    echo ${id_info} > "$filename"
}

########
debasher::_read_process_id_info_from_file()
{
    local dirname=$1
    local processname=$2

    # Return id for process
    local filename=`debasher::_get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        "${CAT}" "$filename"
    else
        echo ${DEBASHER_INVALID_SID}
    fi
}

########
debasher::_read_ids_from_files()
{
    local dirname=$1
    local processname=$2
    local ids

    # Return id for process
    local filename=`debasher::_get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        ids=`"${CAT}" "$filename"`
    fi

    # Get exec dir
    local execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    # Return ids for array tasks if any
    local id
    for taskid_file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}; do
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
debasher::_signal_process_completion()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local idx=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        local finished_filename=`debasher::_get_process_finished_filename "${dirname}" ${processname}`
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    else
        local finished_filename=`debasher::_get_task_finished_filename "${dirname}" ${processname} ${idx}`
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    fi
}

########
debasher::_get_signal_process_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local taskidx_varname=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        echo "echo \"Finished task idx: 0 ; Total: $total\" > `debasher::_get_process_finished_filename "${dirname}" ${processname}`"
    else
        echo "echo \"Finished task idx: \${${taskidx_varname}} ; Total: $total\" > \`debasher::_get_task_finished_filename \"${dirname}\" ${processname} \${${taskidx_varname}}\`"
    fi
}

########
debasher::_stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Launch process
    local sched=`debasher::_get_scheduler`
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER}) ## Launch using slurm
            debasher::_slurm_stop_process ${ids_info} || return 1
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_builtin_sched_stop_process ${ids_info} || return 1
            ;;
    esac
}

########
debasher::_process_is_in_progress()
{
    local dirname=$1
    local processname=$2
    local ids=`debasher::_read_ids_from_files "$dirname" "$processname"`

    # Iterate over ids
    for id in ${ids}; do
        # Get global id (when executing multiple attempts, multiple ids
        # will be associated to a given process)
        local global_id=`debasher::_get_global_id "${id}"`
        if debasher::_id_exists "${global_id}"; then
            return 0
        fi
    done

    return 1
}

########
debasher::_get_launched_array_task_ids()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    # Return ids for array tasks if any
    local taskid_file
    for taskid_file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            "${CAT}" "${taskid_file}"
        fi
    done

}

########
debasher::_get_finished_array_task_indices()
{
    local dirname=$1
    local processname=$2

    local finished_filename_pref=`debasher::_get_process_finished_filename_prefix "${dirname}" ${processname}`
    local file
    for file in "${finished_filename_pref}"_*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$DEBASHER_FINISHED_PROCESS_FEXT}"
            echo ${id}
        fi
    done
}

########
debasher::_array_task_is_finished()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Check if finished task file exists
    local finished_filename=`debasher::_get_task_finished_filename "${dirname}" ${processname} "${idx}"`
    if [ ! -f "${finished_filename}" ]; then
        return 1
    fi
}

########
debasher::_process_is_finished()
{
    local dirname=$1
    local processname=$2

    local num_tasks_completed=`debasher::_get_num_tasks_completed "${dirname}" "${processname}"`

    if [ "${num_tasks_completed}" -eq 0 ]; then
        return 1
    else
        local num_tasks=`debasher::_get_num_array_tasks "${dirname}" "${processname}"`
        if [ "${num_tasks_completed}" -eq "${num_tasks}" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
debasher::_process_is_unfinished_but_runnable()
{
    local dirname=$1
    local processname=$2

    # Check status depending on the scheduler
    local sched=`debasher::_get_scheduler`
    local exit_code
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            # DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS status is not
            # considered for SLURM scheduler, since task arrays are
            # executed as a single job
            return 1
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_process_is_unfinished_but_runnable_builtin_sched "${dirname}" "${processname}"
            exit_code=$?
            return ${exit_code}
        ;;
    esac
}

########
debasher::_get_process_status()
{
    local dirname=$1
    local processname=$2
    local script_filename=`debasher::_get_script_filename "${dirname}" ${processname}`

    if [ -f "${script_filename}" ]; then
        if debasher::_process_is_in_progress "$dirname" "$processname"; then
            echo "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
            return ${DEBASHER_INPROGRESS_PROCESS_EXIT_CODE}
        fi

        if debasher::_process_is_finished "$dirname" "$processname"; then
            echo "${DEBASHER_FINISHED_PROCESS_STATUS}"
            return ${DEBASHER_FINISHED_PROCESS_EXIT_CODE}
        else
            if debasher::_process_is_unfinished_but_runnable "$dirname" "$processname"; then
                echo "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}"
                return ${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_EXIT_CODE}
            fi
        fi

        echo "${DEBASHER_UNFINISHED_PROCESS_STATUS}"
        return ${DEBASHER_UNFINISHED_PROCESS_EXIT_CODE}
    else
        echo "${DEBASHER_TODO_PROCESS_STATUS}"
        return ${DEBASHER_TODO_PROCESS_EXIT_CODE}
    fi
}
