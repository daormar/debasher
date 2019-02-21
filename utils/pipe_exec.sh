# *- bash -*

# INCLUDE BASH LIBRARY
. ${panpipe_bindir}/panpipe_lib || exit 1

#############
# CONSTANTS #
#############

LOCKFD=99
MAX_NUM_SCRIPT_OPTS_TO_DISPLAY=10

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
    echo "                          [--dflt-nodes <string>] [--dflt-throttle <string>]"
    echo "                          [--cfgfile <string>] [--conda-support]"
    echo "                          [--showopts|--checkopts|--debug]"
    echo "                          [--version] [--help]"
    echo ""
    echo "--pfile <string>          File with pipeline steps to be performed (see manual"
    echo "                          for additional information)"
    echo "--outdir <string>         Output directory"
    echo "--sched <string>          Scheduler used to execute the pipeline (if not given,"
    echo "                          it is determined using information gathered during"
    echo "                          package configuration)" 
    echo "--dflt-nodes <string>     Default set of nodes used to execute the pipeline"
    echo "--dflt-throttle <string>  Default task throttle used when executing job arrays"
    echo "--cfgfile <string>        File with options (options provided in command line"
    echo "                          overwrite those given in the configuration file)"
    echo "--conda-support           Enable conda support"
    echo "--showopts                Show pipeline options"
    echo "--checkopts               Check pipeline options"
    echo "--debug                   Do everything except launching pipeline steps"
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
    dflt_nodes_given=0
    dflt_throttle_given=0
    cfgfile_given=0
    conda_support_given=0
    showopts_given=0
    checkopts_given=0
    debug=0
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
                      sched=$1
                      sched_given=1
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
        set_panpipe_scheduler ${sched} || return 1
        echo "scheduler: ${sched}" >&2
        echo "" >&2
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
            ${explain_cmdline_opts_funcname} || exit 1
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
            if check_func_exists ${conda_envs_funcname}; then
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

    $FLOCK -u $fd
    $FLOCK -xn $fd && rm -f $file
}

########
prepare_lock()
{
    local fd=$1
    local file=$2
    eval "exec $fd>\"$file\""; trap "release_lock $fd $file" EXIT;
}

########
ensure_exclusive_execution()
{
    local lockfile=${outd}/lock

    prepare_lock $LOCKFD $lockfile

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
get_stepdeps_from_detailed_spec()
{
    local stepdeps_spec=$1
    local sdeps=""

    # Iterate over the elements of the step specification: type1:stepname1,...,typen:stepnamen
    local stepdeps_spec_blanks=`replace_str_elem_sep_with_blank "," ${stepdeps_spec}`
    local dep_spec
    for dep_spec in ${stepdeps_spec_blanks}; do
        local deptype=`get_deptype_part_in_dep ${dep_spec}`
        local step=`get_stepname_part_in_dep ${dep_spec}`
        
        # Check if there is a id for the step
        local step_id=${step}_id
        if [ ! -z "${!step_id}" ]; then
            if [ -z "${sdeps}" ]; then
                sdeps=${deptype}":"${!step_id}
            else
                sdeps=${sdeps}","${deptype}":"${!step_id}
            fi
        fi
    done

    echo ${sdeps}
}

########
get_stepdeps()
{
    local stepdeps_spec=$1
    case ${stepdeps_spec} in
            "afterok:all") apply_deptype_to_stepids ${step_ids} afterok
                    ;;
            "none") echo ""
                    ;;
            *) get_stepdeps_from_detailed_spec ${stepdeps_spec}
               ;;
    esac
}

########
archive_script()
{
    local script_filename=$1
        
    # Archive script with date info
    local curr_date=`date '+%Y_%m_%d'`
    cp ${script_filename} ${script_filename}.${curr_date}
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
        return ${script_older}
    else
        # script does not exist
        echo "Warning: ${script_filename} does not exist" >&2
        return 1
    fi
}

########
execute_step()
{
    # Initialize variables
    local cmdline=$1
    local fullmodnames=$2
    local dirname=$3
    local stepname=$4
    local stepspec=$5
    
    # Execute step

    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2

    ## Decide whether the step should be executed
    if [ "${status}" != "${FINISHED_STEP_STATUS}" -a "${status}" != "${INPROGRESS_STEP_STATUS}" ]; then

        # Create script
        local script_filename=`get_script_filename ${dirname} ${stepname}`
        local step_function=`get_name_of_step_function ${stepname}`
        local step_function_post=`get_name_of_step_function_post ${stepname}`
        define_opts_for_script "${cmdline}" "${stepspec}" || return 1
        local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
        local array_size=${#script_opts_array[@]}
        create_script ${script_filename} ${step_function} "${step_function_post}" "script_opts_array"

        # Archive script
        archive_script ${script_filename}

        # Prepare files and directories for step
        update_step_completion_signal ${status} ${script_filename} || { echo "Error when updating step completion signal for step" >&2 ; return 1; }
        clean_step_log_files ${array_size} ${script_filename} || { echo "Error when cleaning log files for step" >&2 ; return 1; }
        local remove=0
        if [ ${array_size} -eq 1 ]; then
            remove=1
        fi
        prepare_outdir_for_step ${dirname} ${stepname} ${remove} || { echo "Error when preparing output directory for step" >&2 ; return 1; }
        prepare_fifos_owned_by_step ${stepname}
        
        # Execute script
        local job_array_list=`get_job_array_list ${array_size} ${script_filename}`
        local stepdeps_spec=`extract_stepdeps_from_stepspec "$stepspec"`
        local stepdeps="`get_stepdeps ${stepdeps_spec}`"
        local stepname_id=${stepname}_id
        launch ${script_filename} "${job_array_list}" "${stepspec}" "${stepdeps}" ${stepname_id} || { echo "Error while launching step!" >&2 ; return 1; }
        
        # Update variables storing ids
        step_ids="${step_ids}:${!stepname_id}"

        # Write id to file
        write_step_id_to_file ${dirname} ${stepname} ${!stepname_id}
    else
        # If step is in progress, its id should be retrieved so as to
        # correctly express dependencies
        if [ "${status}" = "${INPROGRESS_STEP_STATUS}" ]; then
            local stepname_id=${stepname}_id
            local sid=`read_step_id_from_file ${dirname} ${stepname}` || { echo "Error while retrieving id of in-progress step" >&2 ; return 1; }
            eval "${stepname_id}='${sid}'"
            step_ids="${step_ids}:${!stepname_id}"
        fi
        
        # Step will not be executed, check if outdated modules were used
        local script_filename=`get_script_filename ${dirname} ${stepname}`
        if check_script_is_older_than_modules ${script_filename} "${fullmodnames}"; then
            if [ "${status}" = "${INPROGRESS_STEP_STATUS}" ]; then
                echo "Warning: current execution of this script is using outdated modules">&2
            else
                echo "Warning: last execution of this script used outdated modules">&2
            fi
        fi
    fi
}

########
debug_step()
{
    # Initialize variables
    local cmdline=$1
    local fullmodnames=$2
    local dirname=$3
    local stepname=$4
    local stepspec=$5
    
    # Debug step

    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; STEPSPEC: ${stepspec}" >&2

    ## Obtain step options
    local define_opts_funcname=`get_define_opts_funcname ${stepname}`
    ${define_opts_funcname} "${cmdline}" "${stepspec}" || return 1
}

########
execute_pipeline_steps()
{
    if [ $debug -eq 0 ]; then
        echo "* Executing pipeline steps..." >&2
    else
        echo "* Executing pipeline steps... (debug mode)" >&2
    fi

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local pfile=$3
    
    # Get names of pipeline modules
    local fullmodnames=`get_pipeline_fullmodnames $pfile` || return 1
    
    # step_ids will store the step ids of the pipeline steps
    local step_ids=""
    
    # Read information about the steps to be executed
    local stepspec
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Extract step name
            local stepname=`extract_stepname_from_stepspec "$stepspec"`

            # Decide whether to execute or debug step
            if [ $debug -eq 0 ]; then
                execute_step "${cmdline}" "${fullmodnames}" ${dirname} ${stepname} "${stepspec}" || return 1
            else
                debug_step "${cmdline}" "${fullmodnames}" ${dirname} ${stepname} "${stepspec}" || return 1                
            fi
        fi
    done < ${pfile}

    echo "" >&2
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

reordered_pfile=${outd}/reordered_pipeline.ppl
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
        ensure_exclusive_execution || { echo "Error: exec_pipeline is being executed for the same output directory" ; exit 1; }

        create_shared_dirs

        register_fifos

        if [ ${conda_support_given} -eq 1 ]; then
            process_conda_requirements ${reordered_pfile} || exit 1
        fi

        define_forced_exec_steps ${reordered_pfile} || exit 1

        define_reexec_steps_due_to_deps ${stepdeps_file} || exit 1

        print_command_line || exit 1
        
        execute_pipeline_steps "${augmented_cmdline}" ${outd} ${pfile} || exit 1    
    fi
fi
