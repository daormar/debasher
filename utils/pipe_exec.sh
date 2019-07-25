# *- bash -*

# INCLUDE BASH LIBRARIES
. ${panpipe_bindir}/panpipe_lib || exit 1
. ${panpipe_bindir}/panpipe_builtin_sched_lib || exit 1

#############
# CONSTANTS #
#############

# MISC. CONSTANTS
LOCKFD=99
MAX_NUM_SCRIPT_OPTS_TO_DISPLAY=10

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store step ids
declare -A PIPE_EXEC_STEP_IDS

#############################
# OPTION HANDLING FUNCTIONS #
#############################

########
print_desc()
{
    echo "pipe_exec executes general purpose pipelines"
    echo "type \"pipe_exec --help\" to get usage information"
}

########
usage()
{
    echo "pipe_exec                 --pfile <string> --outdir <string> [--sched <string>]"
    echo "                          [--builtinsched-cpus <int>] [--builtinsched-mem <int>]"
    echo "                          [--dflt-nodes <string>] [--dflt-throttle <string>]"
    echo "                          [--cfgfile <string>] [--reexec-outdated-steps]"
    echo "                          [--conda-support] [--showopts|--checkopts|--debug]"
    echo "                          [--builtinsched-debug] [--version] [--help]"
    echo ""
    echo "--pfile <string>          File with pipeline steps to be performed (see manual"
    echo "                          for additional information)"
    echo "--outdir <string>         Output directory"
    echo "--sched <string>          Scheduler used to execute the pipeline (if not given,"
    echo "                          it is determined using information gathered during"
    echo "                          package configuration)"
    echo "--builtinsched-cpus <int> Available CPUs for built-in scheduler (${BUILTIN_SCHED_CPUS} by default)."
    echo "                          A value of zero means unlimited CPUs"
    echo "--builtinsched-mem <int>  Available memory in MB for built-in scheduler"
    echo "                          (${BUILTIN_SCHED_MEM} by default). A value of zero"
    echo "                          means unlimited memory"
    echo "--dflt-nodes <string>     Default set of nodes used to execute the pipeline"
    echo "--dflt-throttle <string>  Default task throttle used when executing job arrays"
    echo "--cfgfile <string>        File with options (options provided in command line"
    echo "                          overwrite those given in the configuration file)"
    echo "--reexec-outdated-steps   Reexecute those steps with outdated code"
    echo "--conda-support           Enable conda support"
    echo "--showopts                Show pipeline options"
    echo "--checkopts               Check pipeline options"
    echo "--debug                   Do everything except launching pipeline steps"
    echo "--builtinsched-debug      Show debug information for built-in scheduler"
    echo "--version                 Display version information and exit"
    echo "--help                    Display this help and exit"
}

########
save_command_line()
{
    input_pars="$*"
    command_name=$0
}

########
read_pars()
{
    pfile_given=0
    outdir_given=0
    sched_given=0
    builtinsched_cpus_given=0    
    builtinsched_mem_given=0
    dflt_nodes_given=0
    dflt_throttle_given=0
    cfgfile_given=0
    reexec_outdated_steps_given=0
    conda_support_given=0
    showopts_given=0
    checkopts_given=0
    debug=0
    builtinsched_debug=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--version") panpipe_version
                         exit 1
                         ;;
            "--pfile") shift
                  if [ $# -ne 0 ]; then
                      pfile=$1
                      pfile_given=1
                  fi
                  ;;
            "--outdir") shift
                  if [ $# -ne 0 ]; then
                      outd=$1
                      outdir_given=1
                  fi
                  ;;
            "--sched") shift
                  if [ $# -ne 0 ]; then
                      sched_opt=$1
                      sched_given=1
                  fi
                  ;;
            "--builtinsched-cpus") shift
                  if [ $# -ne 0 ]; then
                      builtinsched_cpus=$1
                      if ! str_is_natural_number ${builtinsched_cpus}; then
                          echo "Value for --builtinsched_cpus option should be a natural number" >&2
                          return 1
                      fi
                      builtinsched_cpus_given=1
                  fi
                  ;;
            "--builtinsched-mem") shift
                  if [ $# -ne 0 ]; then
                      builtinsched_mem=$1
                      builtinsched_mem=`convert_mem_value_to_mb ${builtinsched_mem}` || { echo "Invalid memory specification for --builtinsched_mem option}" >&2; return 1; }
                      if ! str_is_natural_number ${builtinsched_mem}; then
                          echo "Value for --builtinsched_mem option should be a natural number" >&2
                          return 1
                      fi
                      builtinsched_mem_given=1
                  fi
                  ;;
            "--dflt-nodes") shift
                  if [ $# -ne 0 ]; then
                      dflt_nodes=$1
                      dflt_nodes_given=1
                  fi
                  ;;
            "--dflt-throttle") shift
                  if [ $# -ne 0 ]; then
                      dflt_throttle=$1
                      dflt_throttle_given=1
                  fi
                  ;;
            "--cfgfile") shift
                  if [ $# -ne 0 ]; then
                      cfgfile=$1
                      cfgfile_given=1
                  fi
                  ;;
            "--reexec-outdated-steps")
                  if [ $# -ne 0 ]; then
                      reexec_outdated_steps_given=1
                  fi
                  ;;
            "--conda-support")
                  if [ $# -ne 0 ]; then
                      conda_support_given=1
                  fi
                  ;;
            "--showopts") showopts_given=1
                          ;;
            "--checkopts") checkopts_given=1
                           ;;
            "--debug") debug=1
                       ;;
            "--builtinsched-debug") builtinsched_debug=1
                                    ;;
        esac
        shift
    done   
}

########
check_pars()
{
    if [ ${pfile_given} -eq 0 ]; then   
        echo "Error! --pfile parameter not given!" >&2
        exit 1
    else
        if [ ! -f ${pfile} ]; then
            echo "Error! file ${pfile} does not exist" >&2
            exit 1
        fi
    fi
    
    if [ ${outdir_given} -eq 0 ]; then
        echo "Error! --outdir parameter not given!" >&2
        exit 1
    else
        if [ -d ${outd} ]; then
            echo "Warning! output directory does exist" >&2 
        fi
    fi

    if [ ${cfgfile_given} -eq 1 ]; then
        if [ ! -f ${cfgfile} ]; then
            echo "Error: ${cfgfile} file does not exist" >&2
            exit 1
        fi
    fi

    if [ ${showopts_given} -eq 1 -a ${checkopts_given} -eq 1 ]; then
        echo "Error! --showopts and --checkopts options cannot be given simultaneously"
        exit 1
    fi

    if [ ${showopts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --showopts and --debug options cannot be given simultaneously"
        exit 1
    fi

    if [ ${checkopts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --checkopts and --debug options cannot be given simultaneously"
        exit 1
    fi
}

########
absolutize_file_paths()
{
    if [ ${pfile_given} -eq 1 ]; then   
        pfile=`get_absolute_path ${pfile}`
    fi

    if [ ${outdir_given} -eq 1 ]; then   
        outd=`get_absolute_path ${outd}`
    fi

    if [ ${cfgfile_given} -eq 1 ]; then   
        cfgfile=`get_absolute_path ${cfgfile}`
    fi
}

####################################
# GENERAL PIPE EXECUTION FUNCTIONS #
####################################

########
check_pipeline_file()
{
    echo "* Checking pipeline file ($pfile)..." >&2

    ${panpipe_bindir}/pipe_check -p ${pfile} || return 1

    echo "" >&2
}

########
reorder_pipeline_file()
{
    echo "* Obtaining reordered pipeline file ($pfile)..." >&2

    ${panpipe_bindir}/pipe_check -p ${pfile} -r 2> /dev/null || return 1

    echo "" >&2
}

########
gen_stepdeps()
{
    echo "* Generating step dependencies information ($pfile)..." >&2

    ${panpipe_bindir}/pipe_check -p ${pfile} -d 2> /dev/null || return 1

    echo "" >&2
}

########
configure_scheduler()
{
    echo "* Configuring scheduler..." >&2
    echo "" >&2

    if [ ${sched_given} -eq 1 ]; then
        echo "** Setting scheduler type from value of \"--sched\" option..." >&2
        set_panpipe_scheduler ${sched_opt} || return 1
        echo "scheduler: ${sched_opt}" >&2
        echo "" >&2
    else
        # If --sched option not given, scheduler is not set. As a
        # result, it is determined based on information gathered during
        # package configuration (see determine_scheduler function in
        # panpipe_lib.sh)
        :
    fi

    if [ ${dflt_nodes_given} -eq 1 ]; then
        echo "** Setting default nodes for pipeline execution... (${dflt_nodes})" >&2
        set_panpipe_default_nodes ${dflt_nodes} || return 1
        echo "" >&2
    fi

    if [ ${dflt_throttle_given} -eq 1 ]; then
        echo "** Setting default job array task throttle... (${dflt_throttle})" >&2
        set_panpipe_default_array_task_throttle ${dflt_throttle} || return 1
        echo "" >&2
    fi
}

########
load_modules()
{
    echo "* Loading pipeline modules..." >&2

    local pfile=$1
    
    load_pipeline_modules ${pfile} || return 1

    echo "" >&2
}

########
show_pipeline_opts()
{
    echo "* Pipeline options..." >&2

    # Read input parameters
    local pfile=$1

    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            local explain_cmdline_opts_funcname=`get_explain_cmdline_opts_funcname ${stepname}`
            DIFFERENTIAL_CMDLINE_OPT_STR=""
            ${explain_cmdline_opts_funcname} || exit 1
            update_opt_to_step_map ${stepname} "${DIFFERENTIAL_CMDLINE_OPT_STR}"
        fi
    done < ${pfile}

    # Print options
    print_pipeline_opts

    echo "" >&2
}

########
check_pipeline_opts()
{
    echo "* Checking pipeline options..." >&2
    
    # Read input parameters
    local cmdline=$1
    local pfile=$2
        
    # Read information about the steps to be executed
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            define_opts_for_script "${cmdline}" "${stepspec}" || return 1
            local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
            local serial_script_opts=`serialize_string_array "script_opts_array" " ||| " ${MAX_NUM_SCRIPT_OPTS_TO_DISPLAY}`
            echo "STEP: ${stepname} ; OPTIONS: ${serial_script_opts}" >&2
        fi
    done < ${pfile}

    echo "" >&2
}

########
process_conda_req_entry() 
{
    local env_name=$1
    local yml_fname=$2

    # Check if environment already exists
    if conda_env_exists ${env_name}; then
        :
    else
        local condadir=`get_absolute_condadir`

        # Obtain absolute yml file name
        local abs_yml_fname=`get_abs_yml_fname ${yml_fname}`

        echo "Creating conda environment ${env_name} from file ${abs_yml_fname}..." >&2
        conda_env_prepare ${env_name} ${abs_yml_fname} ${condadir} || return 1
        echo "Package successfully installed"
    fi
}

########
process_conda_requirements_for_step()
{
    stepname=$1
    step_conda_envs=$2

    # Read information about conda environments
    while read conda_env_entry; do
        # Convert string to array
        local array
        IFS=' ' read -r -a array <<< $conda_env_entry
        local arraylen=${#array[@]}
        if [ ${arraylen} -ge 2 ]; then
            local env_name=${array[0]}
            local yml_fname=${array[1]}
            process_conda_req_entry ${env_name} ${yml_fname} || return 1
        else
            echo "Error: invalid conda entry for step ${stepname}; Entry: ${step_conda_envs}" >&2
        fi        
    done < <(echo ${step_conda_envs})
}

########
process_conda_requirements()
{
    echo "* Processing conda requirements (if any)..." >&2

    # Read input parameters
    local pfile=$1

    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            
            # Process conda envs information
            local conda_envs_funcname=`get_conda_envs_funcname ${stepname}`
            if func_exists ${conda_envs_funcname}; then
                step_conda_envs=`${conda_envs_funcname}` || exit 1
                process_conda_requirements_for_step ${stepname} "${step_conda_envs}" || return 1
            fi
        fi
    done < ${pfile}

    echo "Processing complete" >&2

    echo "" >&2
}

########
define_forced_exec_steps()
{
    echo "* Defining steps forced to be reexecuted (if any)..." >&2

    # Read input parameters
    local pfile=$1

    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            local step_forced=`extract_attr_from_stepspec "$stepspec" "force"`
            if [ ${step_forced} = "yes" ]; then
                mark_step_as_reexec $stepname ${FORCED_REEXEC_REASON}
            fi 
        fi
    done < ${pfile}

    echo "Definition complete" >&2

    echo "" >&2
}

########
check_script_is_older_than_modules()
{
    local script_filename=$1
    local fullmodnames=$2
    
    # Check if script exists
    if [ -f ${script_filename} ]; then
        # script exists
        script_older=0
        local mod
        for mod in ${fullmodnames}; do
            if [ ${script_filename} -ot ${mod} ]; then
                script_older=1
                echo "Warning: ${script_filename} is older than module ${mod}" >&2
            fi
        done
        # Return value
        if [ ${script_older} -eq 1 ]; then
            return 0
        else
            return 1
        fi
    else
        # script does not exist
        echo "Warning: ${script_filename} does not exist" >&2
        return 0
    fi
}

########
define_reexec_steps_due_to_code_update()
{
    echo "* Defining steps to be reexecuted due to code updates (if any)..." >&2

    # Read input parameters
    local dirname=$1
    local pfile=$2

    # Get names of pipeline modules
    local fullmodnames=`get_pipeline_fullmodnames $pfile` || return 1

    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`
            local status=`get_step_status ${dirname} ${stepname}`
            local script_filename=`get_script_filename ${dirname} ${stepname}`

            # Handle checkings depending of step status
            if [ "${status}" = "${FINISHED_STEP_STATUS}" ]; then
                if check_script_is_older_than_modules ${script_filename} "${fullmodnames}"; then
                    echo "Warning: last execution of step ${stepname} used outdated modules">&2
                    mark_step_as_reexec $stepname ${OUTDATED_CODE_REEXEC_REASON}
                fi
            fi

            if [ "${status}" = "${INPROGRESS_STEP_STATUS}" ]; then
                if check_script_is_older_than_modules ${script_filename} "${fullmodnames}"; then
                    echo "Warning: current execution of step ${stepname} is using outdated modules">&2
                fi
            fi
        fi
    done < ${pfile}

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_reexec_steps_due_to_deps()
{
    echo "* Defining steps to be reexecuted due to dependencies (if any)..." >&2

    local stepdeps_file=$1
    
    # Obtain list of steps to be reexecuted due to dependencies
    local reexec_steps_string=`get_reexec_steps_as_string`
    local reexec_steps_file=${outd}/.reexec_steps_due_to_deps.txt
    ${panpipe_bindir}/get_reexec_steps_due_to_deps -r "${reexec_steps_string}" -d ${stepdeps_file} > ${reexec_steps_file} || return 1

    # Read information about the steps to be re-executed due to
    # dependencies
    local stepname
    while read stepname; do
        if [ "${stepname}" != "" ]; then
            mark_step_as_reexec $stepname ${DEPS_REEXEC_REASON}
        fi
    done < ${reexec_steps_file}

    echo "Definition complete" >&2

    echo "" >&2
}

########
release_lock()
{
    local fd=$1
    local file=$2

    # Drop lock
    $FLOCK -u $fd || return 1

    # Try to acquire lock and remove associated file (if acquisition was
    # successful)
    $FLOCK -xn $fd && rm -f $file || return 1
}

########
prepare_lock()
{
    local fd=$1
    local file=$2
    eval "exec $fd>\"$file\"" && trap "release_lock $fd $file" EXIT;
}

########
ensure_exclusive_execution()
{
    local lockfile=${outd}/lock

    prepare_lock $LOCKFD $lockfile || return 1

    # Try to acquire lock exclusively
    $FLOCK -xn $LOCKFD || return 1
}

########
create_basic_dirs()
{
    mkdir -p ${outd} || { echo "Error! cannot create output directory" >&2; return 1; }
    set_panpipe_outdir ${outd}
    
    mkdir -p ${outd}/scripts || { echo "Error! cannot create scripts directory" >&2; return 1; }

    local fifodir=`get_absolute_fifoname`
    mkdir -p ${fifodir} || { echo "Error! cannot create fifos directory" >&2; return 1; }

    local condadir=`get_absolute_condadir`
    if [ ${conda_support_given} -eq 1 ]; then
        mkdir -p ${condadir}
    fi
}

########
create_shared_dirs()
{
    # Create shared directories required by the pipeline steps
    # IMPORTANT NOTE: the following function can only be executed after
    # loading pipeline modules
    create_pipeline_shdirs
}

########
register_fifos()
{
    # Register FIFOs (named pipes) required by the pipeline steps
    # IMPORTANT NOTE: the following function can only be executed after
    # loading pipeline modules
    register_pipeline_fifos
}

########
print_command_line()
{
    echo "cd $PWD" > ${outd}/command_line.sh
    echo ${command_line} >> ${outd}/command_line.sh
}

########
obtain_augmented_cmdline()
{
    local cmdline=$1
    
    if [ ${cfgfile_given} -eq 1 ]; then
        echo "* Processing configuration file (${cfgfile})..." >&2
        cfgfile_str=`cfgfile_to_string ${cfgfile}` || return 1
        echo "${cmdline} ${cfgfile_str}"
        echo "" >&2
    else
        echo $cmdline
    fi
}

########
get_stepdeps_from_detailed_spec()
{
    local stepdeps_spec=$1
    local sdeps=""

    # Iterate over the elements of the step specification: type1:stepname1,...,typen:stepnamen or type1:stepname1?...?typen:stepnamen
    local separator=`get_stepdeps_separator ${stepdeps_spec}`
    if [ "${separator}" = "" ]; then
        local stepdeps_spec_blanks=${stepdeps_spec}
    else
        local stepdeps_spec_blanks=`replace_str_elem_sep_with_blank "${separator}" ${stepdeps_spec}`
    fi
    local dep_spec
    for dep_spec in ${stepdeps_spec_blanks}; do
        local deptype=`get_deptype_part_in_dep ${dep_spec}`
        local mapped_deptype=`map_deptype_if_necessary ${deptype}`
        local stepname=`get_stepname_part_in_dep ${dep_spec}`
        # Check if there is an id for the step
        if [ ! -z "${PIPE_EXEC_STEP_IDS[${stepname}]}" ]; then
            if [ -z "${sdeps}" ]; then
                sdeps=${mapped_deptype}":"${PIPE_EXEC_STEP_IDS[${stepname}]}
            else
                sdeps=${sdeps}"${separator}"${mapped_deptype}":"${PIPE_EXEC_STEP_IDS[${stepname}]}
            fi
        fi
    done

    echo ${sdeps}
}

########
get_stepdeps()
{
    local step_id_list=$1
    local stepdeps_spec=$2
    case ${stepdeps_spec} in
            "afterok:all") apply_deptype_to_stepids "${step_id_list}" afterok
                    ;;
            "none") echo ""
                    ;;
            *) get_stepdeps_from_detailed_spec ${stepdeps_spec}
               ;;
    esac
}

########
execute_step()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local stepname=$3
    local stepspec=$4
    
    # Execute step

    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2

    ## Decide whether the step should be executed
    if [ "${status}" != "${FINISHED_STEP_STATUS}" -a "${status}" != "${INPROGRESS_STEP_STATUS}" ]; then
        # Create script
        define_opts_for_script "${cmdline}" "${stepspec}" || return 1
        local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
        local array_size=${#script_opts_array[@]}
        create_script ${dirname} ${stepname} "script_opts_array"

        # Archive script
        archive_script ${dirname} ${stepname}

        # Prepare files and directories for step
        update_step_completion_signal ${dirname} ${stepname} ${status} || { echo "Error when updating step completion signal for step" >&2 ; return 1; }
        clean_step_log_files ${dirname} ${stepname} ${array_size} || { echo "Error when cleaning log files for step" >&2 ; return 1; }
        clean_step_id_files ${dirname} ${stepname} ${array_size} || { echo "Error when cleaning id files for step" >&2 ; return 1; }
        create_outdir_for_step ${dirname} ${stepname} || { echo "Error when creating output directory for step" >&2 ; return 1; }
        prepare_fifos_owned_by_step ${stepname}
        
        # Launch step
        local task_array_list=`get_task_array_list ${dirname} ${stepname} ${array_size}`
        local stepdeps_spec=`extract_stepdeps_from_stepspec "$stepspec"`
        local stepdeps=`get_stepdeps "${step_id_list}" ${stepdeps_spec}`
        launch ${dirname} ${stepname} ${array_size} ${task_array_list} "${stepspec}" "${stepdeps}" "launch_outvar" || { echo "Error while launching step!" >&2 ; return 1; }

        # Update variables storing id information
        local primary_id=`get_primary_id ${launch_outvar}`
        PIPE_EXEC_STEP_IDS[${stepname}]=${primary_id}
        step_id_list="${step_id_list}:${PIPE_EXEC_STEP_IDS[${stepname}]}"

        # Write id to file
        write_step_id_info_to_file ${dirname} ${stepname} ${launch_outvar}
    else
        # If step is in progress, its id should be retrieved so as to
        # correctly express dependencies
        if [ "${status}" = "${INPROGRESS_STEP_STATUS}" ]; then
            local sid_info=`read_step_id_info_from_file ${dirname} ${stepname}` || { echo "Error while retrieving id of in-progress step" >&2 ; return 1; }
            local global_id=`get_global_id ${sid_info}`
            PIPE_EXEC_STEP_IDS[${stepname}]=${global_id}
            step_id_list="${step_id_list}:${PIPE_EXEC_STEP_IDS[${stepname}]}"
        fi
    fi
}

########
execute_pipeline_steps()
{
    echo "* Executing pipeline steps..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local pfile=$3
        
    # step_id_list will store the step ids of the pipeline steps
    local step_id_list=""
    
    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step name
            local stepname=`extract_stepname_from_stepspec "$stepspec"`

            execute_step "${cmdline}" ${dirname} ${stepname} "${stepspec}" || return 1
        fi
    done < ${pfile}

    echo "" >&2
}

########
debug_step()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local stepname=$3
    local stepspec=$4
    
    # Debug step

    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2

    ## Obtain step options
    local define_opts_funcname=`get_define_opts_funcname ${stepname}`
    ${define_opts_funcname} "${cmdline}" "${stepspec}" || return 1
}

########
execute_pipeline_steps_debug()
{
    echo "* Executing pipeline steps... (debug mode)" >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local pfile=$3
        
    # step_id_list will store the step ids of the pipeline steps
    local step_id_list=""
    
    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step name
            local stepname=`extract_stepname_from_stepspec "$stepspec"`

            debug_step "${cmdline}" ${dirname} ${stepname} "${stepspec}" || return 1                
        fi
    done < ${pfile}

    echo "" >&2
}

#################
# MAIN FUNCTION #
#################

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

# Save command line
command_line="$0 $*"

read_pars $@ || exit 1

check_pars || exit 1

absolutize_file_paths || exit 1

create_basic_dirs || exit 1

check_pipeline_file || exit 1

reordered_pfile=${outd}/${REORDERED_PIPELINE_BASENAME}
reorder_pipeline_file > ${reordered_pfile} || exit 1

stepdeps_file=${outd}/.stepdeps.txt
gen_stepdeps > ${stepdeps_file} || exit 1

configure_scheduler || exit 1

load_modules ${reordered_pfile} || exit 1

if [ ${showopts_given} -eq 1 ]; then
    show_pipeline_opts ${reordered_pfile} || exit 1
else
    augmented_cmdline=`obtain_augmented_cmdline "${command_line}"` || exit 1
    
    if [ ${checkopts_given} -eq 1 ]; then
        check_pipeline_opts "${augmented_cmdline}" ${reordered_pfile} || exit 1
    else
        load_pipeline_modules=1
        check_pipeline_opts "${augmented_cmdline}" ${reordered_pfile} || exit 1
        
        # NOTE: exclusive execution should be ensured after creating the output directory
        ensure_exclusive_execution || { echo "Error: there was a problem while trying to ensure exclusive execution of pipe_exec" ; exit 1; }

        create_shared_dirs

        register_fifos

        if [ ${conda_support_given} -eq 1 ]; then
            process_conda_requirements ${reordered_pfile} || exit 1
        fi

        define_forced_exec_steps ${reordered_pfile} || exit 1

        if [ ${reexec_outdated_steps_given} -eq 1 ]; then
            define_reexec_steps_due_to_code_update ${outd} ${reordered_pfile} || exit 1
        fi
        
        define_reexec_steps_due_to_deps ${stepdeps_file} || exit 1

        print_command_line || exit 1

        if [ ${debug} -eq 1 ]; then
            execute_pipeline_steps_debug "${augmented_cmdline}" ${outd} ${reordered_pfile} || exit 1
        else
            sched=`determine_scheduler`
            if [ ${sched} = ${BUILTIN_SCHEDULER} ]; then
                builtin_sched_execute_pipeline_steps "${augmented_cmdline}" ${outd} ${reordered_pfile} || exit 1
            else
                execute_pipeline_steps "${augmented_cmdline}" ${outd} ${reordered_pfile} || exit 1
            fi
        fi
    fi
fi
