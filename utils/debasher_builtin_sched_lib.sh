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

# *- bash -*

#############
# CONSTANTS #
#############

# MISC CONSTANTS
DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS="FAILED"
DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK="NO_ARRAY_TASK"
DEBASHER_BUILTIN_SCHED_SLEEP_TIME_LONG=5
DEBASHER_BUILTIN_SCHED_SLEEP_TIME_SHORT=1
DEBASHER_BUILTIN_SCHED_NPROCESSES_SLEEP_THRESHOLD=10
DEBASHER_BUILTIN_SCHED_KNAPSACK_ITEM_WEIGHT_SPEC_FNAME=.knapsack_item_weight_spec.txt
DEBASHER_BUILTIN_SCHED_KNAPSACK_PRED_SPEC_FNAME=.knapsack_pred_spec.txt
DEBASHER_BUILTIN_SCHED_KNAPSACK_SOL_FNAME=.knapsack_sol.txt
DEBASHER_BUILTIN_SCHED_KNAPSACK_SOL_STDERR_FNAME=.knapsack_sol_stderr.txt
DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS=0
DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM=0
DEBASHER_BUILTIN_SCHED_SOLVE_TIME_LIMIT=1
DEBASHER_BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER=1

# ARRAY TASK STATUSES
DEBASHER_BUILTIN_SCHED_FINISHED_TASK_STATUS="FINISHED"
DEBASHER_BUILTIN_SCHED_INPROGRESS_TASK_STATUS="IN-PROGRESS"
DEBASHER_BUILTIN_SCHED_FAILED_TASK_STATUS="FAILED"
DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS="TO-DO"

####################
# GLOBAL VARIABLES #
####################

# Declare built-in scheduler-related variables
declare -A DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX
declare -A DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_SCRIPT_FILENAME
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_SPEC
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_DEPS
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_CPUS
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_MEM
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM
declare -A DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS
declare -A DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS
declare DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES
declare DEBASHER_BUILTIN_SCHED_CPUS=1
declare DEBASHER_BUILTIN_SCHED_MEM=256
declare DEBASHER_BUILTIN_SCHED_ALLOC_CPUS=0
declare DEBASHER_BUILTIN_SCHED_ALLOC_MEM=0

###############################
# BUILTIN SCHEDULER FUNCTIONS #
###############################

########
debasher_builtin_sched::_cpus_within_limit()
{
    local cpus=$1
    if [ ${DEBASHER_BUILTIN_SCHED_CPUS} -eq 0 ]; then
        return 0
    else
        if [ ${DEBASHER_BUILTIN_SCHED_CPUS} -ge $cpus ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
debasher_builtin_sched::_mem_within_limit()
{
    local mem=$1
    if [ ${DEBASHER_BUILTIN_SCHED_MEM} -eq 0 ]; then
        return 0
    else
        if [ ${DEBASHER_BUILTIN_SCHED_MEM} -ge $mem ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
debasher_builtin_sched::_update_processname_to_idx_info()
{
    local processname=$1
    if [ ${DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]} = ""]; then
        local len=${#DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[@]}
        DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]=${len}
        DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME[${len}]=${processname}
    fi
}

########
debasher_builtin_sched::_init_process_info()
{
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
            local script_filename=`debasher::_get_script_filename "${dirname}" ${processname}`
            local status=`debasher::_get_process_status "${dirname}" ${processname}`
            local processdeps=`debasher::_extract_processdeps_from_process_spec "$process_spec"`
            local spec_throttle=`debasher::_extract_throttle_from_process_spec "$process_spec"`
            local sched_throttle=`debasher::_get_scheduler_throttle ${spec_throttle}`
            local array_size=`debasher::_get_numtasks_for_process "${processname}"`

            # Get cpus info
            local cpus=`debasher::_extract_cpus_from_process_spec "$process_spec"`
            debasher::_str_is_natural_number ${cpus} || { echo "Error: number of cpus ($cpus) for $processname should be a natural number" >&2; return 1; }

            # Get mem info (NOTE: if multiple attempts specified, keep
            # memory specification of the first one)
            local mem=`debasher::_extract_mem_from_process_spec "$process_spec"`
            local attempt_no=1
            mem=`debasher::_get_mem_attempt_value ${mem} ${attempt_no}`
            mem=`debasher::_convert_mem_value_to_mb ${mem}` || { echo "Invalid memory specification for process ${processname}" >&2; return 1; }
            debasher::_str_is_natural_number ${mem} || { echo "Error: amount of memory ($mem) for $processname should be a natural number" >&2; return 1; }

            # Check cpus value
            debasher_builtin_sched::_cpus_within_limit ${cpus} || { echo "Error: number of cpus for process $processname exceeds limit (cpus: ${cpus}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Check mem value
            debasher_builtin_sched::_mem_within_limit ${mem} || { echo "Error: amount of memory for process $processname exceeds limit (mem: ${mem}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Register process information
            debasher_builtin_sched::_update_processname_to_idx_info ${processname}
            DEBASHER_BUILTIN_SCHED_PROCESS_SCRIPT_FILENAME[${processname}]=${script_filename}
            DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${status}
            DEBASHER_BUILTIN_SCHED_PROCESS_SPEC[${processname}]="${process_spec}"
            DEBASHER_BUILTIN_SCHED_PROCESS_DEPS[${processname}]=${processdeps}
            DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]=${array_size}
            DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE[${processname}]=${sched_throttle}
            DEBASHER_BUILTIN_SCHED_PROCESS_CPUS[${processname}]=${cpus}
            DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=0
            DEBASHER_BUILTIN_SCHED_PROCESS_MEM[${processname}]=${mem}
            DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=0
        fi
    done < "${procspec_file}"
}

########
debasher_builtin_sched::_revise_reexec_proc_status()
{
    # Iterate over defined processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        # If process is marked as reexec and it was finished, its process completion is reset
        if debasher::_process_marked_as_reexec ${processname}; then
            if [ ${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]} = ${DEBASHER_FINISHED_PROCESS_STATUS} ]; then
                debasher::_reset_process_completion_signal "${dirname}" "${processname}" || { echo "Error when resetting process completion signal for process" >&2 ; return 1; }
                DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${DEBASHER_UNFINISHED_PROCESS_STATUS}
            fi
        fi
    done
}

########
debasher_builtin_sched::_release_mem()
{
    local processname=$1

    DEBASHER_BUILTIN_SCHED_ALLOC_MEM=$((DEBASHER_BUILTIN_SCHED_ALLOC_MEM - ${DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]}))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=0
}

########
debasher_builtin_sched::_release_cpus()
{
    local processname=$1

    DEBASHER_BUILTIN_SCHED_ALLOC_CPUS=$((DEBASHER_BUILTIN_SCHED_ALLOC_CPUS - ${DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]}))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=0
}

########
debasher_builtin_sched::_get_process_mem()
{
    local processname=$1

    echo ${DEBASHER_BUILTIN_SCHED_PROCESS_MEM[${processname}]}
}

########
debasher_builtin_sched::_get_process_mem_given_num_tasks()
{
    local processname=$1
    local ntasks=$2

    if [ ${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]} -eq 1 ]; then
        echo ${DEBASHER_BUILTIN_SCHED_PROCESS_MEM[${processname}]}
    else
        echo $((${DEBASHER_BUILTIN_SCHED_PROCESS_MEM[${processname}]} * ntasks))
    fi
}

########
debasher_builtin_sched::_reserve_mem()
{
    local processname=$1
    local process_mem=`debasher_builtin_sched::_get_process_mem ${processname}`
    DEBASHER_BUILTIN_SCHED_ALLOC_MEM=$((DEBASHER_BUILTIN_SCHED_ALLOC_MEM + process_mem))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=${process_mem}
}

########
debasher_builtin_sched::_get_process_cpus()
{
    local processname=$1

    echo ${DEBASHER_BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
}

########
debasher_builtin_sched::_get_process_cpus_given_num_tasks()
{
    local processname=$1
    local ntasks=$2

    if [ ${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]} -eq 1 ]; then
        echo ${DEBASHER_BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
    else
        echo $((${DEBASHER_BUILTIN_SCHED_PROCESS_CPUS[${processname}]} * ntasks))
    fi
}

########
debasher_builtin_sched::_reserve_cpus()
{
    local processname=$1
    local process_cpus=`debasher_builtin_sched::_get_process_cpus ${processname}`
    DEBASHER_BUILTIN_SCHED_ALLOC_CPUS=$((DEBASHER_BUILTIN_SCHED_ALLOC_CPUS + process_cpus))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=${process_cpus}
}

########
debasher_builtin_sched::_get_array_task_status()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3
    local processdirname=`debasher::_get_process_outdir_given_dirname "${dirname}" ${processname}`
    local array_taskid_file=`debasher::_get_array_taskid_filename "${dirname}" ${processname} ${task_idx}`

    if [ ! -f ${array_taskid_file} ]; then
        # Task is not started
        echo ${DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS}
    else
        # Task was started
        if debasher::_array_task_is_finished "${dirname}" ${processname} ${task_idx}; then
            echo ${DEBASHER_BUILTIN_SCHED_FINISHED_TASK_STATUS}
        else
            # Task is not finished
            local id=`"${CAT}" "${array_taskid_file}"`
            if debasher::_id_exists $id; then
                echo ${DEBASHER_BUILTIN_SCHED_INPROGRESS_TASK_STATUS}
            else
                echo ${DEBASHER_BUILTIN_SCHED_FAILED_TASK_STATUS}
            fi
        fi
    fi
}

########
debasher_builtin_sched::_get_failed_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`debasher_builtin_sched::_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${DEBASHER_BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$task_idx
            else
                result="$result $task_idx"
            fi
        fi
    done

    echo $result
}

########
debasher_builtin_sched::_get_finished_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`debasher_builtin_sched::_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${DEBASHER_BUILTIN_SCHED_FINISHED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$task_idx
            else
                result="$result $task_idx"
            fi
        fi
    done

    echo $result
}

########
debasher_builtin_sched::_get_inprogress_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`debasher_builtin_sched::_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$task_idx
            else
                result="$result $task_idx"
            fi
        fi
    done

    echo $result
}

########
debasher_builtin_sched::_get_todo_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`debasher_builtin_sched::_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$task_idx
            else
                result="$result $task_idx"
            fi
        fi
    done

    echo $result
}

########
debasher_builtin_sched::_get_pending_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`debasher_builtin_sched::_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS} -o ${task_status} = ${DEBASHER_BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$task_idx
            else
                result="$result $task_idx"
            fi
        fi
    done

    echo $result
}

########
debasher_builtin_sched::_revise_array_mem()
{
    local dirname=$1
    local processname=$2

    local inprogress_tasks=`debasher_builtin_sched::_get_inprogress_array_task_indices "${dirname}" ${processname}`
    local num_inprogress_tasks=`debasher::_get_num_words_in_string "${inprogress_tasks}"`
    local process_revised_mem=`debasher_builtin_sched::_get_process_mem_given_num_tasks ${processname} ${num_inprogress_tasks}`
    DEBASHER_BUILTIN_SCHED_ALLOC_MEM=$((DEBASHER_BUILTIN_SCHED_ALLOC_MEM - ${DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]} + process_revised_mem))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=${process_revised_mem}
}

########
debasher_builtin_sched::_revise_array_cpus()
{
    local dirname=$1
    local processname=$2

    local inprogress_tasks=`debasher_builtin_sched::_get_inprogress_array_task_indices "${dirname}" ${processname}`
    local num_inprogress_tasks=`debasher::_get_num_words_in_string "${inprogress_tasks}"`
    local process_revised_cpus=`debasher_builtin_sched::_get_process_cpus_given_num_tasks ${processname} ${num_inprogress_tasks}`
    DEBASHER_BUILTIN_SCHED_ALLOC_CPUS=$((DEBASHER_BUILTIN_SCHED_ALLOC_CPUS - ${DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]} + process_revised_cpus))
    DEBASHER_BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=${process_revised_cpus}
}

########
debasher_builtin_sched::_init_curr_comp_resources()
{
    # Iterate over defined processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        if [ ${status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
            debasher_builtin_sched::_reserve_mem $processname
            debasher_builtin_sched::_reserve_cpus $processname
        fi
    done
}

########
debasher_builtin_sched::_get_updated_process_status()
{
    local dirname=$1

    # Iterate over defined processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[$processname]}
        if [ ${status} != ${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS} -a ${status} != ${DEBASHER_FINISHED_PROCESS_STATUS} ]; then
            local updated_status=`debasher::_get_process_status "${dirname}" ${processname}`
            BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]=${updated_status}
        fi
    done
}

########
debasher_builtin_sched::_update_comp_resources()
{
    local dirname=$1

    # Iterate over processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        prev_status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        updated_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
        if [ "${updated_status}" != "" ]; then
            # Store array size in variable
            process_array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

            # Check if resources should be released
            if [ ${prev_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
                debasher_builtin_sched::_release_mem $processname
                debasher_builtin_sched::_release_cpus $processname
            fi

            # Check if resources should be reserved
            if [ ${prev_status} != ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a ${updated_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
                if [ ${process_array_size} -eq 1 ]; then
                    debasher_builtin_sched::_reserve_mem $processname
                    debasher_builtin_sched::_reserve_cpus $processname
                else
                    # process is an array
                    debasher_builtin_sched::_revise_array_mem "${dirname}" $processname
                    debasher_builtin_sched::_revise_array_cpus "${dirname}" $processname
                fi
            fi

            # Check if resources of job array should be revised
            if [ ${process_array_size} -gt 1 -a ${prev_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a ${updated_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
                debasher_builtin_sched::_revise_array_mem "${dirname}" $processname
                debasher_builtin_sched::_revise_array_cpus "${dirname}" $processname
            fi
        fi
    done
}

########
debasher_builtin_sched::_fix_updated_process_status()
{
    # Copy updated status into current status
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        prev_status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        updated_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
        if [ "${updated_status}" != "" ]; then
            if [ ${prev_status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS} -a ${updated_status} != ${DEBASHER_FINISHED_PROCESS_STATUS} ]; then
                # Status will be set to failed if previous status was
                # in-progress and new status is unfinished
                DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}
            else
                DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
            fi
        fi
    done
}

########
debasher_builtin_sched::_get_available_cpus()
{
    if [ ${DEBASHER_BUILTIN_SCHED_CPUS} -eq ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        echo 0
    else
        echo $((DEBASHER_BUILTIN_SCHED_CPUS - DEBASHER_BUILTIN_SCHED_ALLOC_CPUS))
    fi
}

########
debasher_builtin_sched::_get_available_mem()
{
    if [ ${DEBASHER_BUILTIN_SCHED_MEM} -eq ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        echo 0
    else
        echo $((DEBASHER_BUILTIN_SCHED_MEM - DEBASHER_BUILTIN_SCHED_ALLOC_MEM))
    fi
}

########
debasher_builtin_sched::_check_comp_res()
{
    local processname=$1

    if [ ${DEBASHER_BUILTIN_SCHED_CPUS} -ne ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        local available_cpus=`debasher_builtin_sched::_get_available_cpus`
        process_cpus=`debasher_builtin_sched::_get_process_cpus ${processname}`
        if [ ${process_cpus} -gt ${available_cpus} ]; then
            return 1
        fi
    fi

    if [ ${DEBASHER_BUILTIN_SCHED_MEM} -ne ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        local available_mem=`debasher_builtin_sched::_get_available_mem`
        process_mem=`debasher_builtin_sched::_get_process_mem ${processname}`
        if [ ${process_mem} -gt ${available_mem} ]; then
            return 1
        fi
    fi

    return 0
}

########
debasher_builtin_sched::_check_process_deps()
{
    local processname=$1
    local processdeps=${DEBASHER_BUILTIN_SCHED_PROCESS_DEPS[${processname}]}

    # Iterate over dependencies
    local separator=`debasher::_get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    local dep
    for dep in ${processdeps_blanks}; do
        # Extract information from dependency
        local deptype=`debasher::_get_deptype_part_in_dep ${dep}`
        local depsname=`debasher::_get_processname_part_in_dep ${dep}`

        # Process dependency
        depstatus=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${depsname}]}

        # Process exit code
        local dep_ok=1
        case ${deptype} in
            ${DEBASHER_AFTER_PROCESSDEP_TYPE})
                if [ ${depstatus} = ${DEBASHER_TODO_PROCESS_STATUS} -o  ${depstatus} = ${DEBASHER_UNFINISHED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${DEBASHER_AFTEROK_PROCESSDEP_TYPE})
                if [ ${depstatus} != ${DEBASHER_FINISHED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE})
                if [ ${depstatus} != ${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${DEBASHER_AFTERANY_PROCESSDEP_TYPE})
                if [ ${depstatus} != ${DEBASHER_FINISHED_PROCESS_STATUS} -a ${depstatus} != ${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${DEBASHER_AFTERCORR_PROCESSDEP_TYPE})
                # NOTE: DEBASHER_AFTERCORR_PROCESSDEP_TYPE dependency type currently
                # treated in the same way as DEBASHER_AFTEROK_PROCESSDEP_TYPE
                # dependency
                if [ ${depstatus} != ${DEBASHER_FINISHED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
        esac

        # Return value depending on the dependency separator used
        case "${separator}" in
            ",")
                # "," separator works as operator "and"
                if [ ${dep_ok} -eq 0 ]; then
                    return 1
                fi
            ;;
            "?")
                # "?" separator works as operator "or"
                if [ ${dep_ok} -eq 1 ]; then
                    return 0
                fi
            ;;
            "")
                # "" separator means that only one dependency was
                # defined
                if [ ${dep_ok} -eq 0 ]; then
                    return 1
                else
                    return 0
                fi
            ;;
        esac
    done

    case "${separator}" in
        ",")
            return 0
            ;;
        "?")
            return 1
            ;;
    esac
}

########
debasher_builtin_sched::_process_can_be_executed()
{
    local processname=$1

    # Check there are enough computational resources
    debasher_builtin_sched::_check_comp_res $processname || return 1
    # Check process dependencies are satisfied
    debasher_builtin_sched::_check_process_deps $processname || return 1

    return 0
}

########
debasher_builtin_sched::_get_max_num_tasks()
{
    local processname=$1
    local throttle=${DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE[${processname}]}
    if [ "${throttle}" -eq "${DEBASHER_DEBASHER_ARRAY_TASK_NOTHROTTLE}" ]; then
        local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
        local result=$((array_size - num_inprogress_tasks))
        echo ${result}
    else
        local inprogress_tasks=`debasher_builtin_sched::_get_inprogress_array_task_indices "${dirname}" $processname`
        local num_inprogress_tasks=`debasher::_get_num_words_in_string "${inprogress_tasks}"`
        local result=$((throttle - num_inprogress_tasks))
        echo ${result}
    fi
}

########
debasher_builtin_sched::_update_executable_non_array_process()
{
    local processname=$1
    local status=$2

    if [ ${status} != ${DEBASHER_INPROGRESS_PROCESS_STATUS} -a \
         ${status} != ${DEBASHER_FINISHED_PROCESS_STATUS} -a \
         ${status} != ${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
        if debasher_builtin_sched::_process_can_be_executed ${processname}; then
            BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]=${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}
        fi
    fi
}

########
debasher_builtin_sched::_update_executable_array_process()
{
    local processname=$1
    local status=$2

    if [ ${status} != ${DEBASHER_FINISHED_PROCESS_STATUS} -a \
         ${status} != ${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
        if debasher_builtin_sched::_process_can_be_executed ${processname}; then
            local max_task_num=`debasher_builtin_sched::_get_max_num_tasks ${processname}`
            if [ ${max_task_num} -gt 0 ]; then
                todo_task_indices=`debasher_builtin_sched::_get_todo_array_task_indices "${dirname}" ${processname}`
                todo_task_indices_truncated=`debasher::_get_first_n_fields_of_str "${todo_task_indices}" ${max_task_num}`
                if [ "${todo_task_indices_truncated}" != "" ]; then
                    BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]=${todo_task_indices_truncated}
                fi
            fi
        fi
    fi
}

########
debasher_builtin_sched::_get_executable_processes()
{
    local dirname=$1

    # Iterate over processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        local status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
        if [ ${array_size} -eq 1 ]; then
            # process is not an array
            debasher_builtin_sched::_update_executable_non_array_process ${processname} ${status}
        else
            # process is an array
            debasher_builtin_sched::_update_executable_array_process ${processname} ${status}
        fi
    done
}

########
debasher_builtin_sched::_get_knapsack_cpus_for_process()
{
    local processname=$1

    # Check how many cpus are available
    if [ ${DEBASHER_BUILTIN_SCHED_CPUS} -eq ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        # If available cpus are unlimited, then the number of required
        # cpus to executed the process will be zero, resulting in
        # solutions of the knapsack problem that will not be restricted
        # by this resource
        echo 0
    else
        echo ${DEBASHER_BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
    fi
}

########
debasher_builtin_sched::_get_knapsack_mem_for_process()
{
    local processname=$1

    # Check how much memory are available
    if [ ${DEBASHER_BUILTIN_SCHED_MEM} -eq ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        # If available memory is unlimited, then the amount of memory
        # required to execute the process will be zero, resulting in
        # solutions of the knapsack problem will not be restricted by
        # this resource
        echo 0
    else
        echo ${DEBASHER_BUILTIN_SCHED_PROCESS_MEM[${processname}]}
    fi
}

########
debasher_builtin_sched::_get_knapsack_name()
{
    local processname=$1
    local task_idx=$2

    if [ "${task_idx}" = "" ]; then
        echo "${DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]}"
    else
        echo "${DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]}_${task_idx}"
    fi
}

########
debasher_builtin_sched::_print_knapsack_item_weight_spec()
{
    # Iterate over each executable process generating its required
    # information for the knapsack solver
    local processname
    for processname in "${!BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}"; do
        # Obtain array size
        local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

        # Determine cpu requirements
        local cpus
        cpus=`debasher_builtin_sched::_get_knapsack_cpus_for_process ${processname}`

        # Determine memory requirements
        local mem
        mem=`debasher_builtin_sched::_get_knapsack_mem_for_process ${processname}`

        if [ ${array_size} -eq 1 ]; then
            local knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${processname}`
            echo "${knapsack_name} ${DEBASHER_BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER} ${cpus} ${mem}"
        else
            for id in ${BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]}; do
                local knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${processname} ${id}`
                echo "${knapsack_name} ${DEBASHER_BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER} ${cpus} ${mem}"
            done
        fi
    done
}

########
debasher_builtin_sched::_print_knapsack_pred_spec()
{
    # Iterate over each executable process generating its required
    # information for the knapsack solver
    local processname
    for fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        # Get fifo owner info
        local owner_proc_plus_idx="${DEBASHER_PROGRAM_FIFOS["${fifoname}"]}"
        local owner_proc="${owner_proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
        local owner_idx="${owner_proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
        local owner_array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${owner_proc}]}
        if [ ${owner_array_size} -eq 1 ]; then
            owner_knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${owner_proc}`
        else
            owner_knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${owner_proc} ${owner_idx}`
        fi

        # Get fifo user info
        local user_proc_plus_idx="${DEBASHER_FIFO_USERS["${fifoname}"]}"
        local user_proc="${user_proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
        local user_idx="${user_proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
        local user_array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${user_proc}]}
        if [ ${user_array_size} -eq 1 ]; then
            user_knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${user_proc}`
        else
            user_knapsack_name=`debasher_builtin_sched::_get_knapsack_name ${user_proc} ${user_idx}`
        fi

        # Print knapsack predecessor specification entry
        echo "${owner_knapsack_name} ${user_knapsack_name}"
        echo "${user_knapsack_name} ${owner_knapsack_name}"
    done
}

########
debasher_builtin_sched::_print_knapsack_sol()
{
    local knapsack_item_weight_spec=$1
    local knapsack_pred_spec=$2
    local available_cpus=`debasher_builtin_sched::_get_available_cpus`
    local available_mem=`debasher_builtin_sched::_get_available_mem`
    "${debasher_libexecdir}"/debasher_solve_knapsack_greedy -s "${knapsack_item_weight_spec}" -d "${knapsack_pred_spec}" \
                            -c ${available_cpus},${available_mem} -t ${DEBASHER_BUILTIN_SCHED_SOLVE_TIME_LIMIT}
}

########
debasher_builtin_sched::_solve_knapsack()
{
    local dirname=$1

    # Create file with item and weight specification
    local knapsack_item_weight_spec="${dirname}/${DEBASHER_BUILTIN_SCHED_KNAPSACK_ITEM_WEIGHT_SPEC_FNAME}"
    "${RM}" -f "${knapsack_item_weight_spec}"
    debasher_builtin_sched::_print_knapsack_item_weight_spec > "${knapsack_item_weight_spec}"

    # Create predecessor specification
    local knapsack_pred_spec="${dirname}/${DEBASHER_BUILTIN_SCHED_KNAPSACK_PRED_SPEC_FNAME}"
    "${RM}" -f "${knapsack_pred_spec}"
    debasher_builtin_sched::_print_knapsack_pred_spec > "${knapsack_pred_spec}"

    # Solve knapsack problem
    local knapsack_sol="${dirname}/${DEBASHER_BUILTIN_SCHED_KNAPSACK_SOL_FNAME}"
    local knapsack_sol_stderr="${dirname}/${DEBASHER_BUILTIN_SCHED_KNAPSACK_SOL_STDERR_FNAME}"
    debasher_builtin_sched::_print_knapsack_sol "${knapsack_item_weight_spec}" "${knapsack_pred_spec}" > "${knapsack_sol}" 2> "${knapsack_sol_stderr}"

    # Store solution in output variable
    DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES=`"${AWK}" -F ": " '{if($1=="Packed items") print $2}' "${knapsack_sol}"`
}

########
debasher_builtin_sched::_count_executable_processes()
{
    echo ${#BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}
}

########
debasher_builtin_sched::_inprogress_processes_pending()
{
    # Iterate over processes
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        if [ ${status} = ${DEBASHER_INPROGRESS_PROCESS_STATUS} ]; then
            return 0
        fi
    done

    return 1
}

########
debasher_builtin_sched::_get_debug_process_status_info()
{
    local process_status
    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        process_status="${process_status} ${processname} -> ${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]};"
    done
    echo $process_status
}

########
debasher_builtin_sched::_get_debug_exec_processes_info()
{
    local exec_processes
    local processname
    for processname in "${!BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}"; do
        exec_processes="${exec_processes} ${processname} -> ${BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]};"
    done
    echo $exec_processes
}
########
debasher_builtin_sched::_get_debug_sel_processes_info()
{
    local sel_processes
    local knapsack_name
    for knapsack_name in ${DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES}; do
        sname=`debasher_builtin_sched::_extract_process_from_knapsack_name ${knapsack_name}`
        tidx=`debasher_builtin_sched::_extract_task_idx_from_knapsack_name ${knapsack_name}`
        sel_processes="${sel_processes} ${knapsack_name} -> ${sname},${tidx};"
    done
    echo $sel_processes
}

########
debasher_builtin_sched::_select_processes_to_be_exec()
{
    local dirname=$1

    # Obtain updated status for processes
    local -A BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED
    debasher_builtin_sched::_get_updated_process_status "${dirname}"

    # Update computational resources depending on changes
    debasher_builtin_sched::_update_comp_resources "${dirname}"

    # Set updated status as current one
    debasher_builtin_sched::_fix_updated_process_status

    # Obtain set of processes that can be executed
    local -A BUILTIN_SCHED_EXECUTABLE_PROCESSES
    debasher_builtin_sched::_get_executable_processes "${dirname}"

    if [ ${builtin_sched_debug} -eq 1 ]; then
        local process_status=`debasher_builtin_sched::_get_debug_process_status_info`
        echo "[BUILTIN_SCHED] - DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS: ${process_status}"
        echo "[BUILTIN_SCHED] - COMPUTATIONAL RESOURCES: total cpus= ${DEBASHER_BUILTIN_SCHED_CPUS}, allocated cpus= ${DEBASHER_BUILTIN_SCHED_ALLOC_CPUS}; total mem= ${DEBASHER_BUILTIN_SCHED_MEM}, allocated mem= ${DEBASHER_BUILTIN_SCHED_ALLOC_MEM}"
        local exec_processes=`debasher_builtin_sched::_get_debug_exec_processes_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_EXECUTABLE_PROCESSES: ${exec_processes}" 2>&1
    fi

    # If there are executable processes, select which ones will be executed
    num_exec_processes=${#BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}
    if [ ${num_exec_processes} -gt 0 ]; then
        debasher_builtin_sched::_solve_knapsack "${dirname}"

        if [ ${builtin_sched_debug} -eq 1 ]; then
            local sel_processes=`debasher_builtin_sched::_get_debug_sel_processes_info`
            echo "[BUILTIN_SCHED] - DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES: ${sel_processes}" 2>&1
        fi

        return 0
    else
        # No executable processes were found
        return 1
    fi
}

########
debasher_builtin_sched::_print_pid_to_file()
{
    if [ "${BUILTIN_SCHED_PID_FILENAME}" != "" ]; then
        echo $$ > "${BUILTIN_SCHED_PID_FILENAME}"
    fi
}

########
debasher_builtin_sched::_print_script_header()
{
    local fname=$1
    local dirname=$2
    local processname=$3
    local num_tasks=$4

    echo "DEBASHER_SCRIPT_FILENAME=\"${fname}\""
    echo "DEBASHER_DIR_NAME=\"${dirname}\""
    echo "DEBASHER_PROCESS_NAME=${processname}"
    echo "DEBASHER_NUM_TASKS=${num_tasks}"
    echo "debasher_builtin_sched::_print_pid_to_file"
}

########
debasher_builtin_sched::_execute_funct_plus_postfunct()
{
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4
    local task_idx=$5
    local skip_funct=`debasher::_get_skip_funcname ${processname}`
    local reset_funct=`debasher::_get_reset_funcname ${processname}`
    local post_funct=`debasher::_get_post_funcname ${processname}`

    # Get serialized arguments
    local sargs=`debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`

    # Convert serialized process options to array (result is placed into
    # the DEBASHER_DESERIALIZED_ARGS variable)
    debasher::_deserialize_args "${sargs}"

    # Execute process skip function if it was provided
    if [ "${skip_funct}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        ${skip_funct} "${DEBASHER_DESERIALIZED_ARGS[@]}" && { echo "Warning: execution of ${processname} will be skipped since the process skip function has finished with exit code $?" >&2 ; return 1; }
    fi

    debasher::_display_begin_process_message

    # Reset output directory
    if [ "${reset_funct}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        if [ "${opt_array_size}" -eq 1 ]; then
            debasher::_default_reset_outfiles_for_process "${dirname}" "${processname}"
        else
            debasher::_default_reset_outfiles_for_process_array "${dirname}" "${processname}" "${task_idx}"
        fi
    else
        ${reset_funct} "${DEBASHER_DESERIALIZED_ARGS[@]}"
    fi

    # Execute process function

    DEBASHER_PROCESS_STDOUT_FILENAME=`debasher::_get_process_stdout_filename "${dirname}" "${processname}" "${opt_array_size}" "${task_idx}"`
    "${processname}" "${DEBASHER_DESERIALIZED_ARGS[@]}" | "${TEE}" > "${DEBASHER_PROCESS_STDOUT_FILENAME}"

    local funct_exit_code=${PIPESTATUS[0]}
    if [ ${funct_exit_code} -ne 0 ]; then
        echo "Error: execution of ${processname} failed with exit code ${funct_exit_code}" >&2
    else
        echo "Command or function ${processname} successfully executed" >&2
    fi

    # Execute process post-function
    if [ "${post_funct}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        ${post_funct} "${DEBASHER_DESERIALIZED_ARGS[@]}" || { echo "Error: execution of ${post_funct} failed with exit code $?" >&2 ; return 1; }
    fi

    # Treat errors
    if [ ${funct_exit_code} -ne 0 ]; then
        return 1;
    fi

    # Signal process completion
    debasher::_signal_process_completion "${dirname}" "${processname}" "${task_idx}" "${opt_array_size}" || return 1

    debasher::_display_end_process_message
}

########
debasher_builtin_sched::_print_script_body()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4

    # Write function to be executed
    if [ "${opt_array_size}" -gt 1 ]; then
        echo "CMDLINE=$(printf '%q' "${cmdline}")"
        echo "builtin_task_log_filename=\`debasher::_get_task_log_filename $(printf '%q' "${dirname}") ${processname} \${BUILTIN_ARRAY_TASK_ID}\`"
        echo "debasher_builtin_sched::_execute_funct_plus_postfunct \"\${CMDLINE}\" $(printf '%q' "${dirname}") ${processname} ${opt_array_size} \"\${BUILTIN_ARRAY_TASK_ID}\" > \${builtin_task_log_filename} 2>&1"
    else
        echo "CMDLINE=$(printf '%q' "${cmdline}")"
        local builtin_log_filename=`debasher::_get_process_log_filename "${dirname}" ${processname}`
        echo "debasher_builtin_sched::_execute_funct_plus_postfunct \"\${CMDLINE}\" $(printf '%q' "${dirname}") ${processname} ${opt_array_size} \"\${BUILTIN_ARRAY_TASK_ID}\" > $(printf '%q' "${builtin_log_filename}") 2>&1"
    fi
}

########
debasher_builtin_sched::_print_script_foot()
{
    :
}

########
debasher_builtin_sched::_write_env_vars_and_funcs()
{
    local dirname=$1

    # Write general environment variables and functions
    debasher::_write_env_vars_and_funcs "${dirname}"

    # Write builtin sched environment functions
    declare -f debasher_builtin_sched::_print_pid_to_file
    declare -f debasher_builtin_sched::_execute_funct_plus_postfunct
    declare -f debasher::_seq_execute_builtin
    declare -f debasher_builtin_sched::_get_script_log_filenames
}

########
debasher_builtin_sched::_create_script()
{
    # Init variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4
    local fname=`debasher::_get_script_filename "${dirname}" ${processname}`

    # Write bash shebang
    local BASH_SHEBANG=`debasher::_init_bash_shebang_var`
    echo ${BASH_SHEBANG} > "${fname}" || return 1

    # Write environment variables
    debasher_builtin_sched::_write_env_vars_and_funcs "${dirname}" | debasher::_exclude_readonly_vars >> "${fname}" ; debasher::pipe_fail || return 1

    # Print header
    debasher_builtin_sched::_print_script_header "${fname}" "${dirname}" "${processname}" "${opt_array_size}" >> "${fname}" || return 1

    # Print body
    debasher_builtin_sched::_print_script_body "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}" >> "${fname}" || return 1

    # Print foot
    debasher_builtin_sched::_print_script_foot >> "${fname}" || return 1

    # Give execution permission
    chmod u+x "${fname}" || return 1
}

########
debasher_builtin_sched::_wait_until_file_exists()
{
    local pid_file=$1
    local max_num_iters=$2
    local iterno=1

    while [ ${iterno} -le ${max_num_iters} ]; do
        if [ -f "${pid_file}" ]; then
            return 0
        fi
        iterno=$((iterno + 1))
    done

    return 1
}

########
debasher_builtin_sched::_launch()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local task_idx=$3
    local file=`debasher::_get_script_filename "${dirname}" ${processname}`

    # Enable execution of specific task id
    if [ ${task_idx} = ${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        export BUILTIN_ARRAY_TASK_ID=0
    else
        export BUILTIN_ARRAY_TASK_ID=${task_idx}
    fi

    # Set variable indicating name of file storing PID
    if [ ${task_idx} = ${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        local pid_file=`debasher::_get_processid_filename "${dirname}" ${processname}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    else
        # Write pid
        local pid_file=`debasher::_get_array_taskid_filename "${dirname}" ${processname} ${task_idx}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    fi

    # Execute file
    "${file}" &
    local pid=$!

    # Wait for PID file to be created
    local max_num_iters=10000
    debasher_builtin_sched::_wait_until_file_exists "${pid_file}" ${max_num_iters} || return 1

    # Unset variables
    if [ ${task_idx} != ${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        unset "${task_varname}"
    fi
    unset BUILTIN_SCHED_PID_FILENAME
}

########
debasher_builtin_sched::_execute_process()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local task_idx=$4
    local launched_tasks=${DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]}
    local process_spec=${DEBASHER_BUILTIN_SCHED_PROCESS_SPEC[${processname}]}

    # Execute process

    ## Obtain process status
    local status=`debasher::_get_process_status "${dirname}" ${processname}`
    echo "PROCESS: ${processname} (TASK_IDX: ${task_idx}) ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    # Create script
    local opt_array_size=`debasher::_get_numtasks_for_process "${processname}"`
    if [ "${launched_tasks}" = "" ]; then
        debasher_builtin_sched::_create_script "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}"
    fi

    # Launch script
    local task_array_list=${task_idx}
    debasher_builtin_sched::_launch "${dirname}" "${processname}" "${task_idx}" || { echo "Error while launching process!" >&2 ; return 1; }

    # Update register of launched tasks
    if [ "${launched_tasks}" = "" ]; then
        DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]=$task_idx
    else
        DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]="${DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]} $task_idx"
    fi
}

########
debasher_builtin_sched::_extract_process_from_knapsack_name()
{
    local knapsack_name=$1
    local process_idx=`echo "${knapsack_name}" | "${AWK}" -F "_" '{print $1}'`
    echo ${DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME[${process_idx}]}
}

########
debasher_builtin_sched::_extract_task_idx_from_knapsack_name()
{
    local knapsack_name=$1
    local tidx=`echo "${knapsack_name}" | "${AWK}" -F "_" '{print $2}'`
    if [ "${tidx}" = "" ]; then
        echo ${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}
    else
        echo ${tidx}
    fi
}

########
debasher_builtin_sched::_exec_processes_and_update_status()
{
    local cmdline=$1
    local dirname=$2

    local knapsack_name
    for knapsack_name in ${DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES}; do
        # Extract process name and task id
        processname=`debasher_builtin_sched::_extract_process_from_knapsack_name "${knapsack_name}"`
        task_idx=`debasher_builtin_sched::_extract_task_idx_from_knapsack_name "${knapsack_name}"`

        # Execute process
        debasher_builtin_sched::_execute_process "${cmdline}" "${dirname}" "${processname}" "${task_idx}" || return 1

        # Update process status
        BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]=${DEBASHER_INPROGRESS_PROCESS_STATUS}
    done

    # Reset variable
    DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES=""
}

########
debasher_builtin_sched::_exec_processes()
{
    local cmdline=$1
    local dirname=$2

    # Execute selected processes and update status accordingly
    if [ "${DEBASHER_BUILTIN_SCHED_SELECTED_PROCESSES}" != "" ]; then
        local -A BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED
        debasher_builtin_sched::_exec_processes_and_update_status "${cmdline}" "${dirname}"
    fi

    # Update computational resources after execution
    debasher_builtin_sched::_update_comp_resources "${dirname}"

    # Set updated status as current one
    debasher_builtin_sched::_fix_updated_process_status
}

########
debasher_builtin_sched::_clean_process_files()
{
    clean_process_id_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local processid_file=`debasher::_get_processid_filename "${dirname}" ${processname}`
        "${RM}" -f "${processid_file}"
    }

    clean_process_id_files_array()
    {
        local dirname=$1
        local processname=$2
        local idx=$3

        local array_taskid_file=`debasher::_get_array_taskid_filename "${dirname}" ${processname} ${idx}`
        if [ -f "${array_taskid_file}" ]; then
            "${RM}" "${array_taskid_file}"
        fi
    }

    clean_process_log_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local builtin_log_filename=`debasher::_get_process_log_filename "${dirname}" ${processname}`
        "${RM}" -f "${builtin_log_filename}"
    }

    clean_process_log_files_array()
    {
        local dirname=$1
        local processname=$2
        local idx=$3

        local builtin_task_log_filename=`debasher::_get_task_log_filename "${dirname}" ${processname} ${idx}`
        if [ -f "${builtin_task_log_filename}" ]; then
            "${RM}" "${builtin_task_log_filename}"
        fi
    }

    local dirname=$1
    local processname=$2
    local array_size=${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        clean_process_id_files_non_array "${dirname}" "${processname}"
        clean_process_log_files_non_array "${dirname}" "${processname}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`debasher_builtin_sched::_get_pending_array_task_indices "${dirname}" ${processname}`
        if [ "${pending_tasks}" != "" ]; then
            # Iterate over pending tasks
            local idx
            for idx in $pending_tasks; do
                clean_process_id_files_array "${dirname}" "${processname}" "${idx}"
                clean_process_log_files_array "${dirname}" "${processname}" "${idx}"
            done
        fi
    fi
}

########
debasher_builtin_sched::_prepare_files_and_dirs_for_process()
{
    local dirname=$1
    local processname=$2
    local script_filename=`debasher::_get_script_filename "${dirname}" ${processname}`
    local process_spec=${DEBASHER_BUILTIN_SCHED_PROCESS_SPEC[${processname}]}

    # Obtain process status
    local status=${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}

    if [ "${status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" -a "${status}" != "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        # Obtain array size
        local array_size=`debasher::_get_numtasks_for_process "${processname}"`

        # Prepare files and directories for process
        if [ "${status}" = "${DEBASHER_TODO_PROCESS_STATUS}" ]; then
            debasher::_create_exec_dir_for_process "${dirname}" "${processname}" || { echo "Error when creating exec directory for process" >&2 ; return 1; }
            debasher::_create_shdirs_owned_by_process "${processname}" || { echo "Error when creating shared directories determined by script option definition" >&2 ; return 1; }
        else
            debasher_builtin_sched::_clean_process_files "${dirname}" ${processname} || { echo "Error when cleaning log files for process" >&2 ; return 1; }
        fi
        debasher::_prepare_fifos_owned_by_process ${processname}

        # Create output directory
        debasher::_create_outdir_for_process "${dirname}" ${processname} || { echo "Error when creating output directory for process" >&2 ; return 1; }
    fi
}

########
debasher_builtin_sched::_prepare_files_and_dirs_for_processes()
{
    local dirname=$1

    local processname
    for processname in "${!DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        debasher_builtin_sched::_prepare_files_and_dirs_for_process "${dirname}" $processname
    done
}

########
debasher_builtin_sched::_sleep()
{
    # Sleep a certain number of seconds depending on the number of
    # program processes
    local num_processes=${#DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[@]}

    if [ ${num_processes} -le ${DEBASHER_BUILTIN_SCHED_NPROCESSES_SLEEP_THRESHOLD} ]; then
        "${SLEEP}" ${DEBASHER_BUILTIN_SCHED_SLEEP_TIME_SHORT}
    else
        "${SLEEP}" ${DEBASHER_BUILTIN_SCHED_SLEEP_TIME_LONG}
    fi
}

########
debasher_builtin_sched::execute_program_processes()
{
    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3
    local iterno=1

    echo "* Configuring scheduler..." >&2
    if [ ${builtin_sched_cpus_given} -eq 1 ]; then
        DEBASHER_BUILTIN_SCHED_CPUS=${builtin_sched_cpus}
    fi

    if [ ${builtin_sched_mem_given} -eq 1 ]; then
        DEBASHER_BUILTIN_SCHED_MEM=${builtin_sched_mem}
    fi
    echo "- Available CPUS: ${DEBASHER_BUILTIN_SCHED_CPUS}" >&2
    echo "- Available memory: ${DEBASHER_BUILTIN_SCHED_MEM}" >&2
    echo "" >&2

    echo "* Initializing data structures..." >&2

    # Initialize process information
    debasher_builtin_sched::_init_process_info "${cmdline}" "${dirname}" "${procspec_file}" || return 1

    # Revise process status for processes to be reexecuted
    debasher_builtin_sched::_revise_reexec_proc_status || return 1

    # Initialize current computational resources
    debasher_builtin_sched::_init_curr_comp_resources || return 1

    # Prepare files and directories for processes
    debasher_builtin_sched::_prepare_files_and_dirs_for_processes "${dirname}"

    echo "" >&2

    echo "* Executing program processes..." >&2

    # Execute scheduling loop
    local end=0
    while [ ${end} -eq 0 ]; do
        if [ ${builtin_sched_debug} -eq 1 ]; then
            echo "[BUILTIN_SCHED] * Iteration ${iterno}" 2>&1
        fi

        # Select processes that should be executed
        if debasher_builtin_sched::_select_processes_to_be_exec "${dirname}"; then
            # Execute processes
            debasher_builtin_sched::_exec_processes "${cmdline}" "${dirname}"

            # Wait before starting a new loop
            debasher_builtin_sched::_sleep
        else
            # There are no processes to be executed

            if debasher_builtin_sched::_inprogress_processes_pending; then
                # Wait for in-progress processes to finish
                debasher_builtin_sched::_sleep
            else
                # Finish loop
                end=1
            fi
        fi

        iterno=$((iterno + 1))
    done

    echo "" >&2
}

########
debasher_builtin_sched::_get_script_log_filenames()
{
    local exec_dirname=$1

    find "${exec_dirname}" -name "*.${DEBASHER_SCHED_LOG_FEXT}" -exec echo {} \;
}
