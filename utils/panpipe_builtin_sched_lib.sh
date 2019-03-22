# *- bash -*

#############
# CONSTANTS #
#############

BUILTIN_SCHED_FAILED_STEP_STATUS="FAILED"
BUILTIN_SCHED_NO_ARRAY_TASK="NO_ARRAY_TASK"

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
            local script_filename=`get_script_filename ${dirname} ${stepname}`
            local status=`get_step_status ${dirname} ${stepname}`
            local stepdeps=`extract_stepdeps_from_stepspec "$stepspec"`
            local spec_throttle=`extract_attr_from_stepspec "$stepspec" "throttle"`
            local sched_throttle=`get_scheduler_throttle ${spec_throttle}`
            local array_size=`get_task_array_size_for_step "${cmdline}" "${stepspec}"`

            # Get cpus info
            local cpus=`extract_cpus_from_stepspec "$stepspec"`
            str_is_natural_number ${cpus} || { echo "Error: number of cpus ($cpus) for $stepname should be a natural number" >&2; return 1; }

            # Get mem info
            local mem=`extract_mem_from_stepspec "$stepspec"`
            mem=`convert_mem_value_to_mb ${mem}` || { echo "Invalid memory specification for step ${stepname}" >&2; return 1; }
            str_is_natural_number ${mem} || { echo "Error: amount of memory ($mem) for $stepname should be a natural number" >&2; return 1; }

            # Obtain full throttle cpus value
            local full_throttle_cpus=${cpus}
            if [ $array_size -gt 1 ]; then
                full_throttle_cpus=`expr ${cpus} \* ${sched_throttle}`
            fi
            # Check full_throttle_cpus value
            builtin_sched_cpus_within_limit ${full_throttle_cpus} || { echo "Error: number of cpus for step $stepname exceeds limit (cpus: ${cpus}, array size: ${array_size}, throttle: ${sched_throttle})" >&2; return 1; }

            # Obtain full throttle mem value
            local full_throttle_mem=${mem}
            if [ $array_size -gt 1 ]; then
                full_throttle_mem=`expr ${mem} \* ${sched_throttle}`
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
            BUILTIN_SCHED_STEP_MEM[${stepname}]=${mem}
        fi
    done < ${pfile}
}

########
builtin_sched_release_mem()
{
    local stepname=$1
    
    BUILTIN_SCHED_ALLOC_MEM=`expr ${BUILTIN_SCHED_ALLOC_MEM} - ${BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]}`
    BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=0
}

########
builtin_sched_release_cpus()
{
    local stepname=$1
    
    BUILTIN_SCHED_ALLOC_CPUS=`expr ${BUILTIN_SCHED_ALLOC_CPUS} - ${BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]}`
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
        echo `expr ${BUILTIN_SCHED_STEP_MEM[${stepname}]} \* ${ntasks}`
    fi
}

########
builtin_sched_reserve_mem()
{
    local stepname=$1
    local step_mem=`builtin_sched_get_step_mem ${stepname}`
    BUILTIN_SCHED_ALLOC_MEM=`expr ${BUILTIN_SCHED_ALLOC_MEM} + ${step_mem}`
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
        echo `expr ${BUILTIN_SCHED_STEP_CPUS[${stepname}]} \* ${ntasks}`
    fi
}

########
builtin_sched_reserve_cpus()
{
    local stepname=$1
    local step_cpus=`builtin_sched_get_step_cpus ${stepname}`
    BUILTIN_SCHED_ALLOC_CPUS=`expr ${BUILTIN_SCHED_ALLOC_CPUS} + ${step_cpus}`
    BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]=${step_cpus}
}

########
builtin_sched_get_failed_array_task_indices()
{
    local dirname=$1
    local stepname=$2
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local result

    for taskidx in `seq ${array_size}`; do
        local task_status=`get_array_task_status $dirname $stepname $taskidx`
        if [ ${task_status} = ${FAILED_TASK_STATUS} ]; then
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
        local task_status=`get_array_task_status $dirname $stepname $taskidx`
        if [ ${task_status} = ${FINISHED_TASK_STATUS} ]; then
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
        local task_status=`get_array_task_status $dirname $stepname $taskidx`
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
builtin_sched_revise_array_mem()
{
    local dirname=$1
    local stepname=$2

    inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices ${dirname} ${stepname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`    
    step_revised_mem=`builtin_sched_get_step_mem_given_num_tasks ${stepname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_MEM=`expr ${BUILTIN_SCHED_ALLOC_MEM} - ${BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]} + ${step_revised_mem}`
    BUILTIN_SCHED_STEP_ALLOC_MEM[${stepname}]=${step_revised_mem}
}

########
builtin_sched_revise_array_cpus()
{
    local dirname=$1
    local stepname=$2

    inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices ${dirname} ${stepname}`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`    
    step_revised_cpus=`builtin_sched_get_step_cpus_given_num_tasks ${stepname} ${num_inprogress_tasks}`
    BUILTIN_SCHED_ALLOC_CPUS=`expr ${BUILTIN_SCHED_ALLOC_CPUS} - ${BUILTIN_SCHED_STEP_ALLOC_CPUS[${stepname}]} + ${step_revised_cpus}`
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
            local updated_status=`get_step_status ${dirname} ${stepname}`
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
            # Check if resources should be released
            if [ ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${INPROGRESS_STEP_STATUS} ]; then
                builtin_sched_release_mem $stepname
                builtin_sched_release_cpus $stepname
            fi

            # Check if resources should be reserved
            if [ ${prev_status} != ${INPROGRESS_STEP_STATUS} -a ${updated_status} = ${INPROGRESS_STEP_STATUS} ]; then
                builtin_sched_reserve_mem $stepname
                builtin_sched_reserve_cpus $stepname
            fi

            # Check if resources of job array should be revised
            if [ ${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]} -gt 1 -a ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} = ${INPROGRESS_STEP_STATUS} ]; then
                builtin_sched_revise_array_mem $dirname $stepname
                builtin_sched_revise_array_cpus $dirname $stepname
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
            if [ ${prev_status} = ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${INPROGRESS_STEP_STATUS} -a ${updated_status} != ${PARTIALLY_EXECUTED_ARRAY_STEP_STATUS} -a ${updated_status} != ${FINISHED_STEP_STATUS} ]; then
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
        echo `expr ${BUILTIN_SCHED_CPUS} - ${BUILTIN_SCHED_ALLOC_CPUS}`
    fi
}

########
builtin_sched_get_available_mem()
{
    if [ ${BUILTIN_SCHED_MEM} -eq 0 ]; then
        echo 0
    else
        echo `expr ${BUILTIN_SCHED_MEM} - ${BUILTIN_SCHED_ALLOC_MEM}`
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
    local stepdeps_blanks=`replace_str_elem_sep_with_blank "," ${stepdeps}`
    local dep
    for dep in ${stepdeps_blanks}; do
        # Extract information from dependency
        local deptype=`get_deptype_part_in_dep ${dep}`
        local depsname=`get_stepname_part_in_dep ${dep}`

        # Process dependency
        depstatus=${BUILTIN_SCHED_CURR_STEP_STATUS[${depsname}]}
            
        # Process exit code
        case ${deptype} in
            ${AFTER_STEPDEP_TYPE})
                if [ ${depstatus} = ${TODO_STEP_STATUS} -o  ${depstatus} = ${UNFINISHED_STEP_STATUS} ]; then
                    return 1
                fi
                ;;
            ${AFTEROK_STEPDEP_TYPE})
                if [ ${depstatus} != ${FINISHED_STEP_STATUS} ]; then
                    return 1
                fi
                ;;
            ${AFTERNOTOK_STEPDEP_TYPE})
                if [ ${depstatus} != ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
                    return 1
                fi
                ;;
            ${AFTERANY_STEPDEP_TYPE})
                if [ ${depstatus} = ${FINISHED_STEP_STATUS} -o ${depstatus} = ${BUILTIN_SCHED_FAILED_STEP_STATUS} ]; then
                    return 1
                fi 
                ;;
        esac
    done

    return 0
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
    local inprogress_tasks=`builtin_sched_get_inprogress_array_task_indices $dirname $stepname`
    local num_inprogress_tasks=`get_num_words_in_string "${inprogress_tasks}"`
    local result=`expr ${throttle} - ${num_inprogress_tasks}`
    echo ${result}
}

########
builtin_sched_get_pending_task_indices()
{
    local dirname=$1
    local stepname=$2
    local max_task_num=$3
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}

    local result
    local num_added_tasks=0
    local idx=1
    while [ ${idx} -le ${array_size} ]; do
        task_status=`get_array_task_status $dirname $stepname $idx`
        # Check if task is pending
        if [ ${task_status} = ${TODO_TASK_STATUS} ]; then
            # Task is pending
            if [ "${result}" = "" ]; then
                result=${idx}
            else
                result="${result} ${idx}"
            fi
            # Update number of added tasks
            num_added_tasks=`expr ${num_added_tasks} + 1`
            # Check if number of added tasks has reached the given
            # maximum number of tasks
            if [ ${num_added_tasks} -eq ${max_task_num} ]; then
                break
            fi
        fi
        idx=`expr ${idx} + 1`
    done

    echo $result
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
                pending_task_indices=`builtin_sched_get_pending_task_indices ${dirname} ${stepname} ${max_task_num}`
                if [ "${pending_task_indices}" != "" ]; then
                    BUILTIN_SCHED_EXECUTABLE_STEPS[${stepname}]=${pending_task_indices}
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
    ${panpipe_bindir}/solve_knapsack_ga -s ${specfile} -c ${available_cpus},${available_mem} -t ${time_limit}
}

########
builtin_sched_solve_knapsack()
{
    local dirname=$1

    # Create file with item and weight specification
    specfile=${dirname}/.knapsack_spec.txt
    rm -f ${specfile}
    builtin_sched_print_knapsack_spec > ${specfile}
    
    # Solve knapsack problem
    local knapsack_sol=${dirname}/.knapsack_sol.txt
    builtin_sched_print_knapsack_sol > ${knapsack_sol}

    # Store solution in output variable
    BUILTIN_SCHED_SELECTED_STEPS=`${AWK} -F ": " '{if($1=="Packed items") print $2}' ${knapsack_sol}`
}

########
builtin_sched_count_executable_steps()
{
    echo ${#BUILTIN_SCHED_EXECUTABLE_STEPS[@]}
}

########
builtin_sched_end_condition_reached()
{
    # Iterate over steps
    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        status=${BUILTIN_SCHED_CURR_STEP_STATUS[${stepname}]}
        if [ ${status} = ${INPROGRESS_STEP_STATUS} -o ${status} = ${PARTIALLY_EXECUTED_ARRAY_STEP_STATUS} -o ${status} = ${TODO_STEP_STATUS} -o ${status} = ${UNFINISHED_STEP_STATUS} ]; then
            return 1
        fi        
    done
    
    return 0
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
        tid=`builtinsched_extract_tid_from_knapsack_name ${knapsack_name}`
        sel_steps="${sel_steps} ${knapsack_name} -> ${sname},${tid};"
    done
    echo $sel_steps
}

########
builtin_sched_select_steps_to_be_exec()
{
    local dirname=$1

    # Obtain updated status for steps
    local -A BUILTIN_SCHED_CURR_STEP_STATUS_UPDATED
    builtin_sched_get_updated_step_status $dirname

    # Update computational resources depending on changes
    builtin_sched_update_comp_resources $dirname

    # Set updated status as current one
    builtin_sched_fix_updated_step_status

    # Obtain set of steps that can be executed
    local -A BUILTIN_SCHED_EXECUTABLE_STEPS
    builtin_sched_get_executable_steps $dirname

    if [ ${builtinsched_debug} -eq 1 ]; then
        local step_status=`builtin_sched_get_debug_step_status_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_CURR_STEP_STATUS: ${step_status}"
        echo "[BUILTIN_SCHED] - COMPUTATIONAL RESOURCES: total cpus= ${BUILTIN_SCHED_CPUS}, allocated cpus= ${BUILTIN_SCHED_ALLOC_CPUS}; total mem= ${BUILTIN_SCHED_MEM}, allocated mem= ${BUILTIN_SCHED_ALLOC_MEM}"
        local exec_steps=`builtin_sched_get_debug_exec_steps_info`
        echo "[BUILTIN_SCHED] - BUILTIN_SCHED_EXECUTABLE_STEPS: ${exec_steps}" 2>&1
    fi
        
    if builtin_sched_end_condition_reached; then
        # End condition reached
        return 1
    else
        # If there are executable steps, select which ones will be executed
        num_exec_steps=${#BUILTIN_SCHED_EXECUTABLE_STEPS[@]}
        if [ ${num_exec_steps} -gt 0 ]; then
            builtin_sched_solve_knapsack $dirname

            if [ ${builtinsched_debug} -eq 1 ]; then
                local sel_steps=`builtin_sched_get_debug_sel_steps_info` 
                echo "[BUILTIN_SCHED] - BUILTIN_SCHED_SELECTED_STEPS: ${sel_steps}" 2>&1
            fi

            return 0
        else
            return 0
        fi
    fi
}

########
builtin_sched_print_pid_to_file()
{
    if [ "${BUILTIN_SCHED_PID_FILENAME}" != "" ]; then
        echo $$ > ${BUILTIN_SCHED_PID_FILENAME}
    fi
}

########
builtin_sched_print_script_header()
{
    local fname=$1
    local step_name=$2
    
    echo "PANPIPE_TASK_FILENAME=${fname}"
    echo "PANPIPE_STEP_NAME=${step_name}"
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
builtin_sched_print_script_body()
{
    # Initialize variables
    local num_scripts=$1
    local fname=$2
    local base_fname=`$BASENAME $fname`
    local taskidx=$3
    local funct=$4
    local post_funct=$5
    local script_opts=$6

    # Write treatment for task id
    if [ ${num_scripts} -gt 1 ]; then
        local varname=`builtin_sched_get_task_array_task_varname ${base_fname} ${taskidx}`
        echo "if [ \"\${${varname}}\" = 1 ]; then"
    fi

    # Write function to be executed
    if [ ${num_scripts} -gt 1 ]; then
        echo "execute_funct_plus_postfunct ${num_scripts} ${fname} ${taskidx} ${funct} ${post_funct} \"${script_opts}\" > ${fname}_${taskidx}.${BUILTIN_SCHED_LOG_FEXT} 2>&1"
    else
        echo "execute_funct_plus_postfunct ${num_scripts} ${fname} ${taskidx} ${funct} ${post_funct} \"${script_opts}\" > ${fname}.${BUILTIN_SCHED_LOG_FEXT} 2>&1"
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
    local fname=$1
    local funct=$2
    local post_funct=$3
    local opts_array_name=$4[@]
    local opts_array=("${!opts_array_name}")
    
    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > ${fname} || return 1
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_bashisms >> ${fname} || return 1

    # Print header
    builtin_sched_print_script_header ${fname} ${funct} >> ${fname} || return 1
    
    # Iterate over options array
    local lineno=1
    local num_scripts=${#opts_array[@]}
    local script_opts
    for script_opts in "${opts_array[@]}"; do

        builtin_sched_print_script_body ${num_scripts} ${fname} ${lineno} ${funct} ${post_funct} "${script_opts}" >> ${fname} || return 1

        lineno=`expr $lineno + 1`

    done

    # Print foot
    builtin_sched_print_script_foot >> ${fname} || return 1
    
    # Give execution permission
    chmod u+x ${fname} || return 1
}

########
builtin_sched_launch()
{
    # Initialize variables
    local file=$1
    local taskidx=$2
    local base_fname=`$BASENAME $file`

    # Enable execution of specific task id
    if [ ${taskidx} != ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        local task_varname=`builtin_sched_get_task_array_task_varname ${base_fname} ${taskidx}`
        export ${task_varname}=1
    fi

    # Set variable indicating name of file storing PID
    if [ ${taskidx} = ${BUILTIN_SCHED_NO_ARRAY_TASK} ]; then
        export BUILTIN_SCHED_PID_FILENAME=${file}.${STEPID_FEXT}
    else
        export BUILTIN_SCHED_PID_FILENAME=${file}_${taskidx}.${ARRAY_TASKID_FEXT}
    fi

    # Execute file
    ${file} &
    local pid=$!
    
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
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} (TASKIDX: ${taskidx}) ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2
    
    # Create script
    local script_filename=`get_script_filename ${dirname} ${stepname}`
    local step_function=`get_name_of_step_function ${stepname}`
    local step_function_post=`get_name_of_step_function_post ${stepname}`
    define_opts_for_script "${cmdline}" "${stepspec}" || return 1
    local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
    local array_size=${#script_opts_array[@]}
    if [ "${launched_tasks}" = "" ]; then
        builtin_sched_create_script ${script_filename} ${step_function} "${step_function_post}" "script_opts_array"
    fi
    
    # Archive script
    if [ "${launched_tasks}" = "" ]; then
        archive_script ${script_filename}
    fi

    # Launch script
    local task_array_list=${taskidx}
    builtin_sched_launch ${script_filename} "${taskidx}" || { echo "Error while launching step!" >&2 ; return 1; }
        
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
    local step_idx=`echo ${knapsack_name} | ${AWK} -F "_" '{print $1}'`
    echo ${BUILTIN_SCHED_IDX_TO_STEPNAME[${step_idx}]}
}

########
builtinsched_extract_tid_from_knapsack_name()
{
    local knapsack_name=$1
    local tid=`echo ${knapsack_name} | ${AWK} -F "_" '{print $2}'`    
    if [ "${tid}" = "" ]; then
        echo ${BUILTIN_SCHED_NO_ARRAY_TASK}
    else
        echo ${tid}
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
        stepname=`builtinsched_extract_step_from_knapsack_name ${knapsack_name}`
        taskidx=`builtinsched_extract_tid_from_knapsack_name ${knapsack_name}`
        
        # Execute step
        builtin_sched_execute_step "${cmdline}" ${dirname} ${stepname} ${taskidx} || return 1
        
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
        builtin_sched_exec_steps_and_update_status "${cmdline}" $dirname
    fi
    
    # Update computational resources after execution
    builtin_sched_update_comp_resources $dirname

    # Set updated status as current one
    builtin_sched_fix_updated_step_status
}

########
builtin_sched_prepare_files_and_dirs_for_step()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`
    local array_size=${BUILTIN_SCHED_STEP_ARRAY_SIZE[${stepname}]}
    local status=`get_step_status ${dirname} ${stepname}`
    
    # Prepare files for step
    update_step_completion_signal ${status} ${script_filename} || { echo "Error when updating step completion signal for step" >&2 ; return 1; }
    clean_step_log_files ${array_size} ${script_filename} || { echo "Error when cleaning log files for step" >&2 ; return 1; }
    clean_step_id_files ${array_size} ${script_filename} || { echo "Error when cleaning id files for step" >&2 ; return 1; }
    prepare_fifos_owned_by_step ${stepname}

    # Prepare output directory
    if [ ${array_size} -eq 1 ]; then
        prepare_outdir_for_step ${dirname} ${stepname} || { echo "Error when preparing output directory for step" >&2 ; return 1; }
    else
        prepare_outdir_for_step_array ${dirname} ${stepname} || { echo "Error when preparing output directory for step" >&2 ; return 1; }
    fi
}

########
builtin_sched_prepare_files_and_dirs_for_steps()
{
    local dirname=$1

    local stepname
    for stepname in "${!BUILTIN_SCHED_CURR_STEP_STATUS[@]}"; do
        builtin_sched_prepare_files_and_dirs_for_step $dirname $stepname
    done
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
    builtin_sched_init_step_info "${cmdline}" ${dirname} ${pfile} || return 1

    # Initialize current step status
    builtin_sched_init_curr_comp_resources || return 1

    # Prepare files and directories for steps
    builtin_sched_prepare_files_and_dirs_for_steps ${dirname}

    echo "" >&2

    echo "* Executing pipeline steps..." >&2

    # Execute scheduling loop
    local end=0
    local sleep_time=5
    while [ ${end} -eq 0 ]; do
        if [ ${builtinsched_debug} -eq 1 ]; then
            echo "[BUILTIN_SCHED] * Iteration ${iterno}" 2>&1
        fi

        # Select steps that should be executed
        if builtin_sched_select_steps_to_be_exec ${dirname}; then
            # Execute steps
            builtin_sched_exec_steps "${cmdline}" ${dirname}
            
            sleep ${sleep_time}
        else
            # There are no steps to be executed
            end=1
        fi

        iterno=`expr $iterno + 1`
    done
}
