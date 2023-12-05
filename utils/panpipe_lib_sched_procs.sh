############################################
# SCHEDULER FUNCTIONS RELATED TO PROCESSES #
############################################

########
get_script_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}"
}

########
get_processid_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/$processname.${PROCESSID_FEXT}"
}

########
get_array_taskid_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_${idx}.${ARRAY_TASKID_FEXT}"
}

########
get_array_taskid()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    file=`get_array_taskid_filename "${dirname}" ${processname} ${idx}`
    if [ -f "${file}" ]; then
        "${CAT}" "$file"
    else
        echo ${INVALID_ARRAY_TID}
    fi
}

########
get_process_finished_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.${FINISHED_PROCESS_FEXT}"
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
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ -f "${finished_filename}" ]; then
        while read line; do
            local fields=( $line )
            local num_fields=${#fields[@]}
            if [ ${num_fields} -eq 7 ]; then
                local id=${fields[3]}
                completed_tasks[${id}]="1"
            fi
        done < "${finished_filename}"
    fi

    # Create string enumerating pending tasks
    local pending_tasks=""
    local idx=1
    while [ $idx -le ${array_size} ]; do
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
get_task_array_list()
{
    local dirname=$1
    local processname=$2
    local array_size=$3
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`

    if [ -f "${finished_filename}" ]; then
        # Some jobs were completed, return list containing pending ones
        get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}
    else
        # No jobs were completed, return list containing all of them
        echo "1-${array_size}"
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
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ "${status}" = "${REEXEC_PROCESS_STATUS}" ]; then
        rm -f "${finished_filename}"
        PANPIPE_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]=1
    fi
}

########
clean_process_log_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            clean_process_log_files_slurm "$dirname" $processname $array_size
            ;;
    esac
}

########
clean_process_id_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local processid_file=`get_processid_filename "${dirname}" ${processname}`
        rm -f "${processid_file}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local array_taskid_file=`get_array_taskid_filename "${dirname}" ${processname} ${idx}`
                rm -f "${array_taskid_file}"
            done
        fi
    fi
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

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_given_basedir "${dirname}"`

    # Return ids for array tasks if any
    local id
    for taskid_file in "${scriptsdir}"/${processname}_*.${ARRAY_TASKID_FEXT}; do
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

    if [ "${PANPIPE_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        PANPIPE_REEXEC_PROCESSES[${processname}]=${reason}
    else
        local curr_val=PANPIPE_REEXEC_PROCESSES[${processname}]
        PANPIPE_REEXEC_PROCESSES[${processname}]="${curr_val},${reason}"
    fi
}

########
get_reexec_processes_as_string()
{
    local result=""
    for processname in "${!PANPIPE_REEXEC_PROCESSES[@]}"; do
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

    if [ "${PANPIPE_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        if [ "${PANPIPE_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]}" = "" ]; then
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
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    echo "Finished task idx: $idx ; Total: $total" >> "${finished_filename}"
}

########
get_signal_process_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local total=$3

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    if [ ${total} -eq 1 ]; then
        echo "echo \"Finished task idx: 1 ; Total: $total\" >> `get_process_finished_filename "${dirname}" ${processname}`"
    else
        echo "echo \"Finished task idx: \${SLURM_ARRAY_TASK_ID} ; Total: $total\" >> `get_process_finished_filename "${dirname}" ${processname}`"
    fi
}

########
stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Launch process
    local sched=`determine_scheduler`
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

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    # Return ids for array tasks if any
    for taskid_file in "${scriptsdir}"/${processname}_*.${ARRAY_TASKID_FEXT}; do
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

    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ -f "${finished_filename}" ]; then
        "${AWK}" '{print $4}' "${finished_filename}"
    fi
}

########
array_task_is_finished()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Check file with finished tasks info exists
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ ! -f "${finished_filename}" ]; then
        return 1
    fi

    # Check that task is in file
    local task_in_file=1
    "${GREP}" "idx: ${idx} ;" "${finished_filename}" > /dev/null || task_in_file=0
    if [ ${task_in_file} -eq 1 ]; then
        return 0
    else
        return 1
    fi
}

########
get_num_finished_array_tasks_from_finished_file()
{
    local finished_filename=$1
    "$WC" -l "${finished_filename}" | "$AWK" '{print $1}'
}

########
get_num_array_tasks_from_finished_file()
{
    local finished_filename=$1
    "$HEAD" -1 "${finished_filename}" | "$AWK" '{print $NF}'
}

########
process_is_finished()
{
    local dirname=$1
    local processname=$2
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`

    if [ -f "${finished_filename}" ]; then
        # Obtain number of finished tasks
        local num_array_tasks_finished=`get_num_finished_array_tasks_from_finished_file "${finished_filename}"`
        if [ ${num_array_tasks_finished} -eq 0 ]; then
            return 1
        fi
        # Check that all tasks are finished
        local num_array_tasks_to_finish=`get_num_array_tasks_from_finished_file "${finished_filename}"`
        if [ ${num_array_tasks_finished} -eq ${num_array_tasks_to_finish} ]; then
            return 0
        else
            return 1
        fi
    else
        return 1
    fi
}

########
process_is_unfinished_but_runnable()
{
    local dirname=$1
    local processname=$2

    # Check status depending on the scheduler
    local sched=`determine_scheduler`
    local exit_code
    case $sched in
        ${SLURM_SCHEDULER})
            # UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS status is not
            # considered for SLURM scheduler, since task arrays are
            # executed as a single job
            return 1
            ;;
        ${BUILTIN_SCHEDULER})
            process_is_unfinished_but_runnable_builtin_sched "${dirname}" ${processname}
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
        echo ${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
    fi
}

########
get_elapsed_time_for_process()
{
    local dirname=$1
    local processname=$2

    # Get name of log file
    local sched=`determine_scheduler`
    local log_filename
    case $sched in
        ${SLURM_SCHEDULER})
            get_elapsed_time_for_process_slurm "${dirname}" ${processname}
            ;;
        ${BUILTIN_SCHEDULER})
            get_elapsed_time_for_process_builtin "${dirname}" ${processname}
            ;;
    esac
}

########
get_process_status()
{
    local dirname=$1
    local processname=$2
    local script_filename=`get_script_filename "${dirname}" ${processname}`

    # Check if process should be reexecuted (REEXEC status has the
    # highest priority level)
    if process_should_be_reexec $processname; then
        echo "${REEXEC_PROCESS_STATUS}"
        return ${REEXEC_PROCESS_EXIT_CODE}
    fi

    # Check that script file for process was created
    if [ -f "${script_filename}" ]; then
        if process_is_in_progress "$dirname" $processname; then
            echo "${INPROGRESS_PROCESS_STATUS}"
            return ${INPROGRESS_PROCESS_EXIT_CODE}
        fi

        if process_is_finished "$dirname" $processname; then
            echo "${FINISHED_PROCESS_STATUS}"
            return ${FINISHED_PROCESS_EXIT_CODE}
        else
            if process_is_unfinished_but_runnable "$dirname" $processname; then
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
