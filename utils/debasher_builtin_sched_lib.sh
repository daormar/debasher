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
BUILTIN_SCHED_FAILED_PROCESS_STATUS="FAILED"
BUILTIN_SCHED_NO_ARRAY_TASK="NO_ARRAY_TASK"
BUILTIN_SCHED_SLEEP_TIME_LONG=5
BUILTIN_SCHED_SLEEP_TIME_SHORT=1
BUILTIN_SCHED_NPROCESSES_SLEEP_THRESHOLD=10
BUILTIN_SCHED_KNAPSACK_SPEC_FNAME=.knapsack_spec.txt
BUILTIN_SCHED_KNAPSACK_SOL_FNAME=.knapsack_sol.txt
BUILTIN_SCHED_UNLIMITED_CPUS=0
BUILTIN_SCHED_UNLIMITED_MEM=0
BUILTIN_SCHED_SOLVE_TIME_LIMIT=1
BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER=1

# ARRAY TASK STATUSES
BUILTIN_SCHED_FINISHED_TASK_STATUS="FINISHED"
BUILTIN_SCHED_INPROGRESS_TASK_STATUS="IN-PROGRESS"
BUILTIN_SCHED_FAILED_TASK_STATUS="FAILED"
BUILTIN_SCHED_TODO_TASK_STATUS="TO-DO"

####################
# GLOBAL VARIABLES #
####################

# Declare built-in scheduler-related variables
declare -A BUILTIN_SCHED_PROCESSNAME_TO_IDX
declare -A BUILTIN_SCHED_IDX_TO_PROCESSNAME
declare -A BUILTIN_SCHED_PROCESS_SCRIPT_FILENAME
declare -A BUILTIN_SCHED_PROCESS_SPEC
declare -A BUILTIN_SCHED_PROCESS_DEPS
declare -A BUILTIN_SCHED_PROCESS_ARRAY_SIZE
declare -A BUILTIN_SCHED_PROCESS_THROTTLE
declare -A BUILTIN_SCHED_PROCESS_CPUS
declare -A BUILTIN_SCHED_PROCESS_ALLOC_CPUS
declare -A BUILTIN_SCHED_PROCESS_MEM
declare -A BUILTIN_SCHED_PROCESS_ALLOC_MEM
declare -A BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS
declare -A BUILTIN_SCHED_CURR_PROCESS_STATUS
declare BUILTIN_SCHED_SELECTED_PROCESSES
declare BUILTIN_SCHED_CPUS=1
declare BUILTIN_SCHED_MEM=256
declare BUILTIN_SCHED_ALLOC_CPUS=0
declare BUILTIN_SCHED_ALLOC_MEM=0

###############################
# BUILTIN SCHEDULER FUNCTIONS #
###############################

########
builtin_sched_cpus_within_limit()
{
    local cpus=$1
    if [ ${BUILTIN_SCHED_CPUS} -eq 0 ]; then
        return 0
    else
        if [ ${BUILTIN_SCHED_CPUS} -ge $cpus ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
builtin_sched_mem_within_limit()
{
    local mem=$1
    if [ ${BUILTIN_SCHED_MEM} -eq 0 ]; then
        return 0
    else
        if [ ${BUILTIN_SCHED_MEM} -ge $mem ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
builtin_sched_update_processname_to_idx_info()
{
    local processname=$1
    if [ ${BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]} = ""]; then
        local len=${#BUILTIN_SCHED_PROCESSNAME_TO_IDX[@]}
        BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]=${len}
        BUILTIN_SCHED_IDX_TO_PROCESSNAME[${len}]=${processname}
    fi
}

########
builtin_sched_init_process_info()
{
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`extract_processname_from_process_spec "$process_spec"`
            local script_filename=`get_script_filename "${dirname}" ${processname}`
            local status=`get_process_status "${dirname}" ${processname}`
            local processdeps=`extract_processdeps_from_process_spec "$process_spec"`
            local spec_throttle=`extract_attr_from_process_spec "$process_spec" "throttle"`
            local sched_throttle=`get_scheduler_throttle ${spec_throttle}`
            local array_size=`get_numtasks_for_process "${processname}"`

            # Get cpus info
            local cpus=`extract_cpus_from_process_spec "$process_spec"`
            str_is_natural_number ${cpus} || { echo "Error: number of cpus ($cpus) for $processname should be a natural number" >&2; return 1; }

            # Get mem info (NOTE: if multiple attempts specified, keep
            # memory specification of the first one)
            local mem=`extract_mem_from_process_spec "$process_spec"`
            local attempt_no=1
            mem=`get_mem_attempt_value ${mem} ${attempt_no}`
            mem=`convert_mem_value_to_mb ${mem}` || { echo "Invalid memory specification for process ${processname}" >&2; return 1; }
            str_is_natural_number ${mem} || { echo "Error: amount of memory ($mem) for $processname should be a natural number" >&2; return 1; }

            # Obtain full throttle cpus value
            local full_throttle_cpus=${cpus}
            if [ $array_size -gt 1 ]; then
                full_throttle_cpus=$((cpus * sched_throttle))
            fi

            # Check full_throttle_cpus value
            builtin_sched_cpus_within_limit ${full_throttle_cpus} || { echo "Error: number of cpus for process $processname exceeds limit (cpus: ${cpus}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Obtain full throttle mem value
            local full_throttle_mem=${mem}
            if [ $array_size -gt 1 ]; then
                full_throttle_mem=$((mem * sched_throttle))
            fi
            # Check mem value
            builtin_sched_mem_within_limit ${full_throttle_mem} || { echo "Error: amount of memory for process $processname exceeds limit (mem: ${mem}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Register process information
            builtin_sched_update_processname_to_idx_info ${processname}
            BUILTIN_SCHED_PROCESS_SCRIPT_FILENAME[${processname}]=${script_filename}
            BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${status}
            BUILTIN_SCHED_PROCESS_SPEC[${processname}]="${process_spec}"
            BUILTIN_SCHED_PROCESS_DEPS[${processname}]=${processdeps}
            BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]=${array_size}
            BUILTIN_SCHED_PROCESS_THROTTLE[${processname}]=${sched_throttle}
            BUILTIN_SCHED_PROCESS_CPUS[${processname}]=${cpus}
            BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=0
            BUILTIN_SCHED_PROCESS_MEM[${processname}]=${mem}
            BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=0
        fi
    done < "${procspec_file}"
}

########
builtin_sched_release_mem()
{
    local processname=$1

    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM - ${BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]}))
    BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=0
}

########
builtin_sched_release_cpus()
{
    local processname=$1

    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS - ${BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]}))
    BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=0
}

########
builtin_sched_get_process_mem()
{
    local processname=$1

    echo ${BUILTIN_SCHED_PROCESS_MEM[${processname}]}
}

########
builtin_sched_get_process_mem_given_num_tasks()
{
    local processname=$1
    local ntasks=$2

    if [ ${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]} -eq 1 ]; then
        echo ${BUILTIN_SCHED_PROCESS_MEM[${processname}]}
    else
        echo $((${BUILTIN_SCHED_PROCESS_MEM[${processname}]} * ntasks))
    fi
}

########
builtin_sched_reserve_mem()
{
    local processname=$1
    local process_mem=`builtin_sched_get_process_mem ${processname}`
    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM + process_mem))
    BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=${process_mem}
}

########
builtin_sched_get_process_cpus()
{
    local processname=$1

    echo ${BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
}

########
builtin_sched_get_process_cpus_given_num_tasks()
{
    local processname=$1
    local ntasks=$2

    if [ ${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]} -eq 1 ]; then
        echo ${BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
    else
        echo $((${BUILTIN_SCHED_PROCESS_CPUS[${processname}]} * ntasks))
    fi
}

########
builtin_sched_reserve_cpus()
{
    local processname=$1
    local process_cpus=`builtin_sched_get_process_cpus ${processname}`
    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS + process_cpus))
    BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=${process_cpus}
}

########
builtin_sched_get_array_task_status()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3
    local processdirname=`get_process_outdir_given_dirname "${dirname}" ${processname}`
    local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`
    local array_taskid_file=`get_array_taskid_filename "${execdir}" ${processname} ${task_idx}`

    if [ ! -f ${array_taskid_file} ]; then
        # Task is not started
        echo ${BUILTIN_SCHED_TODO_TASK_STATUS}
    else
        # Task was started
        if array_task_is_finished "${dirname}" ${processname} ${task_idx}; then
            echo ${BUILTIN_SCHED_FINISHED_TASK_STATUS}
        else
            # Task is not finished
            local id=`"${CAT}" "${array_taskid_file}"`
            if id_exists $id; then
                echo ${BUILTIN_SCHED_INPROGRESS_TASK_STATUS}
            else
                echo ${BUILTIN_SCHED_FAILED_TASK_STATUS}
            fi
        fi
    fi
}

########
builtin_sched_get_failed_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
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
builtin_sched_get_finished_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${BUILTIN_SCHED_FINISHED_TASK_STATUS} ]; then
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
builtin_sched_get_inprogress_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${INPROGRESS_PROCESS_STATUS} ]; then
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
builtin_sched_get_todo_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${BUILTIN_SCHED_TODO_TASK_STATUS} ]; then
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
builtin_sched_get_pending_array_task_indices()
{
    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
    local result

    local task_idx
    local last_task_idx=$((array_size - 1))
    for task_idx in `"${SEQ}" 0 ${last_task_idx}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $processname $task_idx`
        if [ ${task_status} = ${BUILTIN_SCHED_TODO_TASK_STATUS} -o ${task_status} = ${BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
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
builtin_sched_revise_array_mem()
{
    local dirname=$1
    local processname=$2

    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" ${processname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`
    local process_revised_mem=`builtin_sched_get_process_mem_given_num_tasks ${processname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM - ${BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]} + process_revised_mem))
    BUILTIN_SCHED_PROCESS_ALLOC_MEM[${processname}]=${process_revised_mem}
}

########
builtin_sched_revise_array_cpus()
{
    local dirname=$1
    local processname=$2

    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" ${processname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`
    local process_revised_cpus=`builtin_sched_get_process_cpus_given_num_tasks ${processname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS - ${BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]} + process_revised_cpus))
    BUILTIN_SCHED_PROCESS_ALLOC_CPUS[${processname}]=${process_revised_cpus}
}

########
builtin_sched_init_curr_comp_resources()
{
    # Iterate over defined processes
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        if [ ${status} = ${INPROGRESS_PROCESS_STATUS} ]; then
            builtin_sched_reserve_mem $processname
            builtin_sched_reserve_cpus $processname
        fi
    done
}

########
builtin_sched_get_updated_process_status()
{
    local dirname=$1

    # Iterate over defined processes
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[$processname]}
        if [ ${status} != ${BUILTIN_SCHED_FAILED_PROCESS_STATUS} -a ${status} != ${FINISHED_PROCESS_STATUS} ]; then
            local updated_status=`get_process_status "${dirname}" ${processname}`
            BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]=${updated_status}
        fi
    done
}

########
builtin_sched_update_comp_resources()
{
    local dirname=$1

    # Iterate over processes
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        prev_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        updated_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
        if [ "${updated_status}" != "" ]; then
            # Store array size in variable
            process_array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

            # Check if resources should be released
            if [ ${prev_status} = ${INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${INPROGRESS_PROCESS_STATUS} ]; then
                builtin_sched_release_mem $processname
                builtin_sched_release_cpus $processname
            fi

            # Check if resources should be reserved
            if [ ${prev_status} != ${INPROGRESS_PROCESS_STATUS} -a ${updated_status} = ${INPROGRESS_PROCESS_STATUS} ]; then
                if [ ${process_array_size} -eq 1 ]; then
                    builtin_sched_reserve_mem $processname
                    builtin_sched_reserve_cpus $processname
                else
                    # process is an array
                    builtin_sched_revise_array_mem "${dirname}" $processname
                    builtin_sched_revise_array_cpus "${dirname}" $processname
                fi
            fi

            # Check if resources of job array should be revised
            if [ ${process_array_size} -gt 1 -a ${prev_status} = ${INPROGRESS_PROCESS_STATUS} -a ${updated_status} = ${INPROGRESS_PROCESS_STATUS} ]; then
                builtin_sched_revise_array_mem "${dirname}" $processname
                builtin_sched_revise_array_cpus "${dirname}" $processname
            fi
        fi
    done
}

########
builtin_sched_fix_updated_process_status()
{
    # Copy updated status into current status
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        prev_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        updated_status=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
        if [ "${updated_status}" != "" ]; then
            if [ ${prev_status} = ${INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${INPROGRESS_PROCESS_STATUS} -a ${updated_status} != ${UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS} -a ${updated_status} != ${FINISHED_PROCESS_STATUS} ]; then
                # Status will be set to failed if previous status was
                # in-progress and new status is unfinished
                BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${BUILTIN_SCHED_FAILED_PROCESS_STATUS}
            else
                BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]=${BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]}
            fi
        fi
    done
}

########
builtin_sched_get_available_cpus()
{
    if [ ${BUILTIN_SCHED_CPUS} -eq ${BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        echo 0
    else
        echo $((BUILTIN_SCHED_CPUS - BUILTIN_SCHED_ALLOC_CPUS))
    fi
}

########
builtin_sched_get_available_mem()
{
    if [ ${BUILTIN_SCHED_MEM} -eq ${BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        echo 0
    else
        echo $((BUILTIN_SCHED_MEM - BUILTIN_SCHED_ALLOC_MEM))
    fi
}

########
builtin_sched_check_comp_res()
{
    local processname=$1

    if [ ${BUILTIN_SCHED_CPUS} -ne ${BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        local available_cpus=`builtin_sched_get_available_cpus`
        process_cpus=`builtin_sched_get_process_cpus ${processname}`
        if [ ${process_cpus} -gt ${available_cpus} ]; then
            return 1
        fi
    fi

    if [ ${BUILTIN_SCHED_MEM} -ne ${BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        local available_mem=`builtin_sched_get_available_mem`
        process_mem=`builtin_sched_get_process_mem ${processname}`
        if [ ${process_mem} -gt ${available_mem} ]; then
            return 1
        fi
    fi

    return 0
}

########
builtin_sched_check_process_deps()
{
    local processname=$1
    local processdeps=${BUILTIN_SCHED_PROCESS_DEPS[${processname}]}

    # Iterate over dependencies
    local separator=`get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi
    local dep
    for dep in ${processdeps_blanks}; do
        # Extract information from dependency
        local deptype=`get_deptype_part_in_dep ${dep}`
        local depsname=`get_processname_part_in_dep ${dep}`

        # Process dependency
        depstatus=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${depsname}]}

        # Process exit code
        local dep_ok=1
        case ${deptype} in
            ${AFTER_PROCESSDEP_TYPE})
                if [ ${depstatus} = ${TODO_PROCESS_STATUS} -o  ${depstatus} = ${UNFINISHED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTEROK_PROCESSDEP_TYPE})
                if [ ${depstatus} != ${FINISHED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTERNOTOK_PROCESSDEP_TYPE})
                if [ ${depstatus} != ${BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTERANY_PROCESSDEP_TYPE})
                if [ ${depstatus} = ${FINISHED_PROCESS_STATUS} -o ${depstatus} = ${BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTERCORR_PROCESSDEP_TYPE})
                # NOTE: AFTERCORR_PROCESSDEP_TYPE dependency type currently
                # treated in the same way as AFTEROK_PROCESSDEP_TYPE
                # dependency
                if [ ${depstatus} != ${FINISHED_PROCESS_STATUS} ]; then
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
builtin_sched_process_can_be_executed()
{
    local processname=$1

    # Check there are enough computational resources
    builtin_sched_check_comp_res $processname || return 1
    # Check process dependencies are satisfied
    builtin_sched_check_process_deps $processname || return 1

    return 0
}

########
builtin_sched_get_max_num_tasks()
{
    local processname=$1
    local throttle=${BUILTIN_SCHED_PROCESS_THROTTLE[${processname}]}
    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" $processname`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`
    local result=$((throttle - num_inprogress_tasks))
    echo ${result}
}

########
builtin_sched_update_executable_non_array_process()
{
    local processname=$1
    local status=$2

    if [ ${status} != ${INPROGRESS_PROCESS_STATUS} -a \
         ${status} != ${FINISHED_PROCESS_STATUS} -a \
         ${status} != ${BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
        if builtin_sched_process_can_be_executed ${processname}; then
            BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]=${BUILTIN_SCHED_NO_ARRAY_TASK}
        fi
    fi
}

########
builtin_sched_update_executable_array_process()
{
    local processname=$1
    local status=$2

    if [ ${status} != ${FINISHED_PROCESS_STATUS} -a \
         ${status} != ${BUILTIN_SCHED_FAILED_PROCESS_STATUS} ]; then
        if builtin_sched_process_can_be_executed ${processname}; then
            local max_task_num=`builtin_sched_get_max_num_tasks ${processname}`
            if [ ${max_task_num} -gt 0 ]; then
                todo_task_indices=`builtin_sched_get_todo_array_task_indices "${dirname}" ${processname}`
                todo_task_indices_truncated=`get_first_n_fields_of_str "${todo_task_indices}" ${max_task_num}`
                if [ "${todo_task_indices_truncated}" != "" ]; then
                    BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]=${todo_task_indices_truncated}
                fi
            fi
        fi
    fi
}

########
builtin_sched_get_executable_processes()
{
    local dirname=$1

    # Iterate over processes
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        local status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}
        if [ ${array_size} -eq 1 ]; then
            # process is not an array
            builtin_sched_update_executable_non_array_process ${processname} ${status}
        else
            # process is an array
            builtin_sched_update_executable_array_process ${processname} ${status}
        fi
    done
}

########
builtin_sched_get_knapsack_cpus_for_process()
{
    local processname=$1

    # Check how many cpus are available
    if [ ${BUILTIN_SCHED_CPUS} -eq ${BUILTIN_SCHED_UNLIMITED_CPUS} ]; then
        # If available cpus are unlimited, then the number of required
        # cpus to executed the process will be zero, resulting in
        # solutions of the knapsack problem that will not be restricted
        # by this resource
        echo 0
    else
        echo ${BUILTIN_SCHED_PROCESS_CPUS[${processname}]}
    fi
}

########
builtin_sched_get_knapsack_mem_for_process()
{
    local processname=$1

    # Check how much memory are available
    if [ ${BUILTIN_SCHED_MEM} -eq ${BUILTIN_SCHED_UNLIMITED_MEM} ]; then
        # If available memory is unlimited, then the amount of memory
        # required to execute the process will be zero, resulting in
        # solutions of the knapsack problem will not be restricted by
        # this resource
        echo 0
    else
        echo ${BUILTIN_SCHED_PROCESS_MEM[${processname}]}
    fi
}

########
builtin_sched_get_knapsack_name()
{
    local processname=$1
    local task_idx=$2

    if [ "${task_idx}" = "" ]; then
        echo "${BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]}"
    else
        echo "${BUILTIN_SCHED_PROCESSNAME_TO_IDX[${processname}]}_${task_idx}"
    fi
}

########
builtin_sched_print_knapsack_spec()
{
    # Process each executable process generating its required
    # information for the knapsack solver
    local processname
    for processname in "${!BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}"; do
        # Obtain array size
        local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

        # Determine cpu requirements
        cpus=`builtin_sched_get_knapsack_cpus_for_process ${processname}`

        # Determine memory requirements
        mem=`builtin_sched_get_knapsack_mem_for_process ${processname}`

        if [ ${array_size} -eq 1 ]; then
            local knapsack_name=`builtin_sched_get_knapsack_name ${processname}`
            echo "${knapsack_name} ${BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER} ${cpus} ${mem}"
        else
            for id in ${BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]}; do
                local knapsack_name=`builtin_sched_get_knapsack_name ${processname} ${id}`
                echo "${knapsack_name} ${BUILTIN_SCHED_PROCESS_VALUE_FOR_KNAPSACK_SOLVER} ${cpus} ${mem}"
            done
        fi
    done
}

########
builtin_sched_print_knapsack_sol()
{
    local available_cpus=`builtin_sched_get_available_cpus`
    local available_mem=`builtin_sched_get_available_mem`
    "${debasher_libexecdir}"/debasher_solve_knapsack_ga -s "${specfile}" -c ${available_cpus},${available_mem} -t ${BUILTIN_SCHED_SOLVE_TIME_LIMIT}
}

########
builtin_sched_solve_knapsack()
{
    local dirname=$1

    # Create file with item and weight specification
    specfile="${dirname}/${BUILTIN_SCHED_KNAPSACK_SPEC_FNAME}"
    "${RM}" -f "${specfile}"
    builtin_sched_print_knapsack_spec > "${specfile}"

    # Solve knapsack problem
    local knapsack_sol="${dirname}/${BUILTIN_SCHED_KNAPSACK_SOL_FNAME}"
    builtin_sched_print_knapsack_sol > "${knapsack_sol}"

    # Store solution in output variable
    BUILTIN_SCHED_SELECTED_PROCESSES=`"${AWK}" -F ": " '{if($1=="Packed items") print $2}' "${knapsack_sol}"`
}

########
builtin_sched_count_executable_processes()
{
    echo ${#BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}
}

########
builtin_sched_inprogress_processes_pending()
{
    # Iterate over processes
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]}
        if [ ${status} = ${INPROGRESS_PROCESS_STATUS} ]; then
            return 0
        fi
    done

    return 1
}

########
builtin_sched_get_debug_process_status_info()
{
    local process_status
    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        process_status="${process_status} ${processname} -> ${BUILTIN_SCHED_CURR_PROCESS_STATUS[${processname}]};"
    done
    echo $process_status
}

########
builtin_sched_get_debug_exec_processes_info()
{
    local exec_processes
    local processname
    for processname in "${!BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}"; do
        exec_processes="${exec_processes} ${processname} -> ${BUILTIN_SCHED_EXECUTABLE_PROCESSES[${processname}]};"
    done
    echo $exec_processes
}
########
builtin_sched_get_debug_sel_processes_info()
{
    local sel_processes
    local knapsack_name
    for knapsack_name in ${BUILTIN_SCHED_SELECTED_PROCESSES}; do
        sname=`builtinsched_extract_process_from_knapsack_name ${knapsack_name}`
        tidx=`builtinsched_extract_task_idx_from_knapsack_name ${knapsack_name}`
        sel_processes="${sel_processes} ${knapsack_name} -> ${sname},${tidx};"
    done
    echo $sel_processes
}

########
builtin_sched_select_processes_to_be_exec()
{
    local dirname=$1

    # Obtain updated status for processes
    local -A BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED
    builtin_sched_get_updated_process_status "${dirname}"

    # Update computational resources depending on changes
    builtin_sched_update_comp_resources "${dirname}"

    # Set updated status as current one
    builtin_sched_fix_updated_process_status

    # Obtain set of processes that can be executed
    local -A BUILTIN_SCHED_EXECUTABLE_PROCESSES
    builtin_sched_get_executable_processes "${dirname}"

    if [ ${builtinsched_debug} -eq 1 ]; then
        local process_status=`builtin_sched_get_debug_process_status_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_CURR_PROCESS_STATUS: ${process_status}"
        echo "[BUILTIN_SCHED] - COMPUTATIONAL RESOURCES: total cpus= ${BUILTIN_SCHED_CPUS}, allocated cpus= ${BUILTIN_SCHED_ALLOC_CPUS}; total mem= ${BUILTIN_SCHED_MEM}, allocated mem= ${BUILTIN_SCHED_ALLOC_MEM}"
        local exec_processes=`builtin_sched_get_debug_exec_processes_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_EXECUTABLE_PROCESSES: ${exec_processes}" 2>&1
    fi

    # If there are executable processes, select which ones will be executed
    num_exec_processes=${#BUILTIN_SCHED_EXECUTABLE_PROCESSES[@]}
    if [ ${num_exec_processes} -gt 0 ]; then
        builtin_sched_solve_knapsack "${dirname}"

        if [ ${builtinsched_debug} -eq 1 ]; then
            local sel_processes=`builtin_sched_get_debug_sel_processes_info`
            echo "[BUILTIN_SCHED] - BUILTIN_SCHED_SELECTED_PROCESSES: ${sel_processes}" 2>&1
        fi

        return 0
    else
        # No executable processes were found
        return 1
    fi
}

########
builtin_sched_print_pid_to_file()
{
    if [ "${BUILTIN_SCHED_PID_FILENAME}" != "" ]; then
        echo $$ > "${BUILTIN_SCHED_PID_FILENAME}"
    fi
}

########
builtin_sched_print_script_header()
{
    local fname=$1
    local dirname=$2
    local processname=$3
    local num_tasks=$4

    echo "DEBASHER_SCRIPT_FILENAME=\"${fname}\""
    echo "DEBASHER_DIR_NAME=\"${dirname}\""
    echo "DEBASHER_PROCESS_NAME=${processname}"
    echo "DEBASHER_NUM_TASKS=${num_tasks}"
    echo "builtin_sched_print_pid_to_file"
}

########
builtin_sched_execute_funct_plus_postfunct()
{
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4
    local task_idx=$5
    local skip_funct=`get_skip_funcname ${processname}`
    local reset_funct=`get_reset_funcname ${processname}`
    local comm_or_funct=`get_exec_command_or_funcname ${processname}`
    local comm_varname=`get_exec_commvar ${processname}`
    local end_of_opts_marker=`get_end_of_options_marker ${processname}`
    local post_funct=`get_post_funcname ${processname}`

    # Get serialized arguments
    local sargs=`get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`

    # Convert serialized process options to array (result is placed into
    # the DESERIALIZED_ARGS variable)
    deserialize_args "${sargs}"

    # Execute process skip function if it was provided
    if [ "${skip_funct}" != ${FUNCT_NOT_FOUND} ]; then
        ${skip_funct} "${DESERIALIZED_ARGS[@]}" && { echo "Warning: execution of ${processname} will be skipped since the process skip function has finished with exit code $?" >&2 ; return 1; }
    fi

    display_begin_process_message

    # Reset output directory
    if [ "${reset_funct}" = ${FUNCT_NOT_FOUND} ]; then
        if [ "${opt_array_size}" -eq 1 ]; then
            default_reset_outfiles_for_process "${dirname}" "${processname}"
        else
            default_reset_outfiles_for_process_array "${dirname}" "${processname}" "${task_idx}"
        fi
    else
        ${reset_funct} "${DESERIALIZED_ARGS[@]}"
    fi

    # Execute process function
    DEBASHER_PROCESS_STDOUT_FILENAME=`get_process_stdout_filename "${dirname}" "${processname}" "${opt_array_size}" "${task_idx}"`
    ${comm_or_funct} "${!comm_varname}" "${end_of_opts_marker}" "${DESERIALIZED_ARGS[@]}" | "${TEE}" > "${DEBASHER_PROCESS_STDOUT_FILENAME}"
    local funct_exit_code=${PIPESTATUS[0]}
    if [ ${funct_exit_code} -ne 0 ]; then
        echo "Error: execution of ${comm_or_funct} failed with exit code ${funct_exit_code}" >&2
    else
        echo "Command or function ${comm_or_funct} successfully executed" >&2
    fi

    # Execute process post-function
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        ${post_funct} "${DESERIALIZED_ARGS[@]}" || { echo "Error: execution of ${post_funct} failed with exit code $?" >&2 ; return 1; }
    fi

    # Treat errors
    if [ ${funct_exit_code} -ne 0 ]; then
        return 1;
    fi

    # Signal process completion
    signal_process_completion "${dirname}" "${processname}" "${task_idx}" "${opt_array_size}" || return 1

    display_end_process_message
}

########
builtin_sched_print_script_body()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4

    # Write function to be executed
    if [ "${opt_array_size}" -gt 1 ]; then
        echo "CMDLINE=\"$(esc_dq "${cmdline}")\""
        echo "builtin_task_log_filename=\`get_task_log_filename \"$(esc_dq "${dirname}")\" ${processname} \${BUILTIN_ARRAY_TASK_ID}\`"
        echo "builtin_sched_execute_funct_plus_postfunct \"\${CMDLINE}\" \"$(esc_dq "${dirname}")\" ${processname} ${opt_array_size} \"\${BUILTIN_ARRAY_TASK_ID}\" > \${builtin_task_log_filename} 2>&1"
    else
        echo "CMDLINE=\"$(esc_dq "${cmdline}")\""
        local builtin_log_filename=`get_process_log_filename "${dirname}" ${processname}`
        echo "builtin_sched_execute_funct_plus_postfunct \"\${CMDLINE}\" \"$(esc_dq "${dirname}")\" ${processname} ${opt_array_size} \"\${BUILTIN_ARRAY_TASK_ID}\" > \"$(esc_dq "${builtin_log_filename}")\" 2>&1"
    fi
}

########
builtin_sched_print_script_foot()
{
    :
}

########
write_env_vars_and_funcs_builtin()
{
    local dirname=$1

    # Write general environment variables and functions
    write_env_vars_and_funcs "${dirname}"

    # Write builtin sched environment functions
    declare -f builtin_sched_print_pid_to_file
    declare -f get_task_log_filename_builtin
    declare -f builtin_sched_execute_funct_plus_postfunct
    declare -f seq_execute_builtin
    declare -f get_script_log_filenames_builtin
}

########
builtin_sched_create_script()
{
    # Init variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4
    local fname=`get_script_filename "${dirname}" ${processname}`

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > "${fname}" || return 1

    # Write environment variables
    write_env_vars_and_funcs_builtin "${dirname}" | exclude_readonly_vars >> "${fname}" ; pipe_fail || return 1

    # Print header
    builtin_sched_print_script_header "${fname}" "${dirname}" "${processname}" "${opt_array_size}" >> "${fname}" || return 1

    # Print body
    builtin_sched_print_script_body "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}" >> "${fname}" || return 1

    # Print foot
    builtin_sched_print_script_foot >> "${fname}" || return 1

    # Give execution permission
    chmod u+x "${fname}" || return 1
}

########
wait_until_file_exists()
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
builtin_sched_launch()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local task_idx=$3
    local file=`get_script_filename "${dirname}" ${processname}`

    # Enable execution of specific task id
    if [ ${task_idx} = ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        export BUILTIN_ARRAY_TASK_ID=0
    else
        export BUILTIN_ARRAY_TASK_ID=${task_idx}
    fi

    # Set variable indicating name of file storing PID
    if [ ${task_idx} = ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        local pid_file=`get_processid_filename "${dirname}" ${processname}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    else
        # Get exec dir
        local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

        # Write pid
        local pid_file=`get_array_taskid_filename "${execdir}" ${processname} ${task_idx}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    fi

    # Execute file
    "${file}" &
    local pid=$!

    # Wait for PID file to be created
    local max_num_iters=10000
    wait_until_file_exists "${pid_file}" ${max_num_iters} || return 1

    # Unset variables
    if [ ${task_idx} != ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        unset "${task_varname}"
    fi
    unset BUILTIN_SCHED_PID_FILENAME
}

########
builtin_sched_execute_process()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local task_idx=$4
    local launched_tasks=${BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]}
    local process_spec=${BUILTIN_SCHED_PROCESS_SPEC[${processname}]}

    # Execute process

    ## Obtain process status
    local status=`get_process_status "${dirname}" ${processname}`
    echo "PROCESS: ${processname} (TASK_IDX: ${task_idx}) ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    # Create script
    local opt_array_size=`get_numtasks_for_process "${processname}"`
    if [ "${launched_tasks}" = "" ]; then
        builtin_sched_create_script "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}"
    fi

    # Launch script
    local task_array_list=${task_idx}
    builtin_sched_launch "${dirname}" "${processname}" "${task_idx}" || { echo "Error while launching process!" >&2 ; return 1; }

    # Update register of launched tasks
    if [ "${launched_tasks}" = "" ]; then
        BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]=$task_idx
    else
        BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]="${BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS[${processname}]} $task_idx"
    fi
}

########
builtinsched_extract_process_from_knapsack_name()
{
    local knapsack_name=$1
    local process_idx=`echo "${knapsack_name}" | "${AWK}" -F "_" '{print $1}'`
    echo ${BUILTIN_SCHED_IDX_TO_PROCESSNAME[${process_idx}]}
}

########
builtinsched_extract_task_idx_from_knapsack_name()
{
    local knapsack_name=$1
    local tidx=`echo "${knapsack_name}" | "${AWK}" -F "_" '{print $2}'`
    if [ "${tidx}" = "" ]; then
        echo ${BUILTIN_SCHED_NO_ARRAY_TASK}
    else
        echo ${tidx}
    fi
}

########
builtin_sched_exec_processes_and_update_status()
{
    local cmdline=$1
    local dirname=$2

    local knapsack_name
    for knapsack_name in ${BUILTIN_SCHED_SELECTED_PROCESSES}; do
        # Extract process name and task id
        processname=`builtinsched_extract_process_from_knapsack_name "${knapsack_name}"`
        task_idx=`builtinsched_extract_task_idx_from_knapsack_name "${knapsack_name}"`

        # Execute process
        builtin_sched_execute_process "${cmdline}" "${dirname}" "${processname}" "${task_idx}" || return 1

        # Update process status
        BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED[${processname}]=${INPROGRESS_PROCESS_STATUS}
    done

    # Reset variable
    BUILTIN_SCHED_SELECTED_PROCESSES=""
}

########
builtin_sched_exec_processes()
{
    local cmdline=$1
    local dirname=$2

    # Execute selected processes and update status accordingly
    if [ "${BUILTIN_SCHED_SELECTED_PROCESSES}" != "" ]; then
        local -A BUILTIN_SCHED_CURR_PROCESS_STATUS_UPDATED
        builtin_sched_exec_processes_and_update_status "${cmdline}" "${dirname}"
    fi

    # Update computational resources after execution
    builtin_sched_update_comp_resources "${dirname}"

    # Set updated status as current one
    builtin_sched_fix_updated_process_status
}

########
builtin_sched_clean_process_files()
{
    clean_process_id_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local processid_file=`get_processid_filename "${dirname}" ${processname}`
        "${RM}" -f "${processid_file}"
    }

    clean_process_id_files_array()
    {
        local execdir=$1
        local processname=$2
        local idx=$3

        local array_taskid_file=`get_array_taskid_filename "${execdir}" ${processname} ${idx}`
        if [ -f "${array_taskid_file}" ]; then
            "${RM}" "${array_taskid_file}"
        fi
    }

    clean_process_log_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local builtin_log_filename=`get_process_log_filename "${dirname}" ${processname}`
        "${RM}" -f "${builtin_log_filename}"
    }

    clean_process_log_files_array()
    {
        local dirname=$1
        local processname=$2
        local idx=$3

        local builtin_task_log_filename=`get_task_log_filename "${dirname}" ${processname} ${idx}`
        if [ -f "${builtin_task_log_filename}" ]; then
            "${RM}" "${builtin_task_log_filename}"
        fi
    }

    local dirname=$1
    local processname=$2
    local array_size=${BUILTIN_SCHED_PROCESS_ARRAY_SIZE[${processname}]}

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        clean_process_id_files_non_array "${dirname}" "${processname}"
        clean_process_log_files_non_array "${dirname}" "${processname}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`builtin_sched_get_pending_array_task_indices "${dirname}" ${processname}`
        if [ "${pending_tasks}" != "" ]; then
            # Store string of pending tasks into an array
            local pending_tasks_array
            IFS=',' read -ra pending_tasks_array <<< "${pending_tasks}"

            # Iterate over pending tasks
            local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`
            local idx
            for idx in "${pending_tasks_array[@]}"; do
                clean_process_id_files_array "${execdir}" "${processname}" "${idx}"
                clean_process_log_files_array "${execdir}" "${processname}" "${idx}"
            done
        fi
    fi
}

########
builtin_sched_prepare_files_and_dirs_for_process()
{
    local dirname=$1
    local processname=$2
    local script_filename=`get_script_filename "${dirname}" ${processname}`
    local status=`get_process_status "${dirname}" ${processname}`
    local process_spec=${BUILTIN_SCHED_PROCESS_SPEC[${processname}]}

    if [ "${status}" != "${FINISHED_PROCESS_STATUS}" -a "${status}" != "${INPROGRESS_PROCESS_STATUS}" ]; then
        # Obtain array size
        local array_size=`get_numtasks_for_process "${processname}"`

        # Prepare files and directories for process
        if [ "${status}" = "${TODO_PROCESS_STATUS}" ]; then
            create_exec_dir_for_process "${dirname}" "${processname}" || { echo "Error when creating exec directory for process" >&2 ; return 1; }
            create_shdirs_owned_by_process "${processname}" || { echo "Error when creating shared directories determined by script option definition" >&2 ; return 1; }
        else
            builtin_sched_clean_process_files "${dirname}" ${processname} || { echo "Error when cleaning log files for process" >&2 ; return 1; }
        fi
        prepare_fifos_owned_by_process ${processname}
        update_process_completion_signal "${dirname}" ${processname} ${status} || { echo "Error when updating process completion signal for process" >&2 ; return 1; }

        # Create output directory
        create_outdir_for_process "${dirname}" ${processname} || { echo "Error when creating output directory for process" >&2 ; return 1; }
    fi
}

########
builtin_sched_prepare_files_and_dirs_for_processes()
{
    local dirname=$1

    local processname
    for processname in "${!BUILTIN_SCHED_CURR_PROCESS_STATUS[@]}"; do
        builtin_sched_prepare_files_and_dirs_for_process "${dirname}" $processname
    done
}

########
builtin_sched_sleep()
{
    # Sleep a certain number of seconds depending on the number of
    # program processes
    local num_processes=${#BUILTIN_SCHED_PROCESSNAME_TO_IDX[@]}

    if [ ${num_processes} -le ${BUILTIN_SCHED_NPROCESSES_SLEEP_THRESHOLD} ]; then
        "${SLEEP}" ${BUILTIN_SCHED_SLEEP_TIME_SHORT}
    else
        "${SLEEP}" ${BUILTIN_SCHED_SLEEP_TIME_LONG}
    fi
}

########
builtin_sched_execute_program_processes()
{
    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3
    local iterno=1

    echo "* Configuring scheduler..." >&2
    if [ ${builtinsched_cpus_given} -eq 1 ]; then
        BUILTIN_SCHED_CPUS=${builtinsched_cpus}
    fi

    if [ ${builtinsched_mem_given} -eq 1 ]; then
        BUILTIN_SCHED_MEM=${builtinsched_mem}
    fi
    echo "- Available CPUS: ${BUILTIN_SCHED_CPUS}" >&2
    echo "- Available memory: ${BUILTIN_SCHED_MEM}" >&2
    echo "" >&2

    echo "* Initializing data structures..." >&2

    # Initialize process status
    builtin_sched_init_process_info "${cmdline}" "${dirname}" "${procspec_file}" || return 1

    # Initialize current process status
    builtin_sched_init_curr_comp_resources || return 1

    # Prepare files and directories for processes
    builtin_sched_prepare_files_and_dirs_for_processes "${dirname}"

    echo "" >&2

    echo "* Executing program processes..." >&2

    # Execute scheduling loop
    local end=0
    while [ ${end} -eq 0 ]; do
        if [ ${builtinsched_debug} -eq 1 ]; then
            echo "[BUILTIN_SCHED] * Iteration ${iterno}" 2>&1
        fi

        # Select processes that should be executed
        if builtin_sched_select_processes_to_be_exec "${dirname}"; then
            # Execute processes
            builtin_sched_exec_processes "${cmdline}" "${dirname}"

            # Wait before starting a new loop
            builtin_sched_sleep
        else
            # There are no processes to be executed

            if builtin_sched_inprogress_processes_pending; then
                # Wait for in-progress processes to finish
                builtin_sched_sleep
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
get_script_log_filenames_builtin()
{
    local exec_dirname=$1

    find "${exec_dirname}" -name "*.${SCHED_LOG_FEXT}" -exec echo {} \;
}
