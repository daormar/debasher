# *- bash -*

#############
# CONSTANTS #
#############

# STRING HANDLING
NOFILE="_NONE_"
ATTR_NOT_FOUND="_ATTR_NOT_FOUND_"
OPT_NOT_FOUND="_OPT_NOT_FOUND_"
DEP_NOT_FOUND="_DEP_NOT_FOUND_"
FUNCT_NOT_FOUND="_FUNCT_NOT_FOUND_"
INVALID_JID="_INVALID_JID_"
INVALID_PID="_INVALID_PID_"
VOID_VALUE="_VOID_VALUE_"
GENERAL_OPT_CATEGORY="GENERAL"

# STEP STATUSES
FINISHED_STEP_STATUS="FINISHED"
FINISHED_STEP_STATUS_EXIT_CODE=0
INPROGRESS_STEP_STATUS="IN-PROGRESS"
INPROGRESS_STEP_STATUS_EXIT_CODE=1
UNFINISHED_STEP_STATUS="UNFINISHED"
UNFINISHED_STEP_STATUS_EXIT_CODE=2
REEXEC_STEP_STATUS="REEXECUTE"
REEXEC_STEP_STATUS_EXIT_CODE=3
TODO_STEP_STATUS="TO-DO"
TODO_STEP_STATUS_EXIT_CODE=4

# REEXEC REASONS
FORCED_REEXEC_REASON="forced"
DEPS_REEXEC_REASON="dependencies"

# STEP DEPENDENCIES
AFTER_STEPDEP_TYPE="after"
AFTEROK_STEPDEP_TYPE="afterok"
AFTERNOTOK_STEPDEP_TYPE="afternotok"
AFTERANY_STEPDEP_TYPE="afterany"

# PIPELINE STATUSES
PIPELINE_FINISHED_EXIT_CODE=0
PIPELINE_IN_PROGRESS_EXIT_CODE=1
PIPELINE_ONE_OR_MORE_STEPS_IN_PROGRESS_EXIT_CODE=2
PIPELINE_UNFINISHED_EXIT_CODE=3

# PANPIPE STATUS
PANPIPE_SCHEDULER=""
BUILTIN_SCHEDULER="BUILTIN"
SLURM_SCHEDULER="SLURM"

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store help about pipeline options
declare -A PIPELINE_OPT_DESC
declare -A PIPELINE_OPT_TYPE
declare -A PIPELINE_OPT_CATEG
declare -A PIPELINE_CATEG_MAP

# Declare associative array to memoize command line options
declare -A MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
LAST_PROC_LINE_MEMOPTS=""

# Declare array used to save option lists for scripts
declare -a SCRIPT_OPT_LIST_ARRAY

# Declare variable to store name of output directory
declare PIPELINE_OUTDIR

# Declare associative array to store names of loaded modules
declare -A PIPELINE_MODULES

# Declare associative array to store name of shared directories
declare -A PIPELINE_SHDIRS

# Declare associative array to store names of fifos
declare -A PIPELINE_FIFOS

# Declare scheduling-related variables
declare PANPIPE_SCHEDULER
declare -A PANPIPE_REEXEC_STEPS
declare PANPIPE_DEFAULT_NODES
declare PANPIPE_DEFAULT_ARRAY_TASK_THROTTLE=1

# Declare associative array to store exit code for processes
declare -A EXIT_CODE

#####################
# GENERAL FUNCTIONS #
#####################

########
panpipe_version()
{
    echo "${panpipe_pkgname} version: ${panpipe_version}" >&2
}

########
pipe_fail()
{
    # test if there is at least one command to exit with a non-zero status
    local pipe_status_elem
    for pipe_status_elem in ${PIPESTATUS[*]}; do 
        if test ${pipe_status_elem} -ne 0; then 
            return 1; 
        fi 
    done
    return 0
}

########
init_bash_shebang_var()
{
    echo "#!${BASH}"
}

########
is_absolute_path()
{
    case $1 in
        /*) echo 1 ;;
       *) echo 0 ;;
    esac
}

########
get_absolute_path()
{
    local file=$1
    # Check if an absolute path was given
    local absolute=`is_absolute_path $file`
    if [ $absolute -eq 1 ]; then
        echo $file
    else
        local oldpwd=$PWD
        local basetmp=`$BASENAME $PWD/$file`
        local dirtmp=`$DIRNAME $PWD/$file`
        cd $dirtmp
        local result=${PWD}/${basetmp}
        cd $oldpwd
        echo $result
    fi
}

########
exclude_readonly_vars()
{
    $AWK -F "=" 'BEGIN{
                         readonlyvars["BASHOPTS"]=1
                         readonlyvars["BASH_VERSINFO"]=1
                         readonlyvars["EUID"]=1
                         readonlyvars["PPID"]=1
                         readonlyvars["SHELLOPTS"]=1
                         readonlyvars["UID"]=1
                        }
                        {
                         if(!($1 in readonlyvars)) printf"%s\n",$0
                        }'
}

########
exclude_bashisms()
{
    $AWK '{if(index($1,"=(")==0) printf"%s\n",$0}'
}

########
serialize_string_array()
{
    local str_array_name=$1[@]
    local str_array=("${!str_array_name}")
    local sep=$2
    local max_elems=$3
    local result=""
    local num_elem=0

    local str
    for str in "${str_array[@]}"; do
        # Check if number of elements has been exceeded
        if [ ! -z "${max_elems}" ]; then
            if [ ${num_elem} -ge ${max_elems} ]; then
                if [ ! -z "${result}" ]; then
                    result="${result}${sep}..."
                    break
                fi
            fi
        fi

        # Add new element
        if [ -z "${result}" ]; then
            result=${str}
        else
            result="${result}${sep}${str}"
        fi

        num_elem=`expr ${num_elem} + 1`
    done

    echo $result
}

########
check_func_exists()
{
    local funcname=$1
    
    type ${funcname} >/dev/null 2>&1 || return 1

    return 0
}

########
set_panpipe_outdir()
{
    local abs_outd=$1

    PIPELINE_OUTDIR=${abs_outd}
}

########
set_panpipe_scheduler()
{
    local sched=$1

    case $sched in
        ${SLURM_SCHEDULER})
            PANPIPE_SCHEDULER=${SLURM_SCHEDULER}
            ;;
        ${BUILTIN_SCHEDULER})
            PANPIPE_SCHEDULER=${BUILTIN_SCHEDULER}
            ;;
        *)  echo "Error: ${sched} is not a valid scheduler"
            PANPIPE_SCHEDULER=""
            return 1
            ;;
    esac
}

########
set_panpipe_default_nodes()
{
    local value=$1
    
    PANPIPE_DEFAULT_NODES=$value
}

########
set_panpipe_default_array_task_throttle()
{
    local value=$1
    
    PANPIPE_DEFAULT_ARRAY_TASK_THROTTLE=$value
}

########
determine_scheduler()
{
    # Check if schedulers were disabled
    if [ ${DISABLE_SCHEDULERS} = "yes" ]; then
        echo ${BUILTIN_SCHEDULER}
    else
        # Check if scheduler was already specified
        if [ -z "${PANPIPE_SCHEDULER}" ]; then
            # Scheduler not specified, set it based on information
            # gathered during package configuration
            if [ -z "${SBATCH}" ]; then
                echo ${BUILTIN_SCHEDULER}
            else
                echo ${SLURM_SCHEDULER}
            fi
        else
            echo ${PANPIPE_SCHEDULER}
        fi
    fi
}

########
get_job_array_task_varname()
{
    local arrayname=$1
    local taskid=$2
    
    echo "BUILTIN_SCHED_ARRAY_TASK_${arrayname}_${taskid}"
}

########
get_job_array_task_throttle_varname()
{
    local arrayname=$1

    echo "BUILTIN_SCHED_ARRAY_TASK_THROTTLE_${arrayname}"
}

########
execute_funct_plus_postfunct()
{
    local num_scripts=$1
    local fname=$2
    local base_fname=`$BASENAME $fname`
    local taskid=$3
    local funct=$4
    local post_funct=$5
    local script_opts=$6

    # Execute step function
    $funct ${script_opts}
    local funct_exit_code=$?
    if [ ${funct_exit_code} -ne 0 ]; then
        echo "Error: execution of ${funct} failed with exit code ${funct_exit_code}" >&2
    else
        echo "Function ${funct} successfully executed" >&2
    fi

    # Execute step post-function
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        ${post_funct} ${script_opts} || { echo "Error: execution of ${post_funct} failed with exit code $?" >&2 ; return 1; }
    fi

    # Treat errors
    if [ ${funct_exit_code} -ne 0 ]; then
        return 1;
    fi

    # Signal step completion
    signal_step_completion ${fname} ${taskid} ${num_scripts}
}

########
job_array_throttle_wait()
{
    local num_concurrent_tasks=$1
    local throttle=$2

    if [ ${num_concurrent_tasks} -ge ${throttle} ]; then
        wait || exit 1
        return 1
    else
        return 0
    fi
}

########
print_task_header_builtin_sched()
{
    local step_name=$1
    
    echo "PANPIPE_STEP_NAME=${step_name}"
    echo "NUM_CONCURRENT_PIPE_TASKS=0"
}

########
print_task_body_builtin_sched()
{
    # Initialize variables
    local num_scripts=$1
    local fname=$2
    local base_fname=`$BASENAME $fname`
    local taskid=$3
    local funct=$4
    local post_funct=$5
    local script_opts=$6
    
    # Write treatment for task id
    if [ ${num_scripts} -gt 1 ]; then
        local varname=`get_job_array_task_varname ${base_fname} ${taskid}`
        echo "if [ \"\${${varname}}\" -eq 1 ]; then"
    fi

    # Write function to be executed
    echo "execute_funct_plus_postfunct ${num_scripts} ${fname} ${taskid} ${funct} ${post_funct} \"${script_opts}\" &"

    # Add code related to job array task throttle
    echo "NUM_CONCURRENT_PIPE_TASKS=\`expr \${NUM_CONCURRENT_PIPE_TASKS} + 1\`"

    # Close if statement
    if [ ${num_scripts} -gt 1 ]; then
        echo "fi" 
    fi

    local throttle_varname=`get_job_array_task_throttle_varname ${base_fname}`
    echo "job_array_throttle_wait \${NUM_CONCURRENT_PIPE_TASKS} \${${throttle_varname}} || NUM_CONCURRENT_PIPE_TASKS=0"
}

########
print_task_foot_builtin_sched()
{
    echo "wait"
}

########
create_builtin_scheduler_script()
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
    print_task_header_builtin_sched ${funct} >> ${fname} || return 1
    
    # Iterate over options array
    local lineno=1
    local num_scripts=${#opts_array[@]}
    local script_opts
    for script_opts in "${opts_array[@]}"; do

        print_task_body_builtin_sched ${num_scripts} ${fname} ${lineno} ${funct} ${post_funct} "${script_opts}" >> ${fname} || return 1

        lineno=`expr $lineno + 1`

    done

    # Print foot
    print_task_foot_builtin_sched >> ${fname} || return 1
    
    # Give execution permission
    chmod u+x ${fname} || return 1
}

########
print_task_header_slurm_sched()
{
    local step_name=$1
    
    echo "PANPIPE_STEP_NAME=${step_name}"
}

########
print_task_body_slurm_sched()
{
    # Initialize variables
    local num_scripts=$1
    local taskid=$2
    local funct=$3
    local post_funct=$4
    local script_opts=$5

    # Write treatment for task id
    if [ ${num_scripts} -gt 1 ]; then
        echo "if [ \${SLURM_ARRAY_TASK_ID} -eq $taskid ]; then"
    fi

    # Write function to be executed
    echo "${funct} ${script_opts}"
    echo "funct_exit_code=\$?"
    echo "if [ \${funct_exit_code} -ne 0 ]; then echo \"Error: execution of \${funct} failed with exit code \${funct_exit_code}\" >&2; else echo \"Function \${funct} successfully executed\" >&2; fi"
    
    # Write function for cleaning if it was provided
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        echo "${post_funct} ${script_opts} || { echo \"Error: execution of \${post_funct} failed with exit code \$?\" >&2 ;exit 1; }"
    fi

    # Return if function to execute failed
    echo "if [ \${funct_exit_code} -ne 0 ]; then exit 1; fi" 
        
    # Write command to signal step completion
    echo "signal_step_completion ${fname} ${lineno} ${num_scripts}" 

    # Close if statement
    if [ ${num_scripts} -gt 1 ]; then
        echo "fi" 
    fi
}

########
print_task_foot_slurm_sched()
{
    :
}

########
create_slurm_script()
{
    # Init variables
    local fname=$1
    local funct=$2
    local post_funct=$3
    local opts_array_name=$4[@]
    local opts_array=("${!opts_array_name}")
    local num_scripts=${#opts_array[@]}

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > ${fname} || return 1

    # Set SLURM options
    echo "#SBATCH --job-name=${funct}" >> ${fname} || return 1
    if [ ${num_scripts} -eq 1 ]; then
        echo "#SBATCH --output=${fname}.slurm_out" >> ${fname} || return 1
    else
        echo "#SBATCH --output=${fname}_%a.slurm_out" >> ${fname} || return 1
    fi
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_bashisms >> ${fname} || return 1

    # Print header
    print_task_header_slurm_sched ${funct} >> ${fname} || return 1

    # Iterate over options array
    local lineno=1
    local script_opts
    for script_opts in "${opts_array[@]}"; do

        print_task_body_slurm_sched ${num_scripts} ${lineno} ${funct} ${post_funct} "${script_opts}" >> ${fname} || return 1

        lineno=`expr $lineno + 1`
        
    done

    # Print foot
    print_task_foot_builtin_sched >> ${fname} || return 1

    # Give execution permission
    chmod u+x ${fname} || return 1
}

########
create_script()
{
    # Init variables
    local fname=$1
    local funct=$2
    local post_funct=$3
    local opts_array_name=$4

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            create_slurm_script $fname $funct "${post_funct}" ${opts_array_name}
            ;;
        ${BUILTIN_SCHEDULER})
            create_builtin_scheduler_script $fname $funct "${post_funct}" ${opts_array_name}
            ;;
    esac
}

########
get_file_timestamp()
{
    local file=$1
    ${PYTHON} -c "import os; t=os.path.getmtime('${file}'); print int(t)"
}

########
get_slurm_cpus_opt()
{
    local cpus=$1

    if [ "${cpus}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--cpus-per-task=${cpus}"
    fi
}

########
get_slurm_mem_opt()
{
    local mem=$1

    if [ "${mem}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--mem=${mem}"
    fi
}

########
get_slurm_time_opt()
{
    local time=$1

    if [ "${time}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--time ${time}"
    fi
}

########
get_slurm_account_opt()
{
    local account=$1

    if [ "${account}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "-A ${account}"
    fi
}

########
get_slurm_nodes_opt()
{
    local nodes=$1

    if [ "${nodes}" = ${ATTR_NOT_FOUND} ]; then
        if [ "${PANPIPE_DEFAULT_NODES}" != "" ]; then
            echo "-w ${PANPIPE_DEFAULT_NODES}"
        else
            echo ""
        fi
    else
        echo "-w ${nodes}"
    fi
}

########
get_slurm_partition_opt()
{
    local partition=$1

    if [ "${partition}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--partition=${partition}"
    fi
}

########
get_script_filename() 
{
    local dirname=$1
    local stepname=$2
    
    echo ${dirname}/scripts/${stepname}
}

########
remove_suffix_from_stepname()
{
    local stepname=$1
    
    echo ${stepname} | $AWK '{if(index($1,"__")==0){print $1} else{printf "%s\n",substr($1,1,index($1,"__")-1)}}'
}

########
get_name_of_step_function()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`
    
    echo "${stepname_wo_suffix}"
}

########
get_name_of_step_function_post()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    local step_function_post="${stepname_wo_suffix}_post"

    if check_func_exists ${step_function_post}; then
        echo ${step_function_outdir}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_name_of_step_function_outdir()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    local step_function_outdir="${stepname_wo_suffix}_outdir_basename"

    if check_func_exists ${step_function_outdir}; then
        echo ${step_function_outdir}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_explain_cmdline_opts_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_explain_cmdline_opts
}

########
get_define_opts_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_define_opts
}

########
get_conda_envs_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_conda_envs
}

########
define_opts_for_script()
{
    local cmdline=$1
    local stepspec=$2
    local stepname=`extract_stepname_from_stepspec "$stepspec"`
    
    clear_opt_list_array
    local define_opts_funcname=`get_define_opts_funcname ${stepname}`
    ${define_opts_funcname} "${cmdline}" "${stepspec}" || return 1
}

########
find_dependency_for_step()
{
    local stepspec=$1
    local stepname_part=$2

    local stepdeps=`extract_stepdeps_from_stepspec "$stepspec"`
    local prevIFS=$IFS
    IFS=','
    local dep
    for dep in ${stepdeps}; do
        local stepname_part_in_dep=`get_stepname_part_in_dep ${dep}`
        if [ "${stepname_part_in_dep}" = ${stepname_part} ]; then
            echo ${dep}
            IFS=${prevIFS}
            return 0
        fi
    done
    IFS=${prevIFS}
    echo ${DEP_NOT_FOUND}
    return 1
}

########
get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd=${PIPELINE_OUTDIR}

        # Get stepname
        local stepname_part=`echo ${dep} | $AWK -F ":" '{print $2}'`
        
        get_step_outdir ${outd} ${stepname_part}
    fi
}

########
get_outd_for_dep_given_stepspec()
{
    local stepspec=$1
    local depname=$2
    
    local dep=`find_dependency_for_step "${stepspec}" $depname`
    if [ ${dep} = ${DEP_NOT_FOUND} ]; then
        return 1
    else
        local outd=`get_outd_for_dep "${dep}"`
        echo ${outd}
        return 0
    fi
}

########
apply_deptype_to_stepids()
{
    # Initialize variables
    local stepids=$1
    local deptype=$2

    # Apply deptype
    local result=""
    local prevIFS=$IFS
    IFS=','
    local id
    for id in ${stepids}; do
        if [ -z "" ]; then
            result=${deptype}:${id}
        else
            result=${result}","${deptype}:${id}
        fi
    done
    IFS=${prevIFS}

    echo $result
}

########
get_slurm_dependency_opt()
{
    local stepdeps=$1

    # Create dependency option
    if [ "${stepdeps}" = ${ATTR_NOT_FOUND} -o "${stepdeps}" = "" ]; then
        echo ""
    else
        echo "--dependency=${stepdeps}"
    fi
}

########
get_job_array_list()
{
    local file=$1
    local array_size=$2

    if [ -f ${file}.finished ]; then
        # Some jobs were completed, return list containing pending ones

        # Create associative map containing completed jobs
        local -A completed_jobs
        while read line; do
            local fields=( $line )
            local num_fields=${#fields[@]}
            if [ ${num_fields} -eq 7 ]; then
                local id=${fields[3]}
                completed_jobs[${id}]="1"
            fi
        done < ${file}.finished
            
        # Create string enumerating pending jobs
        local pending_jobs=""
        local id=1
        while [ $id -le ${array_size} ]; do
            if [ -z "${completed_jobs[${id}]}" ]; then
                if [ -z "${pending_jobs}" ]; then
                    pending_jobs=${id}
                else
                    pending_jobs="${pending_jobs},${id}"
                fi
            fi
            id=`expr $id + 1`
        done

        echo ${pending_jobs}
    else
        # No jobs were completed, return list containing all of them
        echo "1-${array_size}"
    fi
}

########
get_slurm_job_array_opt()
{
    local file=$1
    local job_array_list=$2
    local throttle=$3

    if [ ${job_array_list} = "1-1" -o ${job_array_list} = "1" ]; then
        echo ""
    else
        echo "--array=${job_array_list}%${throttle}"
    fi
}

########
get_deptype_part_in_dep()
{
    local dep=$1
    echo ${dep} | $AWK -F ":" '{print $1}'
}

########
get_stepname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "none" ]; then
        echo ${dep}
    else
        echo ${dep} | $AWK -F ":" '{print $2}'
    fi
}

########
get_id_part_in_dep()
{
    local dep=$1
    echo ${dep} | $AWK -F ":" '{print $2}'
}

########
get_exit_code()
{
    local pid=$1
    local outvar=$2

    # Search for exit code in associative array
    if [ -z "${EXIT_CODE[$pid]}" ]; then
        wait $pid
        local exit_code=$?
        EXIT_CODE[$pid]=${exit_code}
        eval "${outvar}='${exit_code}'"
    else
        eval "${outvar}='${EXIT_CODE[$pid]}'"
    fi
}

########
wait_for_deps_builtin_scheduler()
{
    # Initialize variables
    local stepdeps=$1

    # Iterate over dependencies
    local prevIFS=$IFS
    IFS=','
    local dep
    for dep in ${stepdeps}; do
        # Extract information from dependency
        local deptype=`get_deptype_part_in_dep ${dep}`
        local pid=`get_id_part_in_dep ${dep}`

        # Wait for process to finish (except for "after" dependency
        # types)
        if [ ${deptype} != ${AFTER_STEPDEP_TYPE} ]; then
            get_exit_code $pid _exit_code
            local exit_code=${_exit_code}
            
            # Process exit code
            case ${deptype} in
                ${AFTEROK_STEPDEP_TYPE})
                    if [ ${exit_code} -ne 0 ]; then
                        return 1
                        IFS=${prevIFS}
                    fi
                ;;
                ${AFTERNOTOK_STEPDEP_TYPE})
                    if [ ${exit_code} -eq 0 ]; then
                        return 1
                        IFS=${prevIFS}
                    fi 
                ;;
                ${AFTERANY_STEPDEP_TYPE})
                # No actions required
                    :
                ;;
            esac
        fi
    done
    IFS=${prevIFS}
    return 0
}

########
check_job_array_elem_is_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        return 0
    else
        return 1
    fi
}

########
get_start_id_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[0]}
    else
        echo "-1"
    fi
}

########
get_end_id_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[1]}
    else
        echo "-1"
    fi
}

########
get_scheduler_throttle()
{
    local stepspec_throttle=$1

    if [ "${stepspec_throttle}" = ${ATTR_NOT_FOUND} ]; then
        echo ${PANPIPE_DEFAULT_ARRAY_TASK_THROTTLE}
    else
        echo ${stepspec_throttle}
    fi
}

########
builtin_scheduler_launch()
{
    # Initialize variables
    local file=$1
    local job_array_list=$2
    local stepspec=$3
    local stepdeps=$4
    local outvar=$5
    local base_fname=`$BASENAME $file`

    # Export task throttle variable
    local spec_throttle=`extract_attr_from_stepspec "$stepspec" "throttle"`
    local sched_throttle=`get_scheduler_throttle ${spec_throttle}`
    local throttle_varname=`get_job_array_task_throttle_varname ${base_fname}`
    export ${throttle_varname}=${sched_throttle}

    # Determine which jobs from the array will be executed
    local prevIFS=$IFS
    IFS=','
    local elem
    for elem in ${job_array_list}; do
        if check_job_array_elem_is_range $elem; then
            local start_id=`get_start_id_in_range $elem`
            local end_id=`get_end_id_in_range $elem`
            local id=${start_id}
            while [ ${id} -le ${end_id} ]; do
                local task_varname=`get_job_array_task_varname ${base_fname} ${id}`
                export ${task_varname}=1
                id=`expr $id + 1`
            done
        else
            local task_varname=`get_job_array_task_varname ${base_fname} ${elem}`
            export ${task_varname}=1
        fi
    done
    IFS=${prevIFS}

    # Execute file
    if wait_for_deps_builtin_scheduler "${stepdeps}"; then
        ${file} > ${file}.log 2>&1 &
        local pid=$!
        eval "${outvar}='${pid}'"
    else
        local pid=${INVALID_PID}
        eval "${outvar}='${pid}'"
    fi
}

########
slurm_launch()
{
    # Initialize variables
    local file=$1
    local job_array_list=$2
    local stepspec=$3
    local stepdeps=$4
    local outvar=$5

    # Retrieve specification
    local cpus=`extract_attr_from_stepspec "$stepspec" "cpus"`
    local mem=`extract_attr_from_stepspec "$stepspec" "mem"`
    local time=`extract_attr_from_stepspec "$stepspec" "time"`
    local account=`extract_attr_from_stepspec "$stepspec" "account"`
    local partition=`extract_attr_from_stepspec "$stepspec" "partition"`
    local nodes=`extract_attr_from_stepspec "$stepspec" "nodes"`
    local spec_throttle=`extract_attr_from_stepspec "$stepspec" "throttle"`
    local sched_throttle=`get_scheduler_throttle ${spec_throttle}`

    # Define options for sbatch
    local cpus_opt=`get_slurm_cpus_opt ${cpus}`
    local mem_opt=`get_slurm_mem_opt ${mem}`
    local time_opt=`get_slurm_time_opt ${time}`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${stepdeps}"`
    local jobarray_opt=`get_slurm_job_array_opt ${file} ${job_array_list} ${sched_throttle}`
    
    # Submit job
    local jid=$($SBATCH ${cpus_opt} ${mem_opt} ${time_opt} --parsable ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} ${file})
    
    # Check for errors
    if [ -z "$jid" ]; then
        jid=${INVALID_JID}
    fi

    eval "${outvar}='${jid}'"
}

########
launch()
{
    # Initialize variables
    local file=$1
    local job_array_list=$2
    local stepspec=$3
    local stepdeps=$4
    local outvar=$5
    
    # Launch file
    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            slurm_launch ${file} "${job_array_list}" "${stepspec}" "${stepdeps}" ${outvar}
            ;;

        *) # Built-in scheduler will be used
            builtin_scheduler_launch ${file} "${job_array_list}" "${stepspec}" "${stepdeps}" ${outvar}
            ;;
    esac
}

########
launch_step()
{
    # Initialize variables
    local stepname=$1
    local job_array_list=$2
    local stepspec=$3
    local stepdeps=$4
    local opts_array_name=$5
    local jid=$6

    # Create script
    create_script ${tmpdir}/scripts/${stepname} ${stepname} ${opts_array_name} || return 1

    # Launch script
    launch ${tmpdir}/scripts/${stepname} ${job_array_list} "${stepspec}" ${stepdeps} ${jid} || return 1
}

########
get_step_info()
{
    local stepname=$1
    local infofile=$2

    $AWK -v stepname=${stepname} '{if($1==stepname) print $0}' ${infofile}
}

########
pipeline_stepspec_is_comment()
{
    local stepspec=$1
    local fields=( $stepspec )
    if [[ "${fields[0]}" = \#* ]]; then
        echo "yes"
    else
        echo "no"
    fi
}

########
pipeline_stepspec_is_ok()
{
    local stepspec=$1

    local fieldno=1
    local field
    for field in $stepspec; do
        if [[ ${field} = "stepdeps="* ]]; then
            if [ $fieldno -ge 2 ]; then
                echo "yes"
                return 0
            fi
        fi
        fieldno=`expr ${fieldno} + 1`
    done

    echo "no"
}

########
extract_attr_from_stepspec()
{
    local stepspec=$1
    local attrname=$2

    local field
    for field in $stepspec; do
        if [[ "${field}" = "${attrname}="* ]]; then
            local attrname_len=${#attrname}
            local start=`expr ${attrname_len} + 1`
            local attr_val=${field:${start}}
            echo ${attr_val}
            return 0
        fi
    done

    echo ${ATTR_NOT_FOUND}
}

########
extract_stepname_from_stepspec()
{
    local stepspec=$1
    local fields=( $stepspec )
    echo ${fields[0]}
}

########
extract_stepdeps_from_stepspec()
{
    local stepspec=$1
    extract_attr_from_stepspec "${stepspec}" "stepdeps"    
}

########
extract_cpus_from_stepspec()
{
    local stepspec=$1
    extract_attr_from_stepspec "${stepspec}" "cpus"
}

########
get_pipeline_modules()
{
    local pfile=$1
    local modules=`$AWK '{if($1=="#import") {$1=""; printf "%s ",$0}}' $pfile | $AWK '{for(i=1;i<=NF;++i) printf"%s",$i}'` ; pipe_fail || return 1
    echo ${modules}
}


########
search_mod_in_dirs()
{
    local module=$1
    
    # Search module in directories listed in PANPIPE_MOD_DIR
    local prevIFS=$IFS
    IFS=':'
    local dir
    local fullmodname
    for dir in ${PANPIPE_MOD_DIR}; do
        if [ -f ${dir}/${module} ]; then
            fullmodname=${dir}/${module}
            break
        fi
    done
    IFS=${prevIFS}
    
    # Fallback to package bindir
    if [ -z "${fullmodname}" ]; then
        fullmodname=${panpipe_bindir}/${module}
    fi

    echo $fullmodname
}

########
determine_full_module_name()
{
    local module=$1
    local absolute=`is_absolute_path $module`
    if [ $absolute -eq 1 ]; then
        fullmodname=${module}
    else
        fullmodname=`search_mod_in_dirs ${module}`
    fi

    echo $fullmodname
}

########
load_pipeline_module()
{
    local module=$1

    # Determine full module name
    local fullmodname=`determine_full_module_name $module`

    echo "Loading module $module (${fullmodname})..." >&2

    # Check that module file exists
    if [ -f ${fullmodname} ]; then
        . ${fullmodname} || return 1
        # Store module name in associative array
        PIPELINE_MODULES[${fullmodname}]=1        
    else
        echo "File not found (consider setting an appropriate value for PANPIPE_MOD_DIR environment variable)">&2
        return 1
    fi
}

########
load_pipeline_modules()
{
    local pfile=$1

    file_exists $pfile || { echo "Error: file $pfile does not exist" >&2 ; return 1; }
    
    local comma_sep_modules=`get_pipeline_modules $pfile`
    
    if [ -z "${comma_sep_modules}" ]; then
        echo "Error: no pipeline modules were given" >&2
        return 1
    else
        # Load modules
        local prevIFS=$IFS
        IFS=','
        local mod
        for mod in ${comma_sep_modules}; do
            load_pipeline_module $mod || { echo "Error while loading ${mod}" >&2 ; return 1; }
        done
        IFS=${prevIFS}
    fi
}

########
get_pipeline_fullmodnames()
{
    local pfile=$1

    file_exists $pfile || { echo "Error: file $pfile does not exist" >&2 ; return 1; }
    
    local comma_sep_modules=`get_pipeline_modules $pfile`
    
    if [ -z "${comma_sep_modules}" ]; then
        echo "Warning: no pipeline modules were given" >&2
    else
        # Get names
        local fullmodnames
        local prevIFS=$IFS
        IFS=','
        local mod
        for mod in ${comma_sep_modules}; do
            local fullmodname=`determine_full_module_name $mod`
            if [ -z "${fullmodnames}" ]; then
                fullmodnames=${fullmodname}
            else
                fullmodnames="${fullmodnames} ${fullmodname}"
            fi
        done
        IFS=${prevIFS}
        echo "${fullmodnames}"
    fi
}

########
get_default_step_outdir()
{
    local dirname=$1
    local stepname=$2
    echo ${dirname}/${stepname}
}

########
get_step_outdir()
{
    local dirname=$1
    local stepname=$2

    # Get name of step function to set output directory
    step_function_outdir=`get_name_of_step_function_outdir ${stepname}`
    
    if [ ${step_function_outdir} = "${FUNCT_NOT_FOUND}" ]; then
        get_default_step_outdir $dirname $stepname
    else
        outdir_basename=`step_function_outdir`
        echo ${dirname}/${outdir_basename}
    fi
}

########
prepare_outdir_for_step() 
{
    local dirname=$1
    local stepname=$2
    local remove=$3
    local outd=`get_step_outdir ${dirname} ${stepname}`

    if [ -d ${outd} ]; then
        if [ ${remove} -eq 1 ]; then
           echo "Warning: ${stepname} output directory already exists but pipeline was not finished, directory content will be removed">&2
           rm -rf ${outd}/* || { echo "Error! could not clear output directory" >&2; return 1; }
        fi
    else
        mkdir ${outd} || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
reset_scriptdir_for_step() 
{
    local script_filename=$1

    rm -f ${script_filename}.log
    rm -f ${script_filename}.id
    rm -f ${script_filename}_*
}

########
write_step_id_to_file()
{
    local dirname=$1
    local stepname=$2
    local id=$3
    local filename=$dirname/scripts/$stepname.id

    echo $id > $filename
}

########
read_step_id_from_file()
{
    local dirname=$1
    local stepname=$2
    local filename=$dirname/scripts/$stepname.id

    if [ -f $filename ]; then
        cat $filename
    else
        echo ${INVALID_JID}
    fi
}

########
check_if_pid_exists()
{
    local pid=$1

    local pid_exists=1
    kill -0 $pid  > /dev/null 2>&1 || pid_exists=0

    echo ${pid_exists}
}

########
get_slurm_state_code()
{
    local jid
    ${SQUEUE} -j $jid -h -o "%t" 2>/dev/null
}

########
check_if_slurm_jid_exists()
{
    local jid=$1

    # Use squeue to get job status
    local squeue_success=1
    ${SQUEUE} -j $jid > /dev/null 2>&1 || squeue_success=0

    if [ ${squeue_success} -eq 1 ]; then
        # If squeue succeeds, determine if it returns a state code
        local job_state_code=`get_slurm_state_code $jid`
        if [ -z "${job_state_code}" ]; then
            echo 0
        else
            echo 1
        fi
    else
        # Since squeue has failed, the job is not being executed
        echo 0
    fi
    
    echo ${jid_exists}
}

########
check_if_id_exists()
{
    local id=$1

    # Check id depending on the scheduler
    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            check_if_slurm_jid_exists $id
        ;;
        *) # Use built-in scheduler
            check_if_pid_exists $id
        ;;
    esac
}

########
check_step_is_in_progress()
{
    local dirname=$1
    local stepname=$2

    local stepid=`read_step_id_from_file $dirname $stepname`
    local stepid_exists=`check_if_id_exists $stepid`

    if [ ${stepid_exists} -eq 1 ]; then
        return 0
    else
        return 1
    fi
}

########
get_num_substeps_finished()
{
    local script_filename=$1

    echo `$WC -l ${script_filename}.finished | $AWK '{print $1}'`
}

########
get_num_substeps_to_finish()
{
    local script_filename=$1

    echo `$HEAD -1 ${script_filename}.finished | $AWK '{print $NF}'`
}

########
mark_step_as_reexec()
{
    local stepname=$1
    local reason=$2
    
    if [ "${PANPIPE_REEXEC_STEPS[${stepname}]}" = "" ]; then
        PANPIPE_REEXEC_STEPS[${stepname}]=${reason}
    else
        local curr_val=PANPIPE_REEXEC_STEPS[${stepname}]
        PANPIPE_REEXEC_STEPS[${stepname}]="${curr_val},${reason}"
    fi
}

########
get_reexec_steps_as_string()
{
    local result=""
    for stepname in "${!PANPIPE_REEXEC_STEPS[@]}"; do
        if [ "${result}" = "" ]; then
            result=${stepname}
        else
            result="${result},${stepname}"
        fi
    done

    echo ${result}
}

########
check_step_should_be_reexec()
{
    local stepname=$1

    if [ "${PANPIPE_REEXEC_STEPS[${stepname}]}" = "" ]; then
        return 1
    else
        return 0
    fi
}

########
check_step_is_finished()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`

    if [ -f ${script_filename}.finished ]; then
        # Check that all sub-steps are finished
        local num_substeps_finished=`get_num_substeps_finished ${script_filename}`
        local num_substeps=`get_num_substeps_to_finish ${script_filename}`
        if [ ${num_substeps_finished} -eq ${num_substeps} ]; then
            return 0
        else
            return 1
        fi
    else
        return 1
    fi     
}

########
get_step_status()
{
    local dirname=$1
    local stepname=$2
    local stepdirname=`get_step_outdir ${dirname} ${stepname}`

    # Check if output directory was created
    if [ -d ${stepdirname} ]; then
        if check_step_should_be_reexec $stepname; then
            echo "${REEXEC_STEP_STATUS}"
            return ${REEXEC_STEP_STATUS_EXIT_CODE}
        fi
        
        if check_step_is_finished $dirname $stepname; then
            echo "${FINISHED_STEP_STATUS}"
            return ${FINISHED_STEP_STATUS_EXIT_CODE}
        fi
        
        # Determine if step is unfinished or in progress
        if check_step_is_in_progress $dirname $stepname; then
            echo "${INPROGRESS_STEP_STATUS}"
            return ${INPROGRESS_STEP_STATUS_EXIT_CODE}
        fi

        echo "${UNFINISHED_STEP_STATUS}"
        return ${UNFINISHED_STEP_STATUS_EXIT_CODE}
    else
        echo "${TODO_STEP_STATUS}"
        return ${TODO_STEP_STATUS_EXIT_CODE}
    fi
}

########
display_begin_step_message()
{
    echo "Step started at `date`" >&2
}

########
display_end_step_message()
{
    echo "Step finished at `date`" >&2
}

########
errmsg()
{
    local msg=$1
    echo "$msg" >&2
}

########
logmsg()
{
    local msg=$1
    echo "$msg" >&2
}

########
file_exists()
{
    local file=$1
    if [ -f $file ]; then
        return 0
    else
        return 1
    fi
}

########
dir_exists()
{
    local dir=$1
    if [ -d $dir ]; then
        return 0
    else
        return 1
    fi
}

########
signal_step_completion()
{
    # Initialize variables
    local script_filename=$1
    local id=$2
    local total=$3

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    echo "Finished step id: $id ; Total: $total" >> ${script_filename}.finished
}

########
memoize_opts()
{
    shift
    while [ $# -ne 0 ]; do
        # Check if argument is an option
        if [ ${1:0:1} = "-" -o ${1:0:2} = "--"  ]; then
            # Argument is option
            local opt=$1
            shift

            # continue if option was already given
            if [ "${MEMOIZED_OPTS[$opt]}" != "" ]; then
                # If option has a value it is necessary to execute shift
                if [ ${1:0:1} != "-" -a ${1:0:2} != "--"  ]; then
                    shift
                fi
                continue
            fi
            
            if [ $# -ne 0 ]; then
                # Check if next argument is option
                if [ ${1:0:1} = "-" -o ${1:0:2} = "--"  ]; then
                    # Next argument is option
                    MEMOIZED_OPTS[$opt]=${VOID_VALUE}
                else
                    # Next argument is value
                    value=$1
                    MEMOIZED_OPTS[$opt]=$value
                    shift
                fi
            else
                # There are no more arguments
                MEMOIZED_OPTS[$opt]=${VOID_VALUE}
            fi
        else
            echo "Warning: unexpected argument ($1), skipping..." >&2
            shift
        fi
    done
}

########
check_opt_given()
{
    local line=$1
    local opt=$2
    # Convert string to array
    local array
    IFS=' ' read -r -a array <<< $line
    # Scan array
    i=0
    while [ $i -lt ${#array[@]} ]; do
        if [ ${array[$i]} = "${opt}" ]; then
            return 0
        fi
        i=$((i+1))
    done

    # Option not given
    return 1
}

########
check_memoized_opt()
{
    local opt=$1

    # Check if option was not given
    if [ -z "${MEMOIZED_OPTS[$opt]}" ]; then
        return 1
    else
        return 0
    fi
}

########
check_opt_given_memoiz()
{
    local line=$1
    local opt=$2

    if [ "${LAST_PROC_LINE_MEMOPTS}" = "$line" ]; then
        # Given line was previously processed, return memoized result
        check_memoized_opt $opt || return 1
    else
        # Process not memoized line
        memoize_opts $line
        
        # Store processed line
        LAST_PROC_LINE_MEMOPTS="$line"

        # Return result
        check_memoized_opt $opt || return 1
    fi    
}

########
read_opt_value_from_line()
{
    local line=$1
    local opt=$2
    
    # Convert string to array
    local array
    IFS=' ' read -r -a array <<< $line
    # Scan array
    i=0
    while [ $i -lt ${#array[@]} ]; do
        if [ ${array[$i]} = "${opt}" ]; then
            i=$((i+1))
            if [ $i -lt ${#array[@]} ]; then
                echo ${array[$i]}
                return 0
            fi
        fi
        i=$((i+1))
    done

    # Option not given
    echo ${OPT_NOT_FOUND}
    return 1
}

########
read_memoized_opt_value()
{
    local opt=$1

    # Check if option was not given or it had void value
    if [ -z "${MEMOIZED_OPTS[$opt]}" -o "${MEMOIZED_OPTS[$opt]}" = ${VOID_VALUE} ]; then
        echo ${OPT_NOT_FOUND}
        return 1
    else
        echo ${MEMOIZED_OPTS[$opt]}
        return 0
    fi
}

########
read_opt_value_from_line_memoiz()
{
    local line=$1
    local opt=$2

    if [ "${LAST_PROC_LINE_MEMOPTS}" = "$line" ]; then
        # Given line was previously processed, return memoized result
        _OPT_VALUE_=`read_memoized_opt_value $opt` || return 1
    else
        # Process not memoized line
        memoize_opts $line
        
        # Store processed line
        LAST_PROC_LINE_MEMOPTS="$line"

        # Return result
        _OPT_VALUE_=`read_memoized_opt_value $opt` || return 1
    fi
}

########
explain_cmdline_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    PIPELINE_OPT_TYPE[$opt]=$type
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1
}

########
explain_cmdline_opt_wo_value()
{
    local opt=$1
    local desc=$2
    local categ=$3

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${GENERAL_OPT_CATEGORY}
    fi
    
    # Store option in associative arrays
    PIPELINE_OPT_TYPE[$opt]=""
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1
}

########
print_pipeline_opts()
{
    local lineno=0
    
    # Iterate over option categories
    local categ
    for categ in ${!PIPELINE_CATEG_MAP[@]}; do
        if [ ${lineno} -gt 0 ]; then
            echo ""
        fi
        echo "CATEGORY: ${categ}"
        # Iterate over options
        local opt
        for opt in ${!PIPELINE_OPT_TYPE[@]}; do
            # Check if option belongs to current category
            if [ ${PIPELINE_OPT_CATEG[${opt}]} = $categ ]; then
                # Print option
                if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
                    echo "${opt} ${PIPELINE_OPT_DESC[$opt]}"
                else
                    echo "${opt} ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}"
                fi
            fi
        done

        lineno=`expr ${lineno} + 1`
    done
}

########
define_fifo()
{
    local fifoname=$1
    local stepname=$2

    # Check if FIFO was previously defined
    if [ "${PIPELINE_FIFOS[${fifoname}]}" != "" ]; then
        errmsg "Error: FIFO was previously defined (${fifoname})"
        return 1
    else
        # Store name of FIFO in associative array
        PIPELINE_FIFOS[${fifoname}]=${stepname}
    fi
}

########
define_shared_dir()
{
    local shared_dir=$1

    # Store name of shared directory in associative array
    PIPELINE_SHDIRS[${shared_dir}]=1
}

########
define_cmdline_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    # local value
    # value=`read_opt_value_from_line "$cmdline" $opt` || { errmsg "$opt option not found" ; return 1; }
    read_opt_value_from_line_memoiz "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }
    local value=${_OPT_VALUE_}
    
    # Add option
    define_opt $opt $value $varname
}

########
define_cmdline_opt_wo_value()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    check_opt_given "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }

    # Add option
    define_opt_wo_value $opt $varname
}

########
define_cmdline_nonmandatory_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    # local value
    # value=`read_opt_value_from_line "$cmdline" $opt`
    read_opt_value_from_line_memoiz "$cmdline" $opt
    local value=${_OPT_VALUE_}

    if [ $value = ${OPT_NOT_FOUND} ]; then
        value=${default_value}
    fi
    
    # Add option
    define_opt $opt $value $varname    
}

########
define_cmdline_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    # local value
    # value=`read_opt_value_from_line "$cmdline" $opt`
    read_opt_value_from_line_memoiz "$cmdline" $opt
    local value=${_OPT_VALUE_}

    if [ $value != ${OPT_NOT_FOUND} ]; then
        # Add option
        define_opt $opt $value $varname
    fi
}

########
define_cmdline_infile_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    # local value
    # value=`read_opt_value_from_line "$cmdline" $opt` || { errmsg "$opt option not found" ; return 1; }
    read_opt_value_from_line_memoiz "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }
    local value=${_OPT_VALUE_}

    if [ $value != ${NOFILE} ]; then
        # Check if file exists
        file_exists $value || { errmsg "file $value does not exist ($opt option)" ; return 1; }
    fi

    # Absolutize path
    value=`get_absolute_path ${value}`
    
    # Add option
    define_opt $opt $value $varname
}

########
get_step_outdir_given_stepspec()
{
    local stepspec=$1

    # Get full path of output directory
    local outd=${PIPELINE_OUTDIR}

    # Obtain output directory for step
    local stepname=`extract_stepname_from_stepspec ${stepspec}`
    local step_outd=`get_step_outdir ${outd} ${stepname}`

    echo ${step_outd}
}

########
define_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_opt: wrong input parameters"
        return 1
    fi

    if [ -z "${!varname}" ]; then
        eval "${varname}='${opt} ${value}'" || { errmsg "define_opt: execution error" ; return 1; }
    else
        eval "${varname}='${!varname} ${opt} ${value}'" || { errmsg "define_opt: execution error" ; return 1; }
    fi
}

########
define_opt_wo_value()
{
    local opt=$1
    local varname=$2

    # Check parameters
    if [ "${opt}" = "" -o "${varname}" = "" ]; then
        errmsg "define_opt_wo_value: wrong input parameters"
        return 1
    fi

    if [ -z "${!varname}" ]; then
        eval "${varname}='${opt}'" || { errmsg "define_opt_wo_value: execution error" ; return 1; }
    else
        eval "${varname}='${!varname} ${opt}'" || { errmsg "define_opt_wo_value: execution error" ; return 1; }
    fi
}

########
define_infile_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_infile_opt: wrong input parameters"
        return 1
    fi
    
    # Check if file exists
    file_exists "$value" || { errmsg "file $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path ${value}`

    if [ -z "${!varname}" ]; then
        eval "${varname}='${opt} ${value}'" || { errmsg "define_infile_opt: execution error" ; return 1; }
    else
        eval "${varname}='${!varname} ${opt} ${value}'" || { errmsg "define_infile_opt: execution error" ; return 1; }
    fi
}

########
define_indir_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_indir_opt: wrong input parameters"
        return 1
    fi

    # Check if file exists
    dir_exists "$value" || { errmsg "directory $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path ${value}`

    if [ -z "${!varname}" ]; then
        eval "${varname}='${opt} ${value}'" || { errmsg "define_indir_opt: execution error" ; return 1; }
    else
        eval "${varname}='${!varname} ${opt} ${value}'" || { errmsg "define_indir_opt: execution error" ; return 1; }
    fi
}

########
get_shrdirs_func_name()
{
    local absmodname=$1

    local modname=`$BASENAME ${absmodname}`

    echo "${modname}_shared_dirs"
}

########
create_pipeline_shdirs()
{
    # Populate associative array of shared directories for the loaded
    # modules
    local absmodname
    for absmodname in "${!PIPELINE_MODULES[@]}"; do
        shrdirs_func_name=`get_shrdirs_func_name ${absmodname}`
        ${shrdirs_func_name}
    done
    
    # Create shared directories
    local dirname
    for dirname in "${!PIPELINE_SHDIRS[@]}"; do
        absdir=`get_absolute_shdirname $dirname`
        if [ ! -d ${absdir} ]; then
           mkdir ${absdir} || exit 1
        fi
    done
}

########
get_fifos_func_name()
{
    local absmodname=$1

    local modname=`$BASENAME ${absmodname}`

    echo "${modname}_fifos"
}

########
register_pipeline_fifos()
{
    # Populate associative array of FIFOS for the loaded modules
    local absmodname
    for absmodname in "${!PIPELINE_MODULES[@]}"; do
        fifos_func_name=`get_fifos_func_name ${absmodname}`
        ${fifos_func_name}
    done
}

########
prepare_fifos_owned_by_step()
{
    local stepname=$1

    # Obtain name of directory for FIFOS
    local fifodir=`get_absolute_fifoname`

    # Create FIFOS
    local fifoname
    for fifoname in "${!PIPELINE_FIFOS[@]}"; do
        if [ ${PIPELINE_FIFOS[${fifoname}]} = "${stepname}" ]; then         
            rm -f ${fifodir}/${fifoname} || exit 1
            $MKFIFO ${fifodir}/${fifoname} || exit 1
        fi
    done
}

########
get_absolute_shdirname()
{
    local shdirname=$1
    echo ${PIPELINE_OUTDIR}/${shdirname}
}

########
get_absolute_fifoname()
{
    local fifoname=$1
    echo ${PIPELINE_OUTDIR}/.fifos/${fifoname}
}

########
get_absolute_condadir()
{
    echo ${PIPELINE_OUTDIR}/.conda
}

########
clear_opt_list_array()
{
    unset SCRIPT_OPT_LIST_ARRAY
}

########
save_opt_list()
{
    local optlist_varname=$1
    SCRIPT_OPT_LIST_ARRAY+=("${!optlist_varname}")
}

########
cfgfile_to_string()
{
    local cfgfile=$1
    local str=""

    # Check that the cfg file exists
    if [ ! -f ${cfgfile} ]; then
        return 1
    fi

    # Read cfg file line by line
    local line
    local field
    while read line; do
        for field in $line; do
            # Stop processing line when finding a comment
            if [[ $field = \#* ]]; then
                break
            fi

            # Add field to string
            if [ "${str}" = "" ]; then
                str=$field
            else
                str="${str} ${field}"
            fi
        done
    done < ${cfgfile}

    echo ${str}

    return 0
}

########
define_conda_env()
{
    local env_name=$1
    local yml_file=$2

    echo "${env_name} ${yml_file}"
}

########
conda_env_exists()
{
    local envname=$1

    local env_exists=1
    
    conda activate $envname > /dev/null 2>&1 || env_exists=0

    if [ ${env_exists} -eq 1 ]; then
        conda deactivate
        return 0
    else
        return 1
    fi
}

########
conda_env_prepare()
{
    local env_name=$1
    local abs_yml_fname=$2
    local condadir=$3

    local absolute=`is_absolute_path ${env_name}`
    if [ $absolute -eq 1 ]; then
        # Install packages given prefix name
        conda env create -f ${abs_yml_fname} -p ${env_name} > ${condadir}/${env_name}.log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/${env_name}.log file for more information">&2 ; return 1; }
    else    
        # Install packages given environment name
        conda env create -f ${abs_yml_fname} -n ${env_name} > ${condadir}/${env_name}.log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/${env_name}.log file for more information">&2 ; return 1; }
    fi
}

########
get_panpipe_yml_dir()
{
    echo ${panpipe_datadir}/conda_envs
}

########
get_abs_yml_fname()
{
    local yml_fname=$1
    
    # Search module in directories listed in PANPIPE_YML_DIR
    local prevIFS=$IFS
    IFS=':'
    local dir
    local abs_yml_fname
    for dir in ${PANPIPE_YML_DIR}; do
        if [ -f ${dir}/${yml_fname} ]; then
            abs_yml_fname=${dir}/${yml_fname}
            break
        fi
    done
    IFS=${prevIFS}
    
    # Fallback to panpipe yml package
    if [ -z "${abs_yml_fname}" ]; then
        panpipe_yml_dir=`get_panpipe_yml_dir`
        abs_yml_fname=${panpipe_yml_dir}/${yml_fname}
    fi

    echo ${abs_yml_fname}
}
