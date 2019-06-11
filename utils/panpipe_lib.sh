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
VOID_VALUE="_VOID_VALUE_"
GENERAL_OPT_CATEGORY="GENERAL"

# INVALID IDENTIFIERS
INVALID_SID="_INVALID_SID_"
INVALID_JID="_INVALID_JID_"
INVALID_PID="_INVALID_PID_"
INVALID_ARRAY_TID="_INVALID_ARRAY_TID_"

# STEP STATUSES AND EXIT CODES
FINISHED_STEP_STATUS="FINISHED"
FINISHED_STEP_EXIT_CODE=0
INPROGRESS_STEP_STATUS="IN-PROGRESS"
INPROGRESS_STEP_EXIT_CODE=1
UNFINISHED_BUT_RUNNABLE_STEP_STATUS="UNFINISHED_BUT_RUNNABLE"
UNFINISHED_BUT_RUNNABLE_STEP_EXIT_CODE=2
UNFINISHED_STEP_STATUS="UNFINISHED"
UNFINISHED_STEP_EXIT_CODE=3
REEXEC_STEP_STATUS="REEXECUTE"
REEXEC_STEP_EXIT_CODE=4
TODO_STEP_STATUS="TO-DO"
TODO_STEP_EXIT_CODE=5

# REEXEC REASONS
FORCED_REEXEC_REASON="forced"
OUTDATED_CODE_REEXEC_REASON="outdated_code"
DEPS_REEXEC_REASON="dependencies"

# STEP DEPENDENCIES
AFTER_STEPDEP_TYPE="after"
AFTEROK_STEPDEP_TYPE="afterok"
AFTERNOTOK_STEPDEP_TYPE="afternotok"
AFTERANY_STEPDEP_TYPE="afterany"
AFTERCORR_STEPDEP_TYPE="aftercorr"

# STEP STATISTICS
UNKNOWN_ELAPSED_TIME_FOR_STEP="UNKNOWN"

# PIPELINE STATUSES
#
# NOTE: exit code 1 is reserved for general errors when executing
# pipe_status
PIPELINE_FINISHED_EXIT_CODE=0
PIPELINE_IN_PROGRESS_EXIT_CODE=2
PIPELINE_UNFINISHED_EXIT_CODE=3

# PANPIPE STATUS
PANPIPE_SCHEDULER=""
BUILTIN_SCHEDULER="BUILTIN"
SLURM_SCHEDULER="SLURM"

# SLURM-RELATED CONSTANTS
FIRST_SLURM_VERSION_WITH_AFTERCORR="16.05"

# FILE EXTENSIONS
BUILTIN_SCHED_LOG_FEXT="builtin_out"
SLURM_SCHED_LOG_FEXT="slurm_out"
FINISHED_STEP_FEXT="finished"
STEPID_FEXT="id"
ARRAY_TASKID_FEXT="id"

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store help about pipeline options
declare -A PIPELINE_OPT_DESC
declare -A PIPELINE_OPT_TYPE
declare -A PIPELINE_OPT_REQ
declare -A PIPELINE_OPT_CATEG
declare -A PIPELINE_CATEG_MAP
declare -A PIPELINE_OPT_STEP

# Declare associative array to memoize command line options
declare -A MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
declare LAST_PROC_LINE_MEMOPTS=""

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

# Declare general scheduler-related variables
declare PANPIPE_SCHEDULER
declare -A PANPIPE_REEXEC_STEPS
declare PANPIPE_DEFAULT_NODES
declare PANPIPE_DEFAULT_ARRAY_TASK_THROTTLE=1

# Declare SLURM scheduler-related variables
declare AFTERCORR_STEPDEP_TYPE_AVAILABLE_IN_SLURM=0

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
version_to_number()
{
    local ver=$1
    
    echo $ver | ${AWK} -F. '{ printf("%03d%03d%03d\n", $1,$2,$3); }'
}

########
pipe_fail()
{
    # test if there is at least one command to exit with a non-zero status
    local pipestatus=${PIPESTATUS[*]}
    local pipe_status_elem
    for pipe_status_elem in ${pipestatus}; do 
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
    file=$1
    case $file in
        /*) return 0
            ;;
        *) return 1
           ;;
    esac
}

########
get_absolute_path()
{
    local file=$1
    
    # Check if an absolute path was given
    if is_absolute_path $file; then
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
expand_tilde_in_word()
{
    local word=$1

    case "$word" in
        "~/"*) echo "${HOME}/${word#"~/"}"
               ;;
        *) echo $word
           ;;
    esac
}

########
expand_tildes()
{
    local str=$1
    if [ "${str}" != "" ]; then
        local result=""
        for w in $str; do
            w=`expand_tilde_in_word $w`
            if [ "$result" = "" ]; then
                result=$w
            else
                result="${result} ${w}"
            fi
        done
        echo ${result}
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
replace_str_elem_sep_with_blank()
{
    local sep=$1
    local str=$2
    local str_array
    local result

    IFS="$sep" str_array=($str)
    result=${str_array[@]}
    
    echo ${result}
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

        num_elem=$((num_elem + 1))
    done

    echo $result
}

########
func_exists()
{
    local funcname=$1
    
    type ${funcname} >/dev/null 2>&1 || return 1

    return 0
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
replace_tilde_by_homedir()
{
    local file=$1

    if [ ${file:0:1} = "~" ]; then
        echo "$HOME${file:1}"
    else
        echo $file
    fi
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
convert_mem_value_to_mb()
{
    local mem_value=$1

    local len=${#mem_value}
    local len_m_one=$((len - 1))
    local mem_value_suff="${mem_value:${len_m_one}:1}"
    case ${mem_value_suff} in
        "K") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} / 1024 || return 1
             ;;
        "M") echo ${mem_value:0:${len_m_one}}
             ;;
        "G") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} \* 1024 || return 1
             ;;
        "T") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} \* 1024 \* 1024 || return 1
             ;;
        *) echo ${mem_value}
           ;;
    esac
}

########
str_is_natural_number()
{
    local str=$1
    
    case $str in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

########
get_num_words_in_string()
{
    local str=$1
    echo "${str}" | ${WC} -w
}

########
get_first_n_fields_of_str()
{
    local str=$1
    local n_val=$2

    local result
    for field in ${str}; do
        if [ ${n_val} -eq 0 ]; then
            break
        else
            n_val=$((n_val - 1))
        fi
        
        if [ "${result}" = "" ]; then
            result=$field
        else
            result="${result} ${field}"
        fi
    done

    echo $result
}

#######################
# SCHEDULER FUNCTIONS #
#######################

########
set_panpipe_outdir()
{
    local abs_outd=$1

    PIPELINE_OUTDIR=${abs_outd}
}

########
get_slurm_version()
{
    if [ "$SBATCH" = "" ]; then
        echo "0"
    else
        $SBATCH --version | $AWK '{print $2}'
    fi
}

########
slurm_supports_aftercorr_deptype()
{
    local slurm_ver=`get_slurm_version`
    local slurm_ver_num=`version_to_number ${slurm_ver}`
    local slurm_ver_aftercorr_num=`version_to_number ${FIRST_SLURM_VERSION_WITH_AFTERCORR}`
    if [ ${slurm_ver_num} -ge ${slurm_ver_aftercorr_num} ]; then
        return 0
    else
        return 1
    fi
}

########
set_panpipe_scheduler()
{
    local sched=$1

    case $sched in
        ${SLURM_SCHEDULER})
            # Verify SLURM availability
            if [ "$SBATCH" = "" ]; then
                echo "Error: SLURM scheduler is not installed in your system"
                return 1
            fi
            
            PANPIPE_SCHEDULER=${SLURM_SCHEDULER}

            # Verify if aftercorr dependency type is supported by SLURM
            if slurm_supports_aftercorr_deptype; then
                AFTERCORR_STEPDEP_TYPE_AVAILABLE_IN_SLURM=1
            else
                AFTERCORR_STEPDEP_TYPE_AVAILABLE_IN_SLURM=0                
            fi
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
get_task_array_size_for_step()
{
    local cmdline=$1
    local stepspec=$2

    define_opts_for_script "${cmdline}" "${stepspec}" || return 1
    echo ${#SCRIPT_OPT_LIST_ARRAY[@]}
}

########
print_script_header_slurm_sched()
{
    local stepname=$1
    
    echo "PANPIPE_STEP_NAME=${stepname}"
}

########
print_script_body_slurm_sched()
{
    # Initialize variables
    local num_scripts=$1
    local dirname=$2
    local stepname=$3
    local taskidx=$4
    local funct=$5
    local post_funct=$6
    local script_opts=$7

    # Write treatment for task idx
    if [ ${num_scripts} -gt 1 ]; then
        echo "if [ \${SLURM_ARRAY_TASK_ID} -eq $taskidx ]; then"
    fi

    # Write function to be executed
    echo "${funct} ${script_opts}"
    echo "funct_exit_code=\$?"
    echo "if [ \${funct_exit_code} -ne 0 ]; then echo \"Error: execution of \${funct} failed with exit code \${funct_exit_code}\" >&2; else echo \"Function \${funct} successfully executed\" >&2; fi"
    
    # Write post function if it was provided
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        echo "${post_funct} ${script_opts} || { echo \"Error: execution of \${post_funct} failed with exit code \$?\" >&2 ;exit 1; }"
    fi

    # Return if function to execute failed
    echo "if [ \${funct_exit_code} -ne 0 ]; then exit 1; fi" 
        
    # Close if statement
    if [ ${num_scripts} -gt 1 ]; then
        echo "fi" 
    fi
}

########
print_script_foot_slurm_sched()
{
    :
}

########
create_slurm_script()
{
    # Init variables
    local dirname=$1
    local stepname=$2
    local fname=`get_script_filename ${dirname} ${stepname}`
    local funct=`get_name_of_step_function ${stepname}`
    local post_funct=`get_name_of_step_function_post ${stepname}`
    local opts_array_name=$3[@]
    local opts_array=("${!opts_array_name}")
    local num_scripts=${#opts_array[@]}

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > ${fname} || return 1

    # Set SLURM options
    
    echo "#SBATCH --job-name=${funct}" >> ${fname} || return 1
    if [ ${num_scripts} -eq 1 ]; then
        local slurm_log_filename=`get_step_log_filename_slurm ${dirname} ${stepname}`
        echo "#SBATCH --output=${slurm_log_filename}" >> ${fname} || return 1
    else
        local slurm_task_template_log_filename=`get_task_template_log_filename_slurm ${dirname} ${stepname}`
        echo "#SBATCH --output=${slurm_task_template_log_filename}" >> ${fname} || return 1
    fi
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_bashisms >> ${fname} || return 1

    # Print header
    print_script_header_slurm_sched ${stepname} >> ${fname} || return 1

    # Iterate over options array
    local lineno=1
    local script_opts
    for script_opts in "${opts_array[@]}"; do

        print_script_body_slurm_sched ${num_scripts} ${dirname} ${stepname} ${lineno} ${funct} ${post_funct} "${script_opts}" >> ${fname} || return 1

        lineno=$((lineno + 1))
        
    done

    # Print foot
    print_script_foot_slurm_sched >> ${fname} || return 1

    # Give execution permission
    chmod u+x ${fname} || return 1
}

########
create_script()
{
    # Init variables
    local dirname=$1
    local stepname=$2
    local opts_array_name=$3

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            create_slurm_script $dirname $stepname ${opts_array_name}
            ;;
    esac
}

########
archive_script()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`

    # Archive script with date info
    local curr_date=`date '+%Y_%m_%d'`
    cp ${script_filename} ${script_filename}.${curr_date}
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
get_slurm_task_array_opt()
{
    local file=$1
    local task_array_list=$2
    local throttle=$3

    if [ ${throttle} -eq 0 ]; then
        echo "--array=${task_array_list}"
    else
        echo "--array=${task_array_list}%${throttle}"
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
slurm_launch_attempt()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local stepdeps=$6
    local mem_attempt=$7
    local time_attempt=$8

    # Retrieve specification
    local cpus=`extract_attr_from_stepspec "$stepspec" "cpus"`
    local account=`extract_attr_from_stepspec "$stepspec" "account"`
    local partition=`extract_attr_from_stepspec "$stepspec" "partition"`
    local nodes=`extract_attr_from_stepspec "$stepspec" "nodes"`
    local spec_throttle=`extract_attr_from_stepspec "$stepspec" "throttle"`
    local sched_throttle=`get_scheduler_throttle ${spec_throttle}`

    # Define options for sbatch
    local cpus_opt=`get_slurm_cpus_opt ${cpus}`
    local mem_opt=`get_slurm_mem_opt ${mem_attempt}`
    local time_opt=`get_slurm_time_opt ${time_attempt}`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${stepdeps}"`
    if [ ${array_size} -gt 1 ]; then
        local jobarray_opt=`get_slurm_task_array_opt ${file} ${task_array_list} ${sched_throttle}`
    fi

    # Submit job
    local jid
    jid=$($SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} ${file})
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        local command="$SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} ${file}"
        echo "Error while launching attempt job for step ${stepname} (${command})" >&2
        return 1
    fi

    echo $jid
}

########
slurm_get_attempt_deps()
{
    # Initialize variables
    local attempt_jids=$1
    local attempt_deps

    # Iterate of attempt jids
    local attempt_jids_blanks=`replace_str_elem_sep_with_blank "," ${attempt_jids}`
    local attempt_jid
    for attempt_jid in ${attempt_jids_blanks}; do
        if [ "${attempt_deps}" = "" ]; then
            attempt_deps="afternotok:${attempt_jid}"
        else
            attempt_deps="${attempt_deps},afternotok:${attempt_jid}"
        fi
    done

    echo ${attempt_deps}
}

########
slurm_launch_preverif_job()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local attempt_jids=$6

    # Obtain dependencies for attempts
    local attempt_deps=`slurm_get_attempt_deps ${attempt_jids}`
    
    # Retrieve specification
    local account=`extract_attr_from_stepspec "$stepspec" "account"`
    local partition=`extract_attr_from_stepspec "$stepspec" "partition"`
    local nodes=`extract_attr_from_stepspec "$stepspec" "nodes"`

    # Define options
    local cpus_opt=`get_slurm_cpus_opt 1`
    local mem_opt=`get_slurm_mem_opt 16`
    local time_opt=`get_slurm_time_opt 00:01:00`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${attempt_deps}"`
    local preverif_logf=`get_step_log_preverif_filename_slurm ${dirname} ${stepname}`

    # Submit preliminary verification job (the job will fail if all
    # attempts fail)
    local jid
    jid=$($SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} --job-name "${stepname}_preverif" --output ${preverif_logf} --kill-on-invalid-dep=yes --wrap "true")
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        echo "Error while launching preliminary verification job for step ${stepname}" >&2
        return 1
    fi

    echo $jid
}

########
slurm_launch_verif_job()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local preverif_jid=$6

    # Retrieve specification
    local account=`extract_attr_from_stepspec "$stepspec" "account"`
    local partition=`extract_attr_from_stepspec "$stepspec" "partition"`
    local nodes=`extract_attr_from_stepspec "$stepspec" "nodes"`

    # Define options
    local cpus_opt=`get_slurm_cpus_opt 1`
    local mem_opt=`get_slurm_mem_opt 16`
    local time_opt=`get_slurm_time_opt 00:01:00`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local verjob_deps="afternotok:${preverif_jid}"
    local dependency_opt=`get_slurm_dependency_opt "${verjob_deps}"`
    local verif_logf=`get_step_log_verif_filename_slurm ${dirname} ${stepname}`

    # Submit verification job (the job will succeed if preliminary
    # verification job fails)
    local jid
    jid=$($SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} --job-name "${stepname}_verif" --output ${verif_logf} --kill-on-invalid-dep=yes --wrap "true")
    local exit_code=$?
    
    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        echo "Error while launching verification job for step ${stepname}" >&2
        return 1
    fi

    echo $jid
}

########
slurm_launch_signal_compl_job()
{
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local jid=$6

    # Retrieve specification
    local account=`extract_attr_from_stepspec "$stepspec" "account"`
    local partition=`extract_attr_from_stepspec "$stepspec" "partition"`
    local nodes=`extract_attr_from_stepspec "$stepspec" "nodes"`

    # Define options for sbatch
    local cpus_opt=`get_slurm_cpus_opt 1`
    local mem_opt=`get_slurm_mem_opt 16`
    local time_opt=`get_slurm_time_opt 00:01:00`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local signcomp_logf=`get_step_log_signcomp_filename_slurm ${dirname} ${stepname}`
    if [ ${array_size} -gt 1 ]; then
        local jobarray_opt=`get_slurm_task_array_opt ${file} ${task_array_list} 0`
        local scjob_deps="aftercorr:${jid}"
    else
        local scjob_deps="afterok:${jid}"
    fi
    local dependency_opt=`get_slurm_dependency_opt "${scjob_deps}"`

    # Submit signal step completion job
    local sign_step_completion_cmd=`get_signal_step_completion_cmd ${dirname} ${stepname} ${array_size}`
    local jid
    jid=$($SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} --job-name "${stepname}_signcomp" --output ${signcomp_logf} --kill-on-invalid-dep=yes --wrap "${sign_step_completion_cmd}")
    local exit_code=$?
    
    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        echo "Error while launching signal completion job for step ${stepname}" >&2
        return 1
    fi

    echo $jid
}

########
get_num_attempts()
{
    # Initialize variables
    local time=$1
    local mem=$2
    local time_array
    local mem_array
    local sep=","

    # Obtain arrays for time and memory limits
    IFS="$sep" time_array=($time)
    IFS="$sep" mem_array=($mem)

    # Return length of longest array
    if [ ${#time_array[@]} -gt ${#mem_array[@]} ]; then
        echo ${#time_array[@]} 
    else
        echo ${#mem_array[@]} 
    fi
}

########
get_mem_attempt_value()
{
    # Initialize variables
    local mem=$1
    local attempt_no=$2
    local mem_array

    # Obtain array for memory limits
    local sep=","
    IFS="$sep" mem_array=($mem)

    # Return value for attempt
    local array_idx=$(( attempt_no - 1 ))
    local array_len=${#mem_array[@]}
    if [ ${array_idx} -lt  ${array_len} ]; then
        echo ${mem_array[${array_idx}]}
    else
        local last_array_idx=$(( array_len - 1 ))
        echo ${mem_array[${last_array_idx}]]}
    fi
}

########
get_time_attempt_value()
{
    # Initialize variables
    local time=$1
    local attempt_no=$2
    local time_array

    # Obtain array for time limits
    local sep=","
    IFS="$sep" time_array=($time)

    # Return value for attempt
    local array_idx=$(( attempt_no - 1 ))
    local array_len=${#time_array[@]}
    if [ ${array_idx} -lt ${array_len} ]; then
        echo ${time_array[${array_idx}]}
    else
        last_array_idx=$(( array_len - 1 ))
        echo ${time_array[${last_array_idx}]}
    fi
}

########
slurm_launch()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local file=`get_script_filename ${dirname} ${stepname}`
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local stepdeps=$6
    local outvar=$7

    # Launch execution attempts
    local attempt_no=0
    local prev_jid=""
    local attempt_jids=""
    local mem=`extract_attr_from_stepspec "$stepspec" "mem"`
    local time=`extract_attr_from_stepspec "$stepspec" "time"`
    local num_attempts=`get_num_attempts ${time} ${mem}`
    local attempt_no=1
    while [ ${attempt_no} -le ${num_attempts} ]; do
        # Obtain attempt-dependent parameters
        local mem_attempt=`get_mem_attempt_value ${mem} ${attempt_no}`
        local time_attempt=`get_time_attempt_value ${time} ${attempt_no}`
        if [ "${prev_jid}" = "" ]; then
            local attempt_deps="${stepdeps}"
        else
            local attempt_deps="afternotok:${prev_jid}"
        fi

        # Launch attempt
        jid=`slurm_launch_attempt ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" "${attempt_deps}" ${mem_attempt} ${time_attempt}` || return 1

        # Update dependencies of verification job
        if [ "${attempt_jids}" = "" ]; then
            attempt_jids=${jid}
        else
            attempt_jids="${attempt_jids},${jid}"
        fi

        prev_jid=${jid}
        attempt_no=$(( attempt_no + 1 ))
    done

    # If more than one attempt was requested, verify if any of the
    # attempts were successful (currently, verification requires to
    # launch two jobs)
    if [ ${num_attempts} -gt 1 ]; then
        preverif_jid=`slurm_launch_preverif_job ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" ${attempt_jids}` || return 1
        verif_jid=`slurm_launch_verif_job ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" ${preverif_jid}` || return 1
        sc_jid=`slurm_launch_signal_compl_job ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" ${verif_jid}` || return 1
        # Set output value
        eval "${outvar}='${attempt_jids},${preverif_jid},${verif_jid},${sc_jid}'"
    else
        # Only one attempt was requested
        sc_jid=`slurm_launch_signal_compl_job ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" ${jid}` || return 1
        # Set output value
        eval "${outvar}='${jid},${sc_jid}'"
    fi
}

########
launch()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local stepdeps=$6
    local outvar=$7
    
    # Launch step
    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            slurm_launch ${dirname} ${stepname} ${array_size} "${task_array_list}" "${stepspec}" "${stepdeps}" ${outvar} || return 1
            ;;
    esac
}

########
create_script_and_launch()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local array_size=$3
    local task_array_list=$4
    local stepspec=$5
    local stepdeps=$6
    local opts_array_name=$7
    local id=$8

    # Create script for step
    create_script ${dirname} ${stepname} ${opts_array_name} || return 1

    # Launch step
    launch ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" ${stepdeps} ${id} || return 1
}

########
get_launch_outv_primary_id_slurm()
{
    local launch_outvar=$1
    local str_array
    local sep=","
    IFS="$sep" str_array=(${launch_outvar})
    local array_len=${#str_array[@]}
    if [ ${array_len} -eq 2 ]; then
        # launch_outvar only has 2 ids, so only one attempt was executed
        echo ${str_array[0]}
    else
        # launch_outvar only has more than 2 ids, so multiple attempts
        # were executed. In this case, the global id is returned as the
        # primary one
        local last_array_idx=$(( array_len - 1 ))
        echo ${str_array[${last_array_idx}]}
    fi
}

########
get_launch_outv_primary_id()
{
    # Returns the primary id of a step. The primary id is the
    # job/process directly executing the step (additional jobs/processes
    # may be necessary to complete step execution)
    local launch_outvar=$1

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            get_launch_outv_primary_id_slurm ${launch_outvar}
            ;;
    esac
}

########
get_launch_outv_global_id_slurm()
{
    # Initialize variables
    local launch_outvar=$1
    local str_array
    local sep=","
    IFS="$sep" str_array=(${launch_outvar})

    # Return last id stored in launch output variable, which corresponds
    # to the global id
    local array_len=${#str_array[@]}
    local last_array_idx=$(( array_len - 1 ))
    echo ${str_array[${last_array_idx}]}
}

########
get_launch_outv_global_id()
{
    # Returns the global id of a step. The global id is the job/process
    # registering the step as finished. It is only executed when all of
    # the others jobs/processes are completed
    local launch_outvar=$1

        local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            get_launch_outv_global_id_slurm ${launch_outvar}
            ;;
    esac
}

########
pid_exists()
{
    local pid=$1

    kill -0 $pid  > /dev/null 2>&1 || return 1

    return 0
}

########
get_slurm_state_code()
{
    local jid=$1
    ${SQUEUE} -j $jid -h -o "%t" 2>/dev/null
}

########
slurm_jid_exists()
{
    local jid=$1

    # Use squeue to get job status
    local squeue_success=1
    ${SQUEUE} -j $jid > /dev/null 2>&1 || squeue_success=0

    if [ ${squeue_success} -eq 1 ]; then
        # If squeue succeeds, determine if it returns a state code
        local job_state_code=`get_slurm_state_code $jid`
        if [ -z "${job_state_code}" ]; then
            return 1
        else
            return 0
        fi
    else
        # Since squeue has failed, the job is not being executed
        return 1
    fi
}

########
id_exists()
{
    local id=$1

    # Check id depending on the scheduler
    local sched=`determine_scheduler`
    local exit_code
    case $sched in
        ${SLURM_SCHEDULER})
            slurm_jid_exists $id
            exit_code=$?
            return ${exit_code}
            ;;
        ${BUILTIN_SCHEDULER})
            pid_exists $id
            exit_code=$?
            return ${exit_code}
        ;;
    esac
}

########
step_is_in_progress()
{
    local dirname=$1
    local stepname=$2
    local ids=`read_ids_from_files $dirname $stepname`

    # Iterate over ids
    for id in ${ids}; do
        if id_exists $id; then
            return 0
        fi
    done

    return 1
}

########
get_launched_array_task_ids()
{
    local dirname=$1
    local stepname=$2

    # Return ids for array tasks if any
    for taskid_file in ${dirname}/scripts/${stepname}_*.${ARRAY_TASKID_FEXT}; do
        if [ -f ${taskid_file} ]; then
            cat ${taskid_file}
        fi
    done

}

########
get_finished_array_task_indices()
{
    local dirname=$1
    local stepname=$2

    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    if [ -f ${finished_filename} ]; then
        ${AWK} '{print $4}' ${finished_filename}
    fi
}

########
array_task_is_finished()
{
    local dirname=$1
    local stepname=$2
    local idx=$3

    # Check file with finished tasks info exists
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    if [ ! -f ${finished_filename} ]; then
        return 1
    fi
    
    # Check that task is in file
    local task_in_file=1
    ${GREP} "idx: ${idx} ;" ${finished_filename} > /dev/null || task_in_file=0
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
    $WC -l ${finished_filename} | $AWK '{print $1}'
}

########
get_num_array_tasks_from_finished_file()
{
    local finished_filename=$1
    $HEAD -1 ${finished_filename} | $AWK '{print $NF}'
}

########
step_is_finished()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    
    if [ -f ${finished_filename} ]; then
        # Check that all tasks are finished
        local num_array_tasks_finished=`get_num_finished_array_tasks_from_finished_file ${finished_filename}`
        local num_array_tasks_to_finish=`get_num_array_tasks_from_finished_file ${finished_filename}`
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
step_is_unfinished_but_runnable_builtin_sched()
{
    # Steps where the following is true are assigned this status:
    #  - step is an array of tasks
    #  - there are no tasks in progress
    #  - at least one task has been launched
    #  - at least one task can start execution
    
    local dirname=$1
    local stepname=$2

    # Get .id files of finished tasks
    ids=`get_launched_array_task_ids $dirname $stepname`
    local -A launched_array_tids
    for id in ${ids}; do
        launched_array_tids[${id}]=1
    done

    # If no launched array tasks were found, step is not array or it is
    # not an unfinished one
    num_launched_tasks=${#launched_array_tids[@]}
    if [ ${num_launched_tasks} -eq 0 ]; then
        return 1
    else
        # Step is array with some tasks already launched

        # Check that not all array tasks were launched
        local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
        local num_array_tasks_to_finish=`get_num_array_tasks_from_finished_file ${finished_filename}`
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
step_is_unfinished_but_runnable()
{
    local dirname=$1
    local stepname=$2

    # Check status depending on the scheduler
    local sched=`determine_scheduler`
    local exit_code
    case $sched in
        ${SLURM_SCHEDULER})
            # UNFINISHED_BUT_RUNNABLE_STEP_STATUS status is not
            # considered for SLURM scheduler, since task arrays are
            # executed as a single job
            return 1
            ;;
        ${BUILTIN_SCHEDULER})
            step_is_unfinished_but_runnable_builtin_sched ${dirname} ${stepname}
            exit_code=$?
            return ${exit_code}
        ;;
    esac
}

########
get_step_start_date()
{
    log_filename=$1
    if [ -f ${log_filename} ]; then
        ${GREP} "^Step started at " ${log_filename} | ${AWK} '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}

########
get_step_finish_date()
{
    log_filename=$1
    if [ -f ${log_filename} ]; then
        ${GREP} "^Step finished at " ${log_filename} | ${AWK} '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}

########
get_elapsed_time_from_logfile()
{
    local log_filename=$1
    local start_date=`get_step_start_date ${log_filename}`
    local finish_date=`get_step_finish_date ${log_filename}`
    
    # Obtain difference
    if [ ! -z "${start_date}" -a ! -z "${finish_date}" ]; then
        local start_date_secs=`date -d "${finish_date}" +%s`
        local finish_date_secs=`date -d "${start_date}" +%s`
        echo $(( start_date_secs - finish_date_secs ))
    else
        echo ${UNKNOWN_ELAPSED_TIME_FOR_STEP}
    fi
}

########
get_elapsed_time_for_step_slurm()
{
    local dirname=$1
    local stepname=$2

    # Obtain finished filename
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`

    if [ -f ${finished_filename} ]; then
        # Get number of array tasks
        local num_tasks=`get_num_array_tasks_from_finished_file ${finished_filename}`    
    
        # Extract difference time from log files
        if [ ${num_tasks} -eq 1 ]; then
            # Step is not a task array
            log_filename=`get_step_log_filename_slurm ${dirname} ${stepname}`
            local difft=`get_elapsed_time_from_logfile ${log_filename}`
            echo ${difft}
        else
            # Step is a task array
            local result=""
            local taskidx
            for taskidx in `get_finished_array_task_indices ${dirname} ${stepname}`; do
                local log_filename=`get_task_log_filename_slurm ${dirname} ${stepname} ${taskidx}`
                local difft=`get_elapsed_time_from_logfile ${log_filename}`
                if [ ! -z "${result}" ]; then
                    result="${result} "
                fi
                result="${result}${taskidx}->${difft} ;"
            done
            echo ${result}
        fi
    else
        echo ${UNKNOWN_ELAPSED_TIME_FOR_STEP}
    fi    
}

########
get_elapsed_time_for_step_builtin()
{
    local dirname=$1
    local stepname=$2

    # Obtain finished filename
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`

    if [ -f ${finished_filename} ]; then
        # Get number of array tasks
        local num_tasks=`get_num_array_tasks_from_finished_file ${finished_filename}`    
    
        # Extract difference time from log files
        if [ ${num_tasks} -eq 1 ]; then
            # Step is not a task array
            log_filename=`get_step_log_filename_builtin ${dirname} ${stepname}`
            local difft=`get_elapsed_time_from_logfile ${log_filename}`
            echo ${difft}
        else
            # Step is a task array
            local result=""
            local taskidx
            for taskidx in `get_finished_array_task_indices ${dirname} ${stepname}`; do
                local log_filename=`get_task_log_filename_builtin ${dirname} ${stepname} ${taskidx}`
                local difft=`get_elapsed_time_from_logfile ${log_filename}`
                if [ ! -z "${result}" ]; then
                    result="${result} "
                fi
                result="${result}${taskidx}->${difft} ;"
            done
            echo ${result}
        fi
    else
        echo ${UNKNOWN_ELAPSED_TIME_FOR_STEP}
    fi    
}

########
get_elapsed_time_for_step()
{
    local dirname=$1
    local stepname=$2
    
    # Get name of log file
    local sched=`determine_scheduler`
    local log_filename
    case $sched in
        ${SLURM_SCHEDULER})
            get_elapsed_time_for_step_slurm ${dirname} ${stepname}
            ;;
        ${BUILTIN_SCHEDULER})
            get_elapsed_time_for_step_builtin ${dirname} ${stepname}
            ;;
    esac
}

########
get_step_status()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`

    # Check script file for step was created
    if [ -f ${script_filename} ]; then
        if step_should_be_reexec $stepname; then
            echo "${REEXEC_STEP_STATUS}"
            return ${REEXEC_STEP_EXIT_CODE}
        fi

        if step_is_in_progress $dirname $stepname; then
            echo "${INPROGRESS_STEP_STATUS}"
            return ${INPROGRESS_STEP_EXIT_CODE}
        fi

        if step_is_finished $dirname $stepname; then
            echo "${FINISHED_STEP_STATUS}"
            return ${FINISHED_STEP_EXIT_CODE}
        else
            if step_is_unfinished_but_runnable $dirname $stepname; then
                echo "${UNFINISHED_BUT_RUNNABLE_STEP_STATUS}"
                return ${UNFINISHED_BUT_RUNNABLE_STEP_EXIT_CODE}
            fi
        fi
        
        echo "${UNFINISHED_STEP_STATUS}"
        return ${UNFINISHED_STEP_EXIT_CODE}
    else
        echo "${TODO_STEP_STATUS}"
        return ${TODO_STEP_EXIT_CODE}
    fi
}

########
map_deptype_if_necessary_slurm()
{
    local deptype=$1
    case $deptype in
        ${AFTERCORR_STEPDEP_TYPE})
            if [ ${AFTERCORR_STEPDEP_TYPE_AVAILABLE_IN_SLURM} -eq 1 ]; then
                echo ${deptype}
            else
                echo ${AFTEROK_STEPDEP_TYPE}
            fi
            ;;
        *)
            echo $deptype
            ;;
    esac
}

########
map_deptype_if_necessary()
{
    local deptype=$1

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            map_deptype_if_necessary_slurm ${deptype}
            ;;
        *)
            echo ${deptype}
            ;;
    esac
}

############################
# STEP EXECUTION FUNCTIONS #
############################

########
get_script_filename() 
{
    local dirname=$1
    local stepname=$2
    
    echo ${dirname}/scripts/${stepname}
}

########
get_stepid_filename() 
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/$stepname.${STEPID_FEXT}
}

########
get_array_taskid_filename() 
{
    local dirname=$1
    local stepname=$2
    local idx=$3
    
    echo ${dirname}/scripts/${stepname}_${idx}.${ARRAY_TASKID_FEXT}
}

########
get_array_taskid()
{
    local dirname=$1
    local stepname=$2
    local idx=$3

    file=`get_array_taskid_filename ${dirname} ${stepname} ${idx}`
    if [ -f ${file} ]; then
        cat $file
    else
        echo ${INVALID_ARRAY_TID}
    fi
}

########
get_step_finished_filename()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.${FINISHED_STEP_FEXT}
}

########
get_step_log_filename_builtin()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.${BUILTIN_SCHED_LOG_FEXT}
}

########
get_task_log_filename_builtin()
{
    local dirname=$1
    local stepname=$2
    local taskidx=$3
    
    echo ${dirname}/scripts/${stepname}_${taskidx}.${BUILTIN_SCHED_LOG_FEXT}
}

########
get_step_log_filename_slurm()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.${SLURM_SCHED_LOG_FEXT}
}

########
get_step_log_preverif_filename_slurm()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.preverif.${SLURM_SCHED_LOG_FEXT}
}

########
get_step_log_verif_filename_slurm()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.verif.${SLURM_SCHED_LOG_FEXT}
}

########
get_step_log_signcomp_filename_slurm()
{
    local dirname=$1
    local stepname=$2

    echo ${dirname}/scripts/${stepname}.signcomp.${SLURM_SCHED_LOG_FEXT}
}

########
get_task_log_filename_slurm()
{
    local dirname=$1
    local stepname=$2
    local taskidx=$3
    
    echo ${dirname}/scripts/${stepname}_${taskidx}.${SLURM_SCHED_LOG_FEXT}
}

########
get_task_template_log_filename_slurm()
{
    local dirname=$1
    local stepname=$2
    
    echo ${dirname}/scripts/${stepname}_%a.${SLURM_SCHED_LOG_FEXT}
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

    if func_exists ${step_function_post}; then
        echo ${step_function_post}
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

    if func_exists ${step_function_outdir}; then
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
get_stepdeps_separator()
{
    local stepdeps=$1
    if [[ "${stepdeps}" == *","* ]]; then
        echo ","
    else
        if [[ "${stepdeps}" == *"?"* ]]; then
            echo "?"
        else
            echo ""
        fi
    fi
}

########
find_dependency_for_step()
{
    local stepspec=$1
    local stepname_part=$2

    local stepdeps=`extract_stepdeps_from_stepspec "$stepspec"`
    local separator=`get_stepdeps_separator ${stepdeps}`
    if [ "${separator}" = "" ]; then
        local stepdeps_blanks=${stepdeps}
    else
        local stepdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${stepdeps}`
    fi
    local dep
    for dep in ${stepdeps_blanks}; do
        local stepname_part_in_dep=`get_stepname_part_in_dep ${dep}`
        if [ "${stepname_part_in_dep}" = ${stepname_part} ]; then
            echo ${dep}
            return 0
        fi
    done
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
    local separator=`get_stepdeps_separator ${stepids}`
    if [ "${separator}" = "" ]; then
        local stepids_blanks=${stepids}
    else
        local stepids_blanks=`replace_str_elem_sep_with_blank "${separator}" ${stepids}`
    fi
    local id
    for id in ${stepids_blanks}; do
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
    local stepname=$2
    local array_size=$3

    # Create associative map containing completed jobs
    local -A completed_tasks
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    if [ -f ${finished_filename} ]; then
        while read line; do
            local fields=( $line )
            local num_fields=${#fields[@]}
            if [ ${num_fields} -eq 7 ]; then
                local id=${fields[3]}
                completed_tasks[${id}]="1"
            fi
        done < ${finished_filename}
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
    local stepname=$2
    local array_size=$3
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`

    if [ -f ${finished_filename} ]; then
        # Some jobs were completed, return list containing pending ones
        get_list_of_pending_tasks_in_array ${dirname} ${stepname} ${array_size}
    else
        # No jobs were completed, return list containing all of them
        echo "1-${array_size}"
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
task_array_elem_is_range()
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
get_start_idx_in_range()
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
get_end_idx_in_range()
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
    local outd=`get_step_outdir ${dirname} ${stepname}`

    if [ -d ${outd} ]; then
        echo "Warning: ${stepname} output directory already exists but pipeline was not finished or will be re-executed, directory content will be removed">&2
        rm -rf ${outd}/* || { echo "Error! could not clear output directory" >&2; return 1; }
    else
        mkdir ${outd} || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
prepare_outdir_for_step_array() 
{
    local dirname=$1
    local stepname=$2
    local outd=`get_step_outdir ${dirname} ${stepname}`

    if [ ! -d ${outd} ]; then
        mkdir ${outd} || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
update_step_completion_signal()
{
    local dirname=$1
    local stepname=$2
    local status=$3

    # If step will be reexecuted, file signaling step completion
    # should be removed
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    if [ "${status}" = "${REEXEC_STEP_STATUS}" ]; then
        rm -f ${finished_filename}
    fi
}

########
clean_step_log_files_slurm()
{
    local dirname=$1
    local stepname=$2
    local array_size=$3
    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local slurm_log_filename=`get_step_log_filename_slurm ${dirname} ${stepname}`
        rm -f ${slurm_log_filename}
        local slurm_log_preverif=`get_step_log_preverif_filename_slurm ${dirname} ${stepname}`
        rm -f ${slurm_log_preverif}
        local slurm_log_verif=`get_step_log_verif_filename_slurm ${dirname} ${stepname}`
        rm -f ${slurm_log_verif}
        local slurm_log_signcomp=`get_step_log_signcomp_filename_slurm ${dirname} ${stepname}`
        rm -f ${slurm_log_signcomp}
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array ${dirname} ${stepname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local slurm_task_log_filename=`get_task_log_filename_slurm ${dirname} ${stepname} ${idx}`
                rm -f ${slurm_task_log_filename}
            done
        fi
    fi
}

########
clean_step_log_files()
{
    local dirname=$1
    local stepname=$2
    local array_size=$3

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            clean_step_log_files_slurm $dirname $stepname $array_size
            ;;
    esac
}

########
clean_step_id_files()
{
    local dirname=$1
    local stepname=$2
    local array_size=$3
    
    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local stepid_file=`get_stepid_filename ${dirname} ${stepname}`
        rm -f ${stepid_file}
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array ${dirname} ${stepname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local array_taskid_file=`get_array_taskid_filename ${dirname} ${stepname} ${idx}`
                rm -f ${array_taskid_file}
            done
        fi
    fi
}

########
write_step_id_to_file()
{
    local dirname=$1
    local stepname=$2
    local id=$3
    local filename=`get_stepid_filename ${dirname} ${stepname}`

    echo $id > $filename
}

########
read_step_id_from_file()
{
    local dirname=$1
    local stepname=$2

    # Return id for step
    local filename=`get_stepid_filename ${dirname} ${stepname}`
    if [ -f $filename ]; then
        cat $filename
    else
        echo ${INVALID_SID}
    fi
}

########
read_ids_from_files()
{
    local dirname=$1
    local stepname=$2
    local ids
    
    # Return id for step
    local filename=`get_stepid_filename ${dirname} ${stepname}`
    if [ -f $filename ]; then
        ids=`cat $filename`
    fi

    # Return ids for array tasks if any
    local id
    for taskid_file in ${dirname}/scripts/${stepname}_*.${ARRAY_TASKID_FEXT}; do
        if [ -f ${taskid_file} ]; then
            id=`cat ${taskid_file}`
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
step_should_be_reexec()
{
    local stepname=$1

    if [ "${PANPIPE_REEXEC_STEPS[${stepname}]}" = "" ]; then
        return 1
    else
        return 0
    fi
}

########
signal_step_completion()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local idx=$3
    local total=$4

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    local finished_filename=`get_step_finished_filename ${dirname} ${stepname}`
    echo "Finished task idx: $idx ; Total: $total" >> ${finished_filename}
}

########
get_signal_step_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local stepname=$2
    local total=$3

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    if [ ${total} -eq 1 ]; then 
        echo "fname=`get_step_finished_filename ${dirname} ${stepname}`; echo \"Finished task idx: 1 ; Total: $total\" >> \${fname}"
    else
        echo "fname=`get_step_finished_filename ${dirname} ${stepname}`; echo \"Finished task idx: \${SLURM_ARRAY_TASK_ID} ; Total: $total\" >> \${fname}"
    fi
}

########
display_begin_step_message()
{
    echo "Step started at `date +"%D %T"`" >&2
}

########
display_end_step_message()
{
    echo "Step finished at `date +"%D %T"`" >&2
}

################################
# STEP DOCUMENTATION FUNCTIONS #
################################

########
get_document_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_document
}

########
step_description()
{
    local desc=$1
    echo $desc
}

########
document_step_opts()
{
    local opts=$1
    for opt in ${opts}; do
        if [ "${PIPELINE_OPT_REQ[${opt}]}" != "" ]; then
            reqflag=" (required) "
        else
            reqflag=" "
        fi
        # Print option
        if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
            echo "\`${opt}\` ${PIPELINE_OPT_DESC[$opt]}${reqflag}"
        else
            echo "\`${opt}\` ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}${reqflag}"
        fi
        echo ""
    done
}

########
document_step()
{
    local stepname=$1
    local doc_options=$2
    
    # Print header
    echo "# ${stepname}"
    echo ""
    
    # Print body
    echo "## Description"
    local document_funcname=`get_document_funcname ${stepname}`
    ${document_funcname}
    echo ""

    if [ ${doc_options} -eq 1 ]; then
        echo "## Options"
        DIFFERENTIAL_CMDLINE_OPT_STR=""
        local explain_cmdline_opts_funcname=`get_explain_cmdline_opts_funcname ${stepname}`
        ${explain_cmdline_opts_funcname}
        document_step_opts "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    fi
}

###############################
# PPL FILES-RELATED FUNCTIONS #
###############################

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
        fieldno=$((fieldno + 1))
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
            local start=$((attrname_len + 1))
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
extract_mem_from_stepspec()
{
    local stepspec=$1
    extract_attr_from_stepspec "${stepspec}" "mem"
}

############################
# MODULE-RELATED FUNCTIONS #
############################

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
    local PANPIPE_MOD_DIR_BLANKS=`replace_str_elem_sep_with_blank "," ${PANPIPE_MOD_DIR}`
    local dir
    local fullmodname
    for dir in ${PANPIPE_MOD_DIR_BLANKS}; do
        if [ -f ${dir}/${module} ]; then
            fullmodname=${dir}/${module}
            break
        fi
    done
    
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
    if is_absolute_path $file; then
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
        local blank_sep_modules=`replace_str_elem_sep_with_blank "," ${comma_sep_modules}`
        local mod
        for mod in ${blank_sep_modules}; do
            load_pipeline_module $mod || { echo "Error while loading ${mod}" >&2 ; return 1; }
        done
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
        local blank_sep_modules=`replace_str_elem_sep_with_blank "," ${comma_sep_modules}`
        local mod
        for mod in ${blank_sep_modules}; do
            local fullmodname=`determine_full_module_name $mod`
            if [ -z "${fullmodnames}" ]; then
                fullmodnames=${fullmodname}
            else
                fullmodnames="${fullmodnames} ${fullmodname}"
            fi
        done
        echo "${fullmodnames}"
    fi
}

###############################
# OPTION DEFINITION FUNCTIONS #
###############################

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
update_opt_to_step_map()
{
    local stepname=$1
    local opts=$2

    for opt in ${opts}; do
        if [ "${PIPELINE_OPT_STEP[${opt}]}" = "" ]; then
            PIPELINE_OPT_STEP[${opt}]=${stepname}
        else
            PIPELINE_OPT_STEP[${opt}]="${PIPELINE_OPT_STEP[${opt}]} ${stepname}"
        fi
    done
}

########
explain_cmdline_req_opt()
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
    PIPELINE_OPT_REQ[$opt]=1
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
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

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
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

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
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
                # Set value of required option flag
                if [ "${PIPELINE_OPT_REQ[${opt}]}" != "" ]; then
                    reqflag=" (required) "
                else
                    reqflag=" "
                fi
                   
                # Print option
                if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
                    echo "${opt} ${PIPELINE_OPT_DESC[$opt]}${reqflag}[${PIPELINE_OPT_STEP[$opt]}]"
                else
                    echo "${opt} ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}${reqflag}[${PIPELINE_OPT_STEP[$opt]}]"
                fi
            fi
        done

        lineno=$((lineno + 1))
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
    read_opt_value_from_line_memoiz "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }
    local value=${_OPT_VALUE_}

    if [ $value != ${NOFILE} ]; then
        # Check if file exists
        file_exists $value || { errmsg "file $value does not exist ($opt option)" ; return 1; }

        # Absolutize path
        value=`get_absolute_path ${value}`
    fi
    
    # Add option
    define_opt $opt $value $varname
}

########
define_cmdline_infile_nonmand_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt
    local value=${_OPT_VALUE_}

    if [ $value = ${OPT_NOT_FOUND} ]; then
        value=${default_value}
    fi

    if [ $value != ${NOFILE} ]; then
        # Check if file exists
        file_exists $value || { errmsg "file $value does not exist ($opt option)" ; return 1; }
        
        # Absolutize path
        value=`get_absolute_path ${value}`
    fi


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
    file_exists $value || { errmsg "file $value does not exist ($opt option)" ; return 1; }

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
get_shrdirs_funcname()
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
        shrdirs_funcname=`get_shrdirs_funcname ${absmodname}`
        ${shrdirs_funcname}
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
get_fifos_funcname()
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
        fifos_funcname=`get_fifos_funcname ${absmodname}`
        ${fifos_funcname}
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

###########################
# CONDA-RELATED FUNCTIONS #
###########################

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

    if is_absolute_path ${env_name}; then
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
    local PANPIPE_YML_DIR_BLANKS=`replace_str_elem_sep_with_blank "," ${PANPIPE_YML_DIR}`
    local dir
    local abs_yml_fname
    for dir in ${PANPIPE_YML_DIR_BLANKS}; do
        if [ -f ${dir}/${yml_fname} ]; then
            abs_yml_fname=${dir}/${yml_fname}
            break
        fi
    done
    
    # Fallback to panpipe yml package
    if [ -z "${abs_yml_fname}" ]; then
        panpipe_yml_dir=`get_panpipe_yml_dir`
        abs_yml_fname=${panpipe_yml_dir}/${yml_fname}
    fi

    echo ${abs_yml_fname}
}
