# *- bash -*

#############
# CONSTANTS #
#############

NOFILE="_NONE_"
OPT_NOT_FOUND="_OPT_NOT_FOUND_"
DEP_NOT_FOUND="_DEP_NOT_FOUND_"
INVALID_JID="_INVALID_JID_"
INVALID_PID="_INVALID_PID_"
VOID_VALUE="_VOID_VALUE_"
FINISHED_STEP_STATUS="FINISHED"
INPROGRESS_STEP_STATUS="IN-PROGRESS"
UNFINISHED_STEP_STATUS="UNFINISHED"
TODO_STEP_STATUS="TO-DO"
NO_SCHEDULER="NO_SCHEDULER"
SLURM_SCHEDULER="SLURM_SCHEDULER"
ANALYSIS_FINISHED_EXIT_CODE=0
ANALYSIS_IN_PROGRESS_EXIT_CODE=1
ANALYSIS_ONE_OR_MORE_STEPS_IN_PROGRESS_EXIT_CODE=2
ANALYSIS_UNFINISHED_EXIT_CODE=3
AFTER_JOBDEP_TYPE="after"
AFTEROK_JOBDEP_TYPE="afterok"
AFTERNOTOK_JOBDEP_TYPE="afternotok"
AFTERANY_JOBDEP_TYPE="afterany"

####################
# GLOBAL VARIABLES #
####################

# Declare associative array to store exit code for processes
declare -A EXIT_CODE

# Declare associative arrays to store help about pipeline options
declare -A PIPELINE_OPT_DESC
declare -A PIPELINE_OPT_TYPE

# Declare associative arrays to store names of directories
declare -A PIPELINE_STEPDIRS
declare -A PIPELINE_SHDIRS

# Declare associative array to memoize command line options
declare -A MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
LAST_PROC_LINE_MEMOPTS=""

# Declare array used to save option lists for scripts
declare -a SCRIPT_OPT_LIST_ARRAY

#####################
# GENERAL FUNCTIONS #
#####################

pipe_fail()
{
    # test if there is at least one command to exit with a non-zero status
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
    local -n str_array=$1
    local sep=$2
    local max_elems=$3
    local result=""
    local num_elem=0
    
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
determine_scheduler()
{
    if [ ${DISABLE_SCHEDULERS} = "yes" ]; then
        echo ${NO_SCHEDULER}
    else
        if [ -z "${SBATCH}" ]; then
            echo ${NO_SCHEDULER}
        else
            echo ${SLURM_SCHEDULER}
        fi
    fi
}

########
create_no_scheduler_script()
{
    # Init variables
    local name=$1
    local command=$2
    local -n opts_array=$3

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > ${name} || return 1
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_bashisms >> ${name} || return 1

    # Iterate over options array
    local lineno=1
    local num_scripts=${#opts_array[@]}
    for script_opts in "${opts_array[@]}"; do
        # Write command to be executed
        echo "${command} ${script_opts} || exit 1" >> ${name} || return 1

        # Write command to signal step completion
        echo "signal_step_completion ${name} ${lineno} ${num_scripts}" >> ${name} || return 1

        lineno=`expr $lineno + 1`
    done
    
    # Give execution permission
    chmod u+x ${name} || return 1
}

########
create_slurm_script()
{
    # Init variables
    local name=$1
    local command=$2
    local -n opts_array=$3
    local num_scripts=${#opts_array[@]}

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo ${BASH_SHEBANG} > ${name} || return 1

    # Set SLURM options
    echo "#SBATCH --job-name=${command}" >> ${name} || return 1
    if [ ${num_scripts} -eq 1 ]; then
        echo "#SBATCH --output=${name}.slurm_out" >> ${name} || return 1
    else
        echo "#SBATCH --output=${name}_%a.slurm_out" >> ${name} || return 1
    fi
    
    # Write environment variables
    set | exclude_readonly_vars | exclude_bashisms >> ${name} || return 1

    # Iterate over options array
    local lineno=1
    for script_opts in "${opts_array[@]}"; do
        # Write treatment for task id
        if [ ${num_scripts} -gt 1 ]; then
            echo "if [ \${SLURM_ARRAY_TASK_ID} -eq $lineno ]; then" >> ${name} || return 1
        fi
        
        # Write command to be executed
        echo "${command} ${script_opts} || exit 1" >> ${name} || return 1

        # Write command to signal step completion
        echo "signal_step_completion ${name} ${lineno} ${num_scripts}" >> ${name} || return 1

        # Close if statement
        if [ ${num_scripts} -gt 1 ]; then
            echo "fi" >> ${name} || return 1
        fi

        lineno=`expr $lineno + 1`
    done
    
    # Give execution permission
    chmod u+x ${name} || return 1
}

########
create_script()
{
    # Init variables
    local name=$1
    local command=$2
    local opts_array=$3

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            create_slurm_script $name $command ${opts_array}
            ;;
        ${NO_SCHEDULER})
            create_no_scheduler_script $name $command ${opts_array}
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
get_account_opt()
{
    local account=$1

    if [ -z "${account}" ]; then
        echo ""
    else
        echo "-A ${account}"
    fi
}

########
get_partition_opt()
{
    local partition=$1

    if [ -z "${partition}" ]; then
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
get_step_function()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`
    
    echo "${stepname_wo_suffix}"
}

########
get_script_explain_cmdline_opts_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_explain_cmdline_opts
}

########
get_script_define_opts_funcname()
{
    local stepname=$1

    local stepname_wo_suffix=`remove_suffix_from_stepname ${stepname}`

    echo ${stepname_wo_suffix}_define_opts
}

########
define_opts_for_script()
{
    local cmdline=$1
    local jobspec=$2
    local stepname=`extract_stepname_from_jobspec "$jobspec"`
    
    clear_opt_list_array
    local script_define_opts_funcname=`get_script_define_opts_funcname ${stepname}`
    ${script_define_opts_funcname} "${cmdline}" "${jobspec}" || return 1
}

########
find_dependency_for_step()
{
    local jobspec=$1
    local stepname_part=$2

    jobdeps=`extract_jobdeps_from_jobspec "$jobspec"`
    local prevIFS=$IFS
    IFS=','
    for local_dep in ${jobdeps}; do
        local stepname_part_in_dep=`get_stepname_part_in_dep ${local_dep}`
        if [ ${stepname_part_in_dep} = ${stepname_part} ]; then
            echo ${local_dep}
            IFS=${prevIFS}
            return 0
        fi
    done
    IFS=${prevIFS}
    echo ${DEP_NOT_FOUND}
    return 1
}

########
get_default_outd_for_dep()
{
    local cmdline=$1
    local dep=$2

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        read_opt_value_from_line_memoiz "$cmdline" "-o" || return 1
        local outd=${_OPT_VALUE_}

        # Get stepname
        local stepname_part=`echo ${dep} | $AWK -F ":" '{print $2}'`
        
        get_step_dirname ${outd} ${stepname_part}
    fi
}

########
apply_deptype_to_jobids()
{
    # Initialize variables
    local jids=$1
    local deptype=$2

    # Apply deptype
    local result=""
    local prevIFS=$IFS
    IFS=','
    for local_jid in ${jids}; do
        if [ -z "" ]; then
            result=${deptype}:${local_jid}
        else
            result=${result}","${deptype}:${local_jid}
        fi
    done
    IFS=${prevIFS}

    echo $result
}

########
get_slurm_dependency_opt()
{
    local jobdeps=$1

    # Create dependency option
    if [ -z "${jobdeps}" ]; then
        echo ""
    else
        echo "--dependency=${jobdeps}"
    fi
}

########
get_slurm_job_array_opt()
{
    local array_size=$1

    if [ ${array_size} -eq 1 ]; then
        echo ""
    else
        echo "--array=1-${array_size}"
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
    echo ${dep} | $AWK -F ":" '{print $2}'
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
wait_for_deps_no_scheduler()
{
    # Initialize variables
    local jobdeps=$1

    # Iterate over dependencies
    local prevIFS=$IFS
    IFS=','
    for local_dep in ${jobdeps}; do
        # Extract information from dependency
        local deptype=`get_deptype_part_in_dep ${local_dep}`
        local pid=`get_id_part_in_dep ${local_dep}`

        # Wait for process to finish (except for "after" dependency
        # types)
        if [ ${deptype} != ${AFTER_JOBDEP_TYPE} ]; then
            get_exit_code $pid _exit_code
            local exit_code=${_exit_code}
            
            # Process exit code
            case ${deptype} in
                ${AFTEROK_JOBDEP_TYPE})
                    if [ ${exit_code} -ne 0 ]; then
                        return 1
                        IFS=${prevIFS}
                    fi
                ;;
                ${AFTERNOTOK_JOBDEP_TYPE})
                    if [ ${exit_code} -eq 0 ]; then
                        return 1
                        IFS=${prevIFS}
                    fi 
                ;;
                ${AFTERANY_JOBDEP_TYPE})
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
no_scheduler_launch()
{
    # Initialize variables
    local file=$1
    local jobdeps=$2
    local outvar=$3

    if wait_for_deps_no_scheduler "${jobdeps}"; then
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
    local array_size=$2
    local jobspec=$3
    local jobdeps=$4
    local outvar=$5

    # Retrieve specification
    local account=`extract_account_from_jobspec "$jobspec"`
    local partition=`extract_partition_from_jobspec "$jobspec"`
    local cpus=`extract_cpus_from_jobspec "$jobspec"`
    local mem=`extract_mem_from_jobspec "$jobspec"`
    local time=`extract_time_from_jobspec "$jobspec"`

    # Define options for sbatch
    local account_opt=`get_account_opt ${account}`
    local partition_opt=`get_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${jobdeps}"`
    local jobarray_opt=`get_slurm_job_array_opt ${array_size}`
    
    # Submit job
    local jid=$($SBATCH --cpus-per-task=${cpus} --mem=${mem} --time ${time} --parsable ${account_opt} ${partition_opt} ${dependency_opt} ${jobarray_opt} ${file})
    
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
    local array_size=$2
    local jobspec=$3
    local jobdeps=$4
    local outvar=$5
    
    # Launch file
    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            slurm_launch ${file} ${array_size} "${jobspec}" "${jobdeps}" ${outvar}
            ;;

        *) # No scheduler will be used
            no_scheduler_launch ${file} "${jobdeps}" ${outvar}
            ;;
    esac
}

########
launch_step()
{
    # Initialize variables
    local stepname=$1
    local jobspec=$2
    local jobdeps=$3
    local opts_array=$4
    local jid=$5

    # Create script
    create_script ${tmpdir}/scripts/${stepname} ${stepname} ${opts_array} || return 1

    # Launch script
    launch ${tmpdir}/scripts/${stepname} "${jobspec}" ${jobdeps} ${jid} || return 1
}

########
get_step_info()
{
    local stepname=$1
    local infofile=$2

    $AWK -v stepname=${stepname} '{if($1==stepname) print $0}' ${infofile}
}

########
analysis_jobspec_is_comment()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{if(index($1,"#")==1) print"yes\n"; else print"no\n"}'
}

########
analysis_jobspec_is_ok()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{if(NF>=4) print"yes\n"; else print"no\n"}'
}

########
extract_stepname_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $1}'
}

########
extract_account_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $2}'
}

########
extract_partition_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $3}'
}

########
extract_cpus_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $4}'
}

########
extract_mem_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $5}'
}

########
extract_time_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print $6}'
}

########
extract_jobdeps_from_jobspec()
{
    local jobspec=$1
    echo "${jobspec}" | $AWK '{print substr($7,9)}'
}

########
get_pipeline_modules()
{
    local afile=$1
    local modules=`$AWK '{if($1=="#import") {$1=""; printf "%s ",$0}}' $afile | $AWK '{for(i=1;i<=NF;++i) printf"%s",$i}'`
    echo ${modules}
}

########
determine_full_module_name()
{
    local module=$1
    local absolute=`is_absolute_path $module`
    if [ $absolute -eq 1 ]; then
        fullmodname=${module}
    else
        fullmodname=${bindir}${module}
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
    else
        return 1
    fi
}

########
load_pipeline_modules()
{
    local afile=$1

    file_exists $afile || { echo "Error: file $afile does not exist" >&2 ; return 1; }
    
    local comma_sep_modules=`get_pipeline_modules $afile`
    
    if [ -z "${comma_sep_modules}" ]; then
        echo "Error: no pipeline modules were given" >&2
        return 1
    else
        # Load modules
        prevIFS=$IFS
        IFS=','
        for mod in ${comma_sep_modules}; do
            load_pipeline_module $mod || { echo "Error while loading ${fullmodname}" >&2 ; return 1; }
        done
        IFS=${prevIFS}
    fi
}

########
get_pipeline_fullmodnames()
{
    local afile=$1

    file_exists $afile || { echo "Error: file $afile does not exist" >&2 ; return 1; }
    
    local comma_sep_modules=`get_pipeline_modules $afile`
    
    if [ -z "${comma_sep_modules}" ]; then
        echo "Warning: no pipeline modules were given" >&2
    else
        # Get names
        local fullmodnames
        local prevIFS=$IFS
        IFS=','
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
get_default_step_dirname()
{
    local dirname=$1
    local stepname=$2
    echo ${dirname}/${stepname}
}

########
get_step_dirname()
{
    local dirname=$1
    local stepname=$2

    if [ -z "${PIPELINE_STEPDIRS[${stepname}]}" ]; then
        echo "Warning! directory for step ${stepname} not defined, assuming default name" >&2
        get_default_step_dirname $dirname $stepname
    else
        echo ${PIPELINE_STEPDIRS[${stepname}]}
    fi
}

########
reset_outdir_for_step() 
{
    local dirname=$1
    local stepname=$2
    local outd=`get_step_dirname ${dirname} ${stepname}`

    if [ -d ${outd} ]; then
        echo "Warning: ${stepname} output directory already exists but analysis was not finished, directory content will be removed">&2
        rm -rf ${outd}/* || { echo "Error! could not clear output directory" >&2; return 1; }
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
    rm -f ${script_filename}.finished
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
check_if_slurm_jid_exists()
{
    local jid=$1
    
    local jid_exists=1
#    ${SQUEUE} -j $jid -h -o %t || jid_exists=0
    ${SQUEUE} -j $jid > /dev/null 2>&1 || jid_exists=0

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
        *) # No scheduler is being used
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
        echo 1
    else
        echo 0
    fi
}

########
get_num_jobs_finished()
{
    local script_filename=$1

    echo `$WC -l ${script_filename}.finished | $AWK '{print $1}'`
}

########
get_num_jobs_to_finish()
{
    local script_filename=$1

    echo `$HEAD -1 ${script_filename}.finished | $AWK '{print $NF}'`
}

########
check_step_is_finished()
{
    local dirname=$1
    local stepname=$2
    local script_filename=`get_script_filename ${dirname} ${stepname}`

    if [ -f ${script_filename}.finished ]; then
        # Check that all jobs are finished
        local num_jobs_finished=`get_num_jobs_finished ${script_filename}`
        local num_jobs=`get_num_jobs_to_finish ${script_filename}`
        if [ ${num_jobs_finished} -eq ${num_jobs} ]; then
            echo 1
        else
            echo 0
        fi
    else
        echo 0
    fi     
}

########
get_step_status()
{
    local dirname=$1
    local stepname=$2
    local stepdirname=`get_step_dirname ${dirname} ${stepname}`
    
    if [ -d ${stepdirname} ]; then
        step_is_finished=`check_step_is_finished $dirname $stepname`
        if [ ${step_is_finished} -eq 1 ]; then
            echo "${FINISHED_STEP_STATUS}"
        else
            # Determine if step is unfinished or in progress
            local step_is_in_progress=`check_step_is_in_progress $dirname $stepname`
            if [ ${step_is_in_progress} -eq 1 ]; then
                echo "${INPROGRESS_STEP_STATUS}"
            else
                echo "${UNFINISHED_STEP_STATUS}"
            fi
        fi
    else
        echo "${TODO_STEP_STATUS}"
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

    # Store option in associative array
    PIPELINE_OPT_TYPE[$opt]=$type
    PIPELINE_OPT_DESC[$opt]=$desc
}

########
explain_cmdline_opt_wo_value()
{
    local opt=$1
    local desc=$2

    # Store option in associative array
    PIPELINE_OPT_TYPE[$opt]=""
    PIPELINE_OPT_DESC[$opt]=$desc
}

########
print_pipeline_opts()
{
    for opt in ${!PIPELINE_OPT_TYPE[@]}; do
        if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
            echo "${opt} ${PIPELINE_OPT_DESC[$opt]}"
        else
            echo "${opt} ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}"
        fi
    done
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
define_cmdline_opt_shdir()
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

    # Store shared directory name in associative array
    PIPELINE_SHDIRS["-$opt"]=$value
}

########
define_cmdline_nonmandatory_opt_shdir()
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

    # Store shared directory name in associative array
    PIPELINE_SHDIRS["-$opt"]=$value
}

########
define_step_outd_opt()
{
    local stepname=$1
    local step_outd=$2
    local varname=$3

    # Add option
    define_opt "-step-outd" ${step_outd} $varname

    # Store directory name for step in associative array
    PIPELINE_STEPDIRS[${stepname}]=${step_outd}
}

########
define_default_step_outd_opt()
{
    local cmdline=$1
    local jobspec=$2
    local varname=$3

    # Get full path of directory
    # local outd
    # outd=`read_opt_value_from_line "$cmdline" "-o"` || return 1
    read_opt_value_from_line_memoiz "$cmdline" "-o" || return 1
    local outd=${_OPT_VALUE_}

    outd=`get_absolute_path ${outd}`
    local stepname=`extract_stepname_from_jobspec ${jobspec}`
    local step_outd=`get_default_step_dirname ${outd} ${stepname}`

    # Add option
    define_step_outd_opt ${stepname} ${step_outd} ${varname}
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
create_pipeline_shdirs()
{
    local outd=$1
    
    for dirname in "${PIPELINE_SHDIRS[@]}"; do
        absdir=`get_absolute_shdirname $outd $dirname`
        if [ ! -d ${absdir} ]; then
           mkdir ${absdir} || exit 1
        fi
    done
}

########
get_absolute_shdirname()
{
    local outd=$1
    local shdirname=$2
    echo ${outd}/${shdirname}
}

########
get_default_shdirname()
{
    local cmdline=$1
    local shdiropt=$2

    # Get full path of directory
    read_opt_value_from_line_memoiz "$cmdline" "-o" || return 1
    local outd=${_OPT_VALUE_}
    outd=`get_absolute_path ${outd}`

    # Get name of shared dir
    read_opt_value_from_line_memoiz "$cmdline" "${shdiropt}" || return 1
    local shdir=${_OPT_VALUE_}

    get_absolute_shdirname $outd $shdir
}

########
get_default_nonmandatory_opt_shdirname()
{
    local cmdline=$1
    local shdiropt=$2
    local default_value=$3

    # Get full path of directory
    read_opt_value_from_line_memoiz "$cmdline" "-o" || return 1
    local outd=${_OPT_VALUE_}
    outd=`get_absolute_path ${outd}`

    # Get name of shared dir
    if read_opt_value_from_line_memoiz "$cmdline" "${shdiropt}"; then
        local shdir=${_OPT_VALUE_}
        get_absolute_shdirname $outd $shdir
    else
        get_absolute_shdirname $outd ${default_value}
    fi
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
