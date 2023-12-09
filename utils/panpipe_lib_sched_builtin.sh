##########################################
# SCHEDULER FUNCTIONS RELATED TO BUILTIN #
##########################################

########
get_process_log_filename_builtin()
{
    local scriptsdir=$1
    local processname=$2

    echo "${scriptsdir}/${processname}.${BUILTIN_SCHED_LOG_FEXT}"
}

########
get_task_log_filename_builtin()
{
    local scriptsdir=$1
    local processname=$2
    local taskidx=$3

    echo "${scriptsdir}/${processname}_${taskidx}.${BUILTIN_SCHED_LOG_FEXT}"
}

########
builtin_sched_stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Process ids information for process (each element in ids_info is a pid)
    for id in ${ids_info}; do
        stop_pid $id || { echo "Error while stopping process with id $id" >&2 ; return 1; }
    done
}

########
process_is_unfinished_but_runnable_builtin_sched()
{
    # Processes where the following is true are assigned this status:
    #  - process is an array of tasks
    #  - there are no tasks in progress
    #  - at least one task has been launched
    #  - at least one task can start execution

    local dirname=$1
    local processname=$2

    # Get .id files of finished tasks
    ids=`get_launched_array_task_ids "$dirname" $processname`
    local -A launched_array_tids
    for id in ${ids}; do
        launched_array_tids[${id}]=1
    done

    # If no launched array tasks were found, process is not array or it is
    # not an unfinished one
    num_launched_tasks=${#launched_array_tids[@]}
    if [ ${num_launched_tasks} -eq 0 ]; then
        return 1
    else
        # Process is array with some tasks already launched

        # Check that not all array tasks were launched
        local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
        local num_array_tasks_to_finish=`get_num_array_tasks_from_finished_file "${finished_filename}"`
        if [ ${num_launched_tasks} -eq ${num_array_tasks_to_finish} ]; then
            return 1
        fi

        # Check there are no tasks in progress
        for id in ${!launched_array_tids[@]}; do
            if id_exists $id; then
                return 1
            fi
        done

        # All conditions satisfied
        return 0
    fi
}

########
get_elapsed_time_for_process_builtin()
{
    local dirname=$1
    local processname=$2

    # Obtain finished filename
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`

    if [ -f ${finished_filename} ]; then
        # Get number of array tasks
        local num_tasks=`get_num_array_tasks_from_finished_file "${finished_filename}"`

        case $num_tasks in
            0)  echo ${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
                ;;
            1)  # Process is not a task array
                log_filename=`get_process_log_filename_builtin "${dirname}" ${processname}`
                local difft=`get_elapsed_time_from_logfile "${log_filename}"`
                echo ${difft}
                ;;
            *)  # Process is a task array
                local result=""
                local taskidx
                for taskidx in `get_finished_array_task_indices "${dirname}" ${processname}`; do
                    local log_filename=`get_task_log_filename_builtin "${dirname}" ${processname} ${taskidx}`
                    local difft=`get_elapsed_time_from_logfile "${log_filename}"`
                    if [ ! -z "${result}" ]; then
                        result="${result} "
                    fi
                    result="${result}${taskidx}->${difft} ;"
                done
                echo ${result}
                ;;
        esac
    else
        echo ${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
    fi
}

########
seq_execute_builtin()
{
    local process_to_launch=$1

    # Execute process
    shift
    "${process_to_launch}" "$@" || return 1
}
