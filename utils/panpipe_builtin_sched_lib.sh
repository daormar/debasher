# PanPipe package
# Copyright (C) 2019,2020 Daniel Ortiz-Mart\'inez
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
BUILTIN_SCHED_FAILED_STEP_STATUS="FAILED"
BUILTIN_SCHED_NO_ARRAY_TASK="NO_ARRAY_TASK"
BUILTIN_SCHED_SLEEP_TIME_LONG=5
BUILTIN_SCHED_SLEEP_TIME_SHORT=1
BUILTIN_SCHED_NSTEPS_SLEEP_THRESHOLD=10
BUILTIN_SCHED_KNAPSACK_SPEC_FNAME=.knapsack_spec.txt
BUILTIN_SCHED_KNAPSACK_SOL_FNAME=.knapsack_sol.txt

# ARRAY TASK STATUSES
BUILTIN_SCHED_FINISHED_TASK_STATUS="FINISHED"
BUILTIN_SCHED_INPROGRESS_TASK_STATUS="IN-PROGRESS"
BUILTIN_SCHED_FAILED_TASK_STATUS="FAILED"
BUILTIN_SCHED_TODO_TASK_STATUS="TO-DO"

####################
# GLOBAL VARIABLES #
####################

# Declare built-in scheduler-related variables
declare -A BUILTIN_SCHED_STEPNAME_TO_IDX
declare -A BUILTIN_SCHED_IDX_TO_STEPNAME
declare -A BUILTIN_SCHED_STEP_SCRIPT_FILENAME
declare -A BUILTIN_SCHED_STEP_SPEC
declare -A BUILTIN_SCHED_STEP_DEPS
declare -A BUILTIN_SCHED_STEP_ARRAY_SIZE
declare -A BUILTIN_SCHED_STEP_THROTTLE
declare -A BUILTIN_SCHED_STEP_CPUS
declare -A BUILTIN_SCHED_STEP_ALLOC_CPUS
declare -A BUILTIN_SCHED_STEP_MEM
declare -A BUILTIN_SCHED_STEP_ALLOC_MEM
declare -A BUILTIN_SCHED_STEP_LAUNCHED_TASKS
declare -A BUILTIN_SCHED_CURR_STEP_STATUS
declare BUILTIN_SCHED_SELECTED_STEPS
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
builtin_sched_update_stepname_to_idx_info()
{
    local stepname=$1
    if [ ${BUILTIN_SCHED_STEPNAME_TO_IDX[${stepname}]} = ""]; then
        local len=${#BUILTIN_SCHED_STEPNAME_TO_IDX[@]}
        BUILTIN_SCHED_STEPNAME_TO_IDX[${stepname}]=${len}
        BUILTIN_SCHED_IDX_TO_STEPNAME[${len}]=${stepname}
    fi
}

########
builtin_sched_init_step_info()
{
    local cmdline=$1
    local dirname=$2
    local pfile=$3

    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            local script_filename=`get_script_filename "${dirname}" ${stepname}`
            local status=`get_step_status "${dirname}" ${stepname}`
            local stepdeps=`extract_stepdeps_from_stepspec "$stepspec"`
            local spec_throttle=`extract_attr_from_stepspec "$stepspec" "throttle"`
            local sched_throttle=`get_scheduler_throttle ${spec_throttle}`
            local array_size=`get_task_array_size_for_step "${cmdline}" "${stepspec}"`

            # Get cpus info
            local cpus=`extract_cpus_from_stepspec "$stepspec"`
            str_is_natural_number ${cpus} || { echo "Error: number of cpus ($cpus) for $stepname should be a natural number" >&2; return 1; }

            # Get mem info (NOTE: if multiple attempts specified, keep
            # memory specification of the first one)
            local mem=`extract_mem_from_stepspec "$stepspec"`
            local attempt_no=1
            mem=`get_mem_attempt_value ${mem} ${attempt_no}`
            mem=`convert_mem_value_to_mb ${mem}` || { echo "Invalid memory specification for step ${stepname}" >&2; return 1; }
            str_is_natural_number ${mem} || { echo "Error: amount of memory ($mem) for $stepname should be a natural number" >&2; return 1; }

            # Obtain full throttle cpus value
            local full_throttle_cpus=${cpus}
            if [ $array_size -gt 1 ]; then
                full_throttle_cpus=$((cpus * sched_throttle))
            fi
            # Check full_throttle_cpus value
            builtin_sched_cpus_within_limit ${full_throttle_cpus} || { echo "Error: number of cpus for step $stepname exceeds limit (cpus: ${cpus}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Obtain full throttle mem value
            local full_throttle_mem=${mem}
            if [ $array_size -gt 1 ]; then
                full_throttle_mem=$((mem * sched_throttle))
            fi
            # Check mem value
            builtin_sched_mem_within_limit ${full_throttle_mem} || { echo "Error: amount of memory for step $stepname exceeds limit (mem: ${mem}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Register step information
            builtin_sched_update_stepname_to_idx_info ${stepname}
            BUILTIN_SCHED_STEP_SCRIPT_FILENAME[${stepname}]=${script_filename}
            BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]=${status}   
            BUILTIN_SCHED_STEP_SPEC[${stepname}]="${stepspec}"
            BUILTIN_SCHED_STEP_DEPS[${stepname}]=${stepdeps}
            BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]=${array_size}
            BUILTIN_SCHED_STEP_THROTTLE[${stepname}]=${sched_throttle}
            BUILTIN_SCHED_STEP_CPUS[${stepname}]=${cpus}
            BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]=0
            BUILTIN_SCHED_STEP_MEM[${stepname}]=${mem}
            BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=0
        fi
    done < "${pfile}"
}

########
builtin_sched_release_mem()
{
    local stepname=$1
    
    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM - ${BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]}))
    BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=0
}

########
builtin_sched_release_cpus()
{
    local stepname=$1
    
    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS - ${BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]}))
    BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]=0
}

########
builtin_sched_get_step_mem()
{
    local stepname=$1

    echo ${BUILTIN_SCHED_STEP_MEM[${stepname}]}
}

########
builtin_sched_get_step_mem_given_num_tasks()
{
    local stepname=$1
    local ntasks=$2

    if [ ${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]} -eq 1 ]; then
        echo ${BUILTIN_SCHED_STEP_MEM[${stepname}]}
    else
        echo $((${BUILTIN_SCHED_STEP_MEM[${stepname}]} * ntasks))
    fi
}

########
builtin_sched_reserve_mem()
{
    local stepname=$1
    local step_mem=`builtin_sched_get_step_mem ${stepname}`
    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM + step_mem))
    BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=${step_mem}
}

########
builtin_sched_get_step_cpus()
{
    local stepname=$1

    echo ${BUILTIN_SCHED_STEP_CPUS[${stepname}]}
}

########
builtin_sched_get_step_cpus_given_num_tasks()
{
    local stepname=$1
    local ntasks=$2

    if [ ${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]} -eq 1 ]; then
        echo ${BUILTIN_SCHED_STEP_CPUS[${stepname}]}
    else
        echo $((${BUILTIN_SCHED_STEP_CPUS[${stepname}]} * ntasks))
    fi
}

########
builtin_sched_reserve_cpus()
{
    local stepname=$1
    local step_cpus=`builtin_sched_get_step_cpus ${stepname}`
    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS + step_cpus))
    BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]=${step_cpus}
}

########
builtin_sched_get_array_task_status()
{
    local dirname=$1
    local stepname=$2
    local taskidx=$3
    local stepdirname=`get_step_outdir "${dirname}" ${stepname}`
    local array_taskid_file=`get_array_taskid_filename "${dirname}" ${stepname} ${taskidx}`
    
    if [ ! -f ${array_taskid_file} ]; then
        # Task is not started
        echo ${BUILTIN_SCHED_TODO_TASK_STATUS}
    else
        # Task was started
        if array_task_is_finished "${dirname}" ${stepname} ${taskidx}; then
            echo ${BUILTIN_SCHED_FINISHED_TASK_STATUS}
        else
            # Task is not finished
            local id=`cat "${array_taskid_file}"`
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
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    for taskidx in `seq ${array_size}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $stepname $taskidx`
        if [ ${task_status} = ${BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$taskidx
            else
                result="$result $taskidx"
            fi
        fi
    done

    echo $result
}

########
builtin_sched_get_finished_array_task_indices()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    for taskidx in `seq ${array_size}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $stepname $taskidx`
        if [ ${task_status} = ${BUILTIN_SCHED_FINISHED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$taskidx
            else
                result="$result $taskidx"
            fi
        fi
    done

    echo $result
}

########
builtin_sched_get_inprogress_array_task_indices()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    for taskidx in `seq ${array_size}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $stepname $taskidx`
        if [ ${task_status} = ${INPROGRESS_STEP_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$taskidx
            else
                result="$result $taskidx"
            fi
        fi
    done

    echo $result
}

########
builtin_sched_get_todo_array_task_indices()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    local taskidx
    for taskidx in `seq ${array_size}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $stepname $taskidx`
        if [ ${task_status} = ${BUILTIN_SCHED_TODO_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$taskidx
            else
                result="$result $taskidx"
            fi
        fi
    done

    echo $result
}

########
builtin_sched_get_pending_array_task_indices()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    local taskidx
    for taskidx in `seq ${array_size}`; do
        local task_status=`builtin_sched_get_array_task_status "${dirname}" $stepname $taskidx`
        if [ ${task_status} = ${BUILTIN_SCHED_TODO_TASK_STATUS} -o ${task_status} = ${BUILTIN_SCHED_FAILED_TASK_STATUS} ]; then
            if [ "${result}" = "" ]; then
                result=$taskidx
            else
                result="$result $taskidx"
            fi
        fi
    done

    echo $result
}

########
builtin_sched_revise_array_mem()
{
    local dirname=$1
    local stepname=$2

    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" ${stepname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`    
    local step_revised_mem=`builtin_sched_get_step_mem_given_num_tasks ${stepname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_MEM=$((BUILTIN_SCHED_ALLOC_MEM - ${BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]} + step_revised_mem))
    BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=${step_revised_mem}
}

########
builtin_sched_revise_array_cpus()
{
    local dirname=$1
    local stepname=$2

    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" ${stepname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`    
    local step_revised_cpus=`builtin_sched_get_step_cpus_given_num_tasks ${stepname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_CPUS=$((BUILTIN_SCHED_ALLOC_CPUS - ${BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]} + step_revised_cpus))
    BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]=${step_revised_cpus}
}

########
builtin_sched_init_curr_comp_resources()
{
    # Iterate over defined steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        if [ ${status} = ${INPROGRESS_STEP_STATUS} ]; then
            builtin_sched_reserve_mem $stepname
            builtin_sched_reserve_cpus $stepname
        fi
    done
}

########
builtin_sched_get_updated_step_status()
{
    local dirname=$1

    # Iterate over defined steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_STEP_STATUS[$stepname]}
        if [ ${status} != ${BUILTIN_SCHED_FAILED_STEP_STATUS} -a ${status} != ${FINISHED_STEP_STATUS} ]; then
            local updated_status=`get_step_status "${dirname}" ${stepname}`
            BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED[${stepname}]=${updated_status}
        fi
    done
}

########
builtin_sched_update_comp_resources()
{
    local dirname=$1
    
    # Iterate over steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        prev_status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        updated_status=${BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED[${stepname}]}
        if [ "${updated_status}" != "" ]; then
            # Store array size in variable
            step_array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
            
            # Check if resources should be released
            if [ ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${INPROGRESS_STEP_STATUS} ]; then
                builtin_sched_release_mem $stepname
                builtin_sched_release_cpus $stepname
            fi

            # Check if resources should be reserved
            if [ ${prev_status} != ${INPROGRESS_STEP_STATUS} -a ${updated_status} = ${INPROGRESS_STEP_STATUS} ]; then
                if [ ${step_array_size} -eq 1 ]; then
                    builtin_sched_reserve_mem $stepname
                    builtin_sched_reserve_cpus $stepname
                else
                    # step is an array
                    builtin_sched_revise_array_mem "${dirname}" $stepname
                    builtin_sched_revise_array_cpus "${dirname}" $stepname
                fi
            fi

            # Check if resources of job array should be revised
            if [ ${step_array_size} -gt 1 -a ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} = ${INPROGRESS_STEP_STATUS} ]; then
                builtin_sched_revise_array_mem "${dirname}" $stepname
                builtin_sched_revise_array_cpus "${dirname}" $stepname
            fi
        fi
    done
}
    
########
builtin_sched_fix_updated_step_status()
{
    # Copy updated status into current status
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        prev_status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        updated_status=${BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED[${stepname}]}
        if [ "${updated_status}" != "" ]; then
            if [ ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${UNFINISHED_BUT_RUNNABLE_STEP_STATUS} -a ${updated_status} != ${FINISHED_STEP_STATUS} ]; then
                # Status will be set to failed if previous status was
                # in-progress and new status is unfinished
                BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]=${BUILTIN_SCHED_FAILED_STEP_STATUS}
            else
                BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]=${BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED[${stepname}]}
            fi
        fi
    done
}

########
builtin_sched_get_available_cpus()
{
    if [ ${BUILTIN_SCHED_CPUS} -eq 0 ]; then
        echo 0
    else
        echo $((BUILTIN_SCHED_CPUS - BUILTIN_SCHED_ALLOC_CPUS))
    fi
}

########
builtin_sched_get_available_mem()
{
    if [ ${BUILTIN_SCHED_MEM} -eq 0 ]; then
        echo 0
    else
        echo $((BUILTIN_SCHED_MEM - BUILTIN_SCHED_ALLOC_MEM))
    fi
}

########
builtin_sched_check_comp_res()
{
    local stepname=$1

    if [ ${BUILTIN_SCHED_CPUS} -gt 0 ]; then
        local available_cpus=`builtin_sched_get_available_cpus`
        step_cpus=`builtin_sched_get_step_cpus ${stepname}`
        if [ ${step_cpus} -gt ${available_cpus} ]; then
            return 1
        fi
    fi

    if [ ${BUILTIN_SCHED_MEM} -gt 0 ]; then
        local available_mem=`builtin_sched_get_available_mem`
        step_mem=`builtin_sched_get_step_mem ${stepname}`
        if [ ${step_mem} -gt ${available_mem} ]; then
            return 1
        fi
    fi

    return 0
}

########
builtin_sched_check_step_deps()
{
    local stepname=$1
    local stepdeps=${BUILTIN_SCHED_STEP_DEPS[${stepname}]}

    # Iterate over dependencies
    local separator=`get_stepdeps_separator ${stepdeps}`
    if [ "${separator}" = "" ]; then
        local stepdeps_blanks=${stepdeps}
    else
        local stepdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${stepdeps}`
    fi
    local dep
    for dep in ${stepdeps_blanks}; do
        # Extract information from dependency
        local deptype=`get_deptype_part_in_dep ${dep}`
        local depsname=`get_stepname_part_in_dep ${dep}`

        # Process dependency
        depstatus=${BUILTIN_SCHED_CURR_STEP_STATUS[${depsname}]}
            
        # Process exit code
        local dep_ok=1
        case ${deptype} in
            ${AFTER_STEPDEP_TYPE})
                if [ ${depstatus} = ${TODO_STEP_STATUS} -o  ${depstatus} = ${UNFINISHED_STEP_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTEROK_STEPDEP_TYPE})
                if [ ${depstatus} != ${FINISHED_STEP_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTERNOTOK_STEPDEP_TYPE})
                if [ ${depstatus} != ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
                    dep_ok=0
                fi
                ;;
            ${AFTERANY_STEPDEP_TYPE})
                if [ ${depstatus} = ${FINISHED_STEP_STATUS} -o ${depstatus} = ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
                    dep_ok=0
                fi 
                ;;
            ${AFTERCORR_STEPDEP_TYPE})
                # NOTE: AFTERCORR_STEPDEP_TYPE dependency type currently
                # treated in the same way as AFTEROK_STEPDEP_TYPE
                # dependency
                if [ ${depstatus} != ${FINISHED_STEP_STATUS} ]; then
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
builtin_sched_step_can_be_executed()
{
    local stepname=$1

    # Check there are enough computational resources
    builtin_sched_check_comp_res $stepname || return 1
    # Check step dependencies are satisfied
    builtin_sched_check_step_deps $stepname || return 1

    return 0
}

########
builtin_sched_get_max_num_tasks()
{
    local stepname=$1
    local throttle=${BUILTIN_SCHED_STEP_THROTTLE[${stepname}]}
    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices "${dirname}" $stepname`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`
    local result=$((throttle - num_inprogress_tasks))
    echo ${result}
}

########
builtin_sched_process_executable_non_array_step()
{
    local stepname=$1
    local status=$2

    if [ ${status} != ${INPROGRESS_STEP_STATUS} -a ${status} != ${FINISHED_STEP_STATUS} -a ${status} != ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
        if builtin_sched_step_can_be_executed ${stepname}; then
            BUILTIN_SCHED_EXECUTABLE_STEPS[${stepname}]=${BUILTIN_SCHED_NO_ARRAY_TASK}
        fi
    fi
}

########
builtin_sched_process_executable_array_step()
{
    local stepname=$1
    local status=$2
    
    if [ ${status} != ${FINISHED_STEP_STATUS} -a ${status} != ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
        if builtin_sched_step_can_be_executed ${stepname}; then
            max_task_num=`builtin_sched_get_max_num_tasks ${stepname}`
            if [ ${max_task_num} -gt 0 ]; then
                todo_task_indices=`builtin_sched_get_todo_array_task_indices "${dirname}" ${stepname}`
                todo_task_indices_truncated=`get_first_n_fields_of_str "${todo_task_indices}" ${max_task_num}`
                if [ "${todo_task_indices_truncated}" != "" ]; then
                    BUILTIN_SCHED_EXECUTABLE_STEPS[${stepname}]=${todo_task_indices_truncated}
                fi
            fi
        fi
    fi    
}

########
builtin_sched_get_executable_steps()
{
    local dirname=$1
    
    # Iterate over steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        local status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
        if [ ${array_size} -eq 1 ]; then
            # step is not an array
            builtin_sched_process_executable_non_array_step ${stepname} ${status}
        else
            # step is an array
            builtin_sched_process_executable_array_step ${stepname} ${status}
        fi
    done
}

########
builtin_sched_get_knapsack_cpus_for_step()
{
    local stepname=$1
    
    if [ ${BUILTIN_SCHED_CPUS} -gt 0 ]; then
        echo ${BUILTIN_SCHED_STEP_CPUS[${stepname}]}
    else
        echo 0
    fi
}

########
builtin_sched_get_knapsack_mem_for_step()
{
    local stepname=$1
    
    if [ ${BUILTIN_SCHED_MEM} -gt 0 ]; then
        echo ${BUILTIN_SCHED_STEP_MEM[${stepname}]}
    else
        echo 0
    fi
}

########
builtin_sched_get_knapsack_name()
{
    local stepname=$1
    local taskidx=$2

    if [ "${taskidx}" = "" ]; then
        echo "${BUILTIN_SCHED_STEPNAME_TO_IDX[${stepname}]}"
    else
        echo "${BUILTIN_SCHED_STEPNAME_TO_IDX[${stepname}]}_${taskidx}"
    fi
}

########
builtin_sched_print_knapsack_spec()
{
    local stepvalue=1
    
    # Process each executable step
    local stepname
    for stepname in "${!BUILTIN_SCHED_EXECUTABLE_STEPS[@]}"; do
        # Obtain array size
        local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}

        # Determine cpu requirements
        cpus=`builtin_sched_get_knapsack_cpus_for_step ${stepname}`
        
        # Determine memory requirements
        mem=`builtin_sched_get_knapsack_mem_for_step ${stepname}`

        if [ ${array_size} -eq 1 ]; then
            local knapsack_name=`builtin_sched_get_knapsack_name ${stepname}`
            echo "${knapsack_name} ${stepvalue} ${cpus} ${mem}"
        else
            for id in ${BUILTIN_SCHED_EXECUTABLE_STEPS[${stepname}]}; do
                local knapsack_name=`builtin_sched_get_knapsack_name ${stepname} ${id}`
                echo "${knapsack_name} ${stepvalue} ${cpus} ${mem}"
            done
        fi
    done
}

########
builtin_sched_print_knapsack_sol()
{
    local available_cpus=`builtin_sched_get_available_cpus`
    local available_mem=`builtin_sched_get_available_mem`
    local time_limit=1
    "${panpipe_bindir}"/solve_knapsack_ga -s "${specfile}" -c ${available_cpus},${available_mem} -t ${time_limit}
}

########
builtin_sched_solve_knapsack()
{
    local dirname=$1

    # Create file with item and weight specification
    specfile="${dirname}/${BUILTIN_SCHED_KNAPSACK_SPEC_FNAME}"
    rm -f "${specfile}"
    builtin_sched_print_knapsack_spec > "${specfile}"
    
    # Solve knapsack problem
    local knapsack_sol="${dirname}/${BUILTIN_SCHED_KNAPSACK_SOL_FNAME}"
    builtin_sched_print_knapsack_sol > "${knapsack_sol}"

    # Store solution in output variable
    BUILTIN_SCHED_SELECTED_STEPS=`"${AWK}" -F ": " '{if($1=="Packed items") print $2}' "${knapsack_sol}"`
}

########
builtin_sched_count_executable_steps()
{
    echo ${#BUILTIN_SCHED_EXECUTABLE_STEPS[@]}
}

########
builtin_sched_inprogress_steps_pending()
{
    # Iterate over steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        if [ ${status} = ${INPROGRESS_STEP_STATUS} ]; then
            return 0
        fi
    done

    return 1
}

########
builtin_sched_get_debug_step_status_info()
{
    local step_status
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        step_status="${step_status} ${stepname} -> ${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]};"
    done
    echo $step_status
}

########
builtin_sched_get_debug_exec_steps_info()
{
    local exec_steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_EXECUTABLE_STEPS[@]}"; do
        exec_steps="${exec_steps} ${stepname} -> ${BUILTIN_SCHED_EXECUTABLE_STEPS[${stepname}]};"
    done
    echo $exec_steps
}
########
builtin_sched_get_debug_sel_steps_info()
{
    local sel_steps
    local knapsack_name
    for knapsack_name in ${BUILTIN_SCHED_SELECTED_STEPS}; do
        sname=`builtinsched_extract_step_from_knapsack_name ${knapsack_name}`
        tidx=`builtinsched_extract_taskidx_from_knapsack_name ${knapsack_name}`
        sel_steps="${sel_steps} ${knapsack_name} -> ${sname},${tidx};"
    done
    echo $sel_steps
}

########
builtin_sched_select_steps_to_be_exec()
{
    local dirname=$1

    # Obtain updated status for steps
    local -A BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED
    builtin_sched_get_updated_step_status "${dirname}"

    # Update computational resources depending on changes
    builtin_sched_update_comp_resources "${dirname}"

    # Set updated status as current one
    builtin_sched_fix_updated_step_status

    # Obtain set of steps that can be executed
    local -A BUILTIN_SCHED_EXECUTABLE_STEPS
    builtin_sched_get_executable_steps "${dirname}"

    if [ ${builtinsched_debug} -eq 1 ]; then
        local step_status=`builtin_sched_get_debug_step_status_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_CURR_STEP_STATUS: ${step_status}"
        echo "[BUILTIN_SCHED] - COMPUTATIONAL RESOURCES: total cpus= ${BUILTIN_SCHED_CPUS}, allocated cpus= ${BUILTIN_SCHED_ALLOC_CPUS}; total mem= ${BUILTIN_SCHED_MEM}, allocated mem= ${BUILTIN_SCHED_ALLOC_MEM}"
        local exec_steps=`builtin_sched_get_debug_exec_steps_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_EXECUTABLE_STEPS: ${exec_steps}" 2>&1
    fi
        
    # If there are executable steps, select which ones will be executed
    num_exec_steps=${#BUILTIN_SCHED_EXECUTABLE_STEPS[@]}
    if [ ${num_exec_steps} -gt 0 ]; then
        builtin_sched_solve_knapsack "${dirname}"

        if [ ${builtinsched_debug} -eq 1 ]; then
            local sel_steps=`builtin_sched_get_debug_sel_steps_info`
            echo "[BUILTIN_SCHED] - BUILTIN_SCHED_SELECTED_STEPS: ${sel_steps}" 2>&1
        fi

        return 0
    else
        # No executable steps were found
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
    local stepname=$3
    local num_scripts=$4

    echo "PANPIPE_SCRIPT_FILENAME=\"${fname}\""
    echo "PANPIPE_DIR_NAME=\"${dirname}\""
    echo "PANPIPE_STEP_NAME=${stepname}"
    echo "PANPIPE_NUM_SCRIPTS=${num_scripts}"
    echo "builtin_sched_print_pid_to_file"
}

########
builtin_sched_get_task_array_task_varname()
{
    local arrayname=$1
    local taskidx=$2
    
    echo "BUILTIN_SCHED_TASK_ARRAY_${arrayname}_${taskidx}"
}

########
builtin_sched_execute_funct_plus_postfunct()
{
    local num_scripts=$1
    local dirname=$2
    local stepname=$3
    local taskidx=$4
    local reset_funct=$5
    local funct=$6
    local post_funct=$7
    local script_opts=$8

    display_begin_step_message

    # Reset output directory
    if [ "${reset_funct}" = ${FUNCT_NOT_FOUND} ]; then
        if [ ${num_scripts} -eq 1 ]; then
            default_reset_outdir_for_step "${dirname}" ${stepname}
        else
            default_reset_outdir_for_step_array "${dirname}" ${stepname} ${taskidx}
        fi
    else
        ${reset_funct} "${script_opts}"
    fi

    # Execute step function
    $funct "${script_opts}"
    local funct_exit_code=$?
    if [ ${funct_exit_code} -ne 0 ]; then
        echo "Error: execution of ${funct} failed with exit code ${funct_exit_code}" >&2
    else
        echo "Function ${funct} successfully executed" >&2
    fi

    # Execute step post-function
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        ${post_funct} "${script_opts}" || { echo "Error: execution of ${post_funct} failed with exit code $?" >&2 ; return 1; }
    fi

    # Treat errors
    if [ ${funct_exit_code} -ne 0 ]; then
        return 1;
    fi

    # Signal step completion
    signal_step_completion "${dirname}" ${stepname} ${taskidx} ${num_scripts} || return 1

    display_end_step_message
}

########
builtin_sched_print_script_body()
{
    # Initialize variables
    local num_scripts=$1
    local dirname=$2
    local stepname=$3
    local taskidx=$4
    local reset_funct=$5
    local funct=$6
    local post_funct=$7
    local script_opts=$8

    # Write treatment for task id
    if [ ${num_scripts} -gt 1 ]; then
        local varname=`builtin_sched_get_task_array_task_varname ${stepname} ${taskidx}`
        echo "if [ \"\${${varname}}\" = 1 ]; then"
    fi

    # Write function to be executed
    if [ ${num_scripts} -gt 1 ]; then
        local builtin_task_log_filename=`get_task_log_filename_builtin "${dirname}" ${stepname} ${taskidx}`
        echo "builtin_sched_execute_funct_plus_postfunct ${num_scripts} \"$(esc_dq "${dirname}")\" ${stepname} ${taskidx} ${reset_funct} ${funct} ${post_funct} \"$(esc_dq "${script_opts}")\" > \"$(esc_dq "${builtin_task_log_filename}")\" 2>&1"
    else
        local builtin_log_filename=`get_step_log_filename_builtin "${dirname}" ${stepname}`
        echo "builtin_sched_execute_funct_plus_postfunct ${num_scripts} \"$(esc_dq "${dirname}")\" ${stepname} ${taskidx} ${reset_funct} ${funct} ${post_funct} \"$(esc_dq "${script_opts}")\" > \"$(esc_dq "${builtin_log_filename}")\" 2>&1"
    fi
    
    # Close if statement
    if [ ${num_scripts} -gt 1 ]; then
        echo "fi" 
    fi
}

########
builtin_sched_print_script_foot()
{
    :
}

########
builtin_sched_create_script()
{
    # Init variables
    local dirname=$1
    local stepname=$2
    local fname=`get_script_filename "${dirname}" ${stepname}`
    local reset_funct=`get_name_of_step_function_reset ${stepname}`
    local funct=`get_name_of_step_function ${stepname}`
    local post_funct=`get_name_of_step_function_post ${stepname}`
    local opts_array_name=$3[@]
    local opts_array=("${!opts_array_name}")
    local num_scripts=${#opts_array[@]}
    
    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > "${fname}" || return 1
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_other_vars >> "${fname}" || return 1

    # Print header
    builtin_sched_print_script_header "${fname}" "${dirname}" ${stepname} ${num_scripts} >> "${fname}" || return 1
    
    # Iterate over options array
    local lineno=1
    local script_opts
    for script_opts in "${opts_array[@]}"; do

        builtin_sched_print_script_body ${num_scripts} "${dirname}" ${stepname} ${lineno} ${reset_funct} ${funct} ${post_funct} "${script_opts}" >> "${fname}" || return 1

        lineno=$((lineno + 1))

    done

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
    local stepname=$2
    local taskidx=$3
    local file=`get_script_filename "${dirname}" ${stepname}`

    # Enable execution of specific task id
    if [ ${taskidx} != ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        local task_varname=`builtin_sched_get_task_array_task_varname ${stepname} ${taskidx}`
        export ${task_varname}=1
    fi

    # Set variable indicating name of file storing PID
    if [ ${taskidx} = ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        local pid_file=`get_stepid_filename "${dirname}" ${stepname}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    else
        local pid_file=`get_array_taskid_filename "${dirname}" ${stepname} ${taskidx}`
        export BUILTIN_SCHED_PID_FILENAME="${pid_file}"
    fi

    # Execute file
    "${file}" &
    local pid=$!

    # Wait for PID file to be created
    local max_num_iters=10000
    wait_until_file_exists "${pid_file}" ${max_num_iters} || return 1
    
    # Unset variables
    if [ ${taskidx} != ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        unset ${task_varname}
    fi
    unset BUILTIN_SCHED_PID_FILENAME
}

########
builtin_sched_execute_step()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local stepname=$3
    local taskidx=$4
    local launched_tasks=${BUILTIN_SCHED_STEP_LAUNCHED_TASKS[${stepname}]}
    local stepspec=${BUILTIN_SCHED_STEP_SPEC[${stepname}]}
    
    # Execute step

    ## Obtain step status
    local status=`get_step_status "${dirname}" ${stepname}`
    echo "STEP: ${stepname} (TASKIDX: ${taskidx}) ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2
    
    # Create script
    define_opts_for_script "${cmdline}" "${stepspec}" || return 1
    local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
    local array_size=${#script_opts_array[@]}
    if [ "${launched_tasks}" = "" ]; then
        builtin_sched_create_script "${dirname}" ${stepname} "script_opts_array"
    fi
    
    # Archive script
    if [ "${launched_tasks}" = "" ]; then
        archive_script "${dirname}" ${stepname}
    fi

    # Launch script
    local task_array_list=${taskidx}
    builtin_sched_launch "${dirname}" ${stepname} "${taskidx}" || { echo "Error while launching step!" >&2 ; return 1; }
        
    # Update register of launched tasks
    if [ "${launched_tasks}" = "" ]; then
        BUILTIN_SCHED_STEP_LAUNCHED_TASKS[${stepname}]=$taskidx
    else
        BUILTIN_SCHED_STEP_LAUNCHED_TASKS[${stepname}]="${BUILTIN_SCHED_STEP_LAUNCHED_TASKS[${stepname}]} $taskidx"
    fi
}

########
builtinsched_extract_step_from_knapsack_name()
{
    local knapsack_name=$1
    local step_idx=`echo "${knapsack_name}" | "${AWK}" -F "_" '{print $1}'`
    echo ${BUILTIN_SCHED_IDX_TO_STEPNAME[${step_idx}]}
}

########
builtinsched_extract_taskidx_from_knapsack_name()
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
builtin_sched_exec_steps_and_update_status()
{
    local cmdline=$1
    local dirname=$2

    local knapsack_name
    for knapsack_name in ${BUILTIN_SCHED_SELECTED_STEPS}; do
        # Extract step name and task id
        stepname=`builtinsched_extract_step_from_knapsack_name "${knapsack_name}"`
        taskidx=`builtinsched_extract_taskidx_from_knapsack_name "${knapsack_name}"`
        
        # Execute step
        builtin_sched_execute_step "${cmdline}" "${dirname}" ${stepname} ${taskidx} || return 1
        
        # Update step status
        BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED[${stepname}]=${INPROGRESS_STEP_STATUS}
    done
    
    # Reset variable
    BUILTIN_SCHED_SELECTED_STEPS=""
}
    
########
builtin_sched_exec_steps()
{
    local cmdline=$1
    local dirname=$2

    # Execute selected steps and update status accordingly
    if [ "${BUILTIN_SCHED_SELECTED_STEPS}" != "" ]; then
        local -A BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED
        builtin_sched_exec_steps_and_update_status "${cmdline}" "${dirname}"
    fi
    
    # Update computational resources after execution
    builtin_sched_update_comp_resources "${dirname}"

    # Set updated status as current one
    builtin_sched_fix_updated_step_status
}

########
builtin_sched_clean_step_log_files()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local builtin_log_filename=`get_step_log_filename_builtin "${dirname}" ${stepname}`
        rm -f "${builtin_log_filename}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`builtin_sched_get_pending_array_task_indices "${dirname}" ${stepname}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local builtin_task_log_filename=`get_task_log_filename_builtin "${dirname}" ${stepname} ${idx}`
                rm -f "${builtin_task_log_filename}"
            done
        fi
    fi
}

########
builtin_sched_clean_step_id_files()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename "${dirname}" ${stepname}`
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local stepid_file=`get_stepid_filename "${dirname}" ${stepname}`
        rm -f "${stepid_file}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`builtin_sched_get_pending_array_task_indices "${dirname}" ${stepname}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local array_taskid_file=`get_array_taskid_filename "${dirname}" ${stepname} ${idx}`
                rm -f "${array_taskid_file}"
            done
        fi
    fi
}

########
builtin_sched_prepare_files_and_dirs_for_step()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename "${dirname}" ${stepname}`
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local status=`get_step_status "${dirname}" ${stepname}`

    if [ "${status}" != "${FINISHED_STEP_STATUS}" -a "${status}" != "${INPROGRESS_STEP_STATUS}" ]; then
        # Prepare files for step
        update_step_completion_signal "${dirname}" ${stepname} ${status} || { echo "Error when updating step completion signal for step" >&2 ; return 1; }
        builtin_sched_clean_step_log_files "${dirname}" ${stepname} || { echo "Error when cleaning log files for step" >&2 ; return 1; }
        builtin_sched_clean_step_id_files "${dirname}" ${stepname} || { echo "Error when cleaning id files for step" >&2 ; return 1; }
        prepare_fifos_owned_by_step ${stepname}

        # Create output directory
        create_outdir_for_step "${dirname}" ${stepname} || { echo "Error when creating output directory for step" >&2 ; return 1; }
    fi
}

########
builtin_sched_prepare_files_and_dirs_for_steps()
{
    local dirname=$1

    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        builtin_sched_prepare_files_and_dirs_for_step "${dirname}" $stepname
    done
}

########
builtin_sched_sleep()
{
    # Sleep a certain number of seconds depending on the number of
    # pipeline steps
    local num_steps=${#BUILTIN_SCHED_STEPNAME_TO_IDX[@]}

    if [ ${num_steps} -le ${BUILTIN_SCHED_NSTEPS_SLEEP_THRESHOLD} ]; then
        sleep ${BUILTIN_SCHED_SLEEP_TIME_SHORT}        
    else
        sleep ${BUILTIN_SCHED_SLEEP_TIME_LONG}
    fi
}

########
builtin_sched_execute_pipeline_steps()
{
    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local pfile=$3
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

    # Initialize step status
    builtin_sched_init_step_info "${cmdline}" "${dirname}" ${pfile} || return 1

    # Initialize current step status
    builtin_sched_init_curr_comp_resources || return 1

    # Prepare files and directories for steps
    builtin_sched_prepare_files_and_dirs_for_steps "${dirname}"

    echo "" >&2

    echo "* Executing pipeline steps..." >&2

    # Execute scheduling loop
    local end=0
    while [ ${end} -eq 0 ]; do
        if [ ${builtinsched_debug} -eq 1 ]; then
            echo "[BUILTIN_SCHED] * Iteration ${iterno}" 2>&1
        fi

        # Select steps that should be executed
        if builtin_sched_select_steps_to_be_exec "${dirname}"; then
            # Execute steps
            builtin_sched_exec_steps "${cmdline}" "${dirname}"

            # Wait before starting a new loop
            builtin_sched_sleep
        else
            # There are no steps to be executed

            if builtin_sched_inprogress_steps_pending; then
                # Wait for in-progress steps to finish
                builtin_sched_sleep
            else
                # Finish loop
                end=1
            fi
        fi

        iterno=$((iterno + 1))
    done
}
