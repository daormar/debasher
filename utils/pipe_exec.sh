# *- bash -*

# INCLUDE BASH LIBRARY
. ${bindir}/bam_utils_lib

#############
# CONSTANTS #
#############

LOCKFD=99
MAX_NUM_SCRIPT_OPTS_TO_DISPLAY=10

########
print_desc()
{
    echo "exec_pipeline executes general purpose pipelines"
    echo "type \"exec_pipeline --help\" to get usage information"
}

########
usage()
{
    echo "exec_pipeline        -a <string> -o <string>"
    echo "                     [--showopts|--checkopts|--debug]"
    echo "                     [--version] [--help]"
    echo ""
    echo "-a <string>          File with analysis steps to be performed (see manual"
    echo "                     for additional information)"
    echo "-o <string>          Output directory"
    echo "--showopts           Show pipeline options"
    echo "--checkopts          Check pipeline options"
    echo "--debug              Do everything except launching pipeline steps"
    echo "--version            Display version information and exit"
    echo "--help               Display this help and exit"
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
    a_given=0
    o_given=0
    showopts_given=0
    checkopts_given=0
    debug=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--version") version
                         exit 1
                         ;;
            "-a") shift
                  if [ $# -ne 0 ]; then
                      afile=$1
                      a_given=1
                  fi
                  ;;
            "-o") shift
                  if [ $# -ne 0 ]; then
                      outd=$1
                      o_given=1
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
    if [ ${a_given} -eq 0 ]; then   
        echo "Error! -a parameter not given!" >&2
        exit 1
    else
        if [ ! -f ${afile} ]; then
            echo "Error! file ${afile} does not exist" >&2
            exit 1
        fi
    fi
    
    if [ ${o_given} -eq 0 ]; then
        echo "Error! -o parameter not given!" >&2
        exit 1
    else
        if [ -d ${outd} ]; then
            echo "Warning! output directory does exist" >&2 
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
    if [ ${a_given} -eq 1 ]; then   
        afile=`get_absolute_path ${afile}`
    fi

    if [ ${o_given} -eq 1 ]; then   
        outd=`get_absolute_path ${outd}`
    fi
}

########
check_pipeline_file()
{
    echo "* Checking pipeline file ($afile)..." >&2

    ${bindir}/check_pipeline -a ${afile} || return 1

    echo "" >&2
}

########
reorder_pipeline_file()
{
    echo "* Obtaining reordered pipeline file ($afile)..." >&2

    ${bindir}/check_pipeline -a ${afile} -r > ${outd}/reordered_pipeline.csv 2> /dev/null || return 1

    echo "" >&2
}

########
show_pipeline_opts()
{
    echo "* Pipeline options..." >&2

    # Read input parameters
    local cmdline=$1
    local afile=$2

    # Load pipeline modules
    load_pipeline_modules $afile || return 1
        
    # Read information about the steps to be executed
    while read jobspec; do
        local jobspec_comment=`analysis_jobspec_is_comment "$jobspec"`
        local jobspec_ok=`analysis_jobspec_is_ok "$jobspec"`
        if [ ${jobspec_comment} = "no" -a ${jobspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_jobspec "$jobspec"`
            local script_explain_cmdline_opts_funcname=`get_script_explain_cmdline_opts_funcname ${stepname}`
            ${script_explain_cmdline_opts_funcname} || exit 1
        fi
    done < ${outd}/reordered_pipeline.csv

    # Print options
    print_pipeline_opts
}

########
check_pipeline_opts()
{
    echo "* Checking pipeline options..." >&2
    
    # Read input parameters
    local cmdline=$1
    local afile=$2

    # Load pipeline modules
    load_pipeline_modules $afile || return 1
        
    # Read information about the steps to be executed
    while read jobspec; do
        local jobspec_comment=`analysis_jobspec_is_comment "$jobspec"`
        local jobspec_ok=`analysis_jobspec_is_ok "$jobspec"`
        if [ ${jobspec_comment} = "no" -a ${jobspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_jobspec "$jobspec"`
            define_opts_for_script "${cmdline}" "${jobspec}" || return 1
            local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
            local serial_script_opts=`serialize_string_array "script_opts_array" " ||| " ${MAX_NUM_SCRIPT_OPTS_TO_DISPLAY}`
            echo "STEP: ${stepname} ; OPTIONS: ${serial_script_opts}" >&2
        fi
    done < ${outd}/reordered_pipeline.csv

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

    mkdir -p ${outd}/scripts || { echo "Error! cannot create scripts directory" >&2; return 1; }
}

########
create_shared_dirs()
{
    # Create shared directories required by the pipeline steps
    # IMPORTANT NOTE: the following function can only be executed after
    # executing check_pipeline_pars
    create_pipeline_shdirs ${outd}
}

########
print_command_line()
{
    echo "cd $PWD" > ${outd}/command_line.sh
    echo ${command_line} >> ${outd}/command_line.sh
}

########
get_jobdeps_from_detailed_spec()
{
    local jobdeps_spec=$1
    local jdeps=""

    # Iterate over the elements of the job specification: type1:stepname1,...,typen:stepnamen
    prevIFS=$IFS
    IFS=','
    for dep_spec in ${jobdeps_spec}; do
        local deptype=`get_deptype_part_in_dep ${dep_spec}`
        local step=`get_stepname_part_in_dep ${dep_spec}`
        
        # Check if there is a jid for the step
        local step_jid=${step}_jid
        if [ ! -z "${!step_jid}" ]; then
            if [ -z "${jdeps}" ]; then
                jdeps=${deptype}":"${!step_jid}
            else
                jdeps=${jdeps}","${deptype}":"${!step_jid}
            fi
        fi
    done
    IFS=${prevIFS}

    echo ${jdeps}
}

########
get_jobdeps()
{
    local jobdeps_spec=$1
    case ${jobdeps_spec} in
            "afterok:all") apply_deptype_to_jobids ${step_jids} afterok
                    ;;
            "none") echo ""
                    ;;
            *) get_jobdeps_from_detailed_spec ${jobdeps_spec}
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
    local jobspec=$5
    
    # Execute step

    # Initialize script variables
    local script_filename=`get_script_filename ${dirname} ${stepname}`
    local step_function=`get_step_function ${stepname}`
    define_opts_for_script "${cmdline}" "${jobspec}" || return 1
    local script_opts_array=("${SCRIPT_OPT_LIST_ARRAY[@]}")
    local array_size=${#script_opts_array[@]}
    
    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; JOBSPEC: ${jobspec}" >&2

    ## Decide whether the step should be executed
    if [ "${status}" != "${FINISHED_STEP_STATUS}" -a "${status}" != "${INPROGRESS_STEP_STATUS}" ]; then
        # Create script
        create_script ${script_filename} ${step_function} "script_opts_array"

        # Archive script
        archive_script ${script_filename}

        # Execute script
        reset_scriptdir_for_step ${script_filename} || return 1
        reset_outdir_for_step ${dirname} ${stepname} || return 1
        local jobdeps_spec=`extract_jobdeps_from_jobspec "$jobspec"`
        local jobdeps="`get_jobdeps ${jobdeps_spec}`"
        local stepname_jid=${stepname}_jid
        launch ${script_filename} ${array_size} "${jobspec}" "${jobdeps}" ${stepname_jid} || return 1
        
        # Update variables storing jids
        step_jids="${step_jids}:${!stepname_jid}"

        # Write id to file
        write_step_id_to_file ${dirname} ${stepname} ${!stepname_jid}
    else
        local script_filename=`get_script_filename ${dirname} ${stepname}`
        prev_script_older=0
        check_script_is_older_than_modules ${script_filename} "${fullmodnames}" || prev_script_older=1
        if [ ${prev_script_older} -eq 1 ]; then
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
    local jobspec=$5
    
    # Debug step

    ## Obtain step status
    local status=`get_step_status ${dirname} ${stepname}`
    echo "STEP: ${stepname} ; STATUS: ${status} ; JOBSPEC: ${jobspec}" >&2

    ## Obtain step options
    local script_define_opts_funcname=`get_script_define_opts_funcname ${stepname}`
    ${script_define_opts_funcname} "${cmdline}" "${jobspec}" || return 1
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
    local afile=$3

    # Load pipeline modules
    load_pipeline_modules $afile || return 1
    local fullmodnames=`get_pipeline_fullmodnames $afile` || return 1
    
    # step_jids will store the job ids of the analysis steps
    local step_jids=""
    
    # Read information about the steps to be executed
    while read jobspec; do
        local jobspec_comment=`analysis_jobspec_is_comment "$jobspec"`
        local jobspec_ok=`analysis_jobspec_is_ok "$jobspec"`
        if [ ${jobspec_comment} = "no" -a ${jobspec_ok} = "yes" ]; then
            # Extract step name
            local stepname=`extract_stepname_from_jobspec "$jobspec"`

            # Decide whether to execute or debug step
            if [ $debug -eq 0 ]; then
                execute_step "${cmdline}" "${fullmodnames}" ${dirname} ${stepname} "${jobspec}" || return 1
            else
                debug_step "${cmdline}" "${fullmodnames}" ${dirname} ${stepname} "${jobspec}" || return 1                
            fi
        fi
    done < ${outd}/reordered_pipeline.csv

    echo "" >&2
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

reorder_pipeline_file || exit 1

if [ ${showopts_given} -eq 1 ]; then
    show_pipeline_opts "${command_line}" ${afile} || exit 1
else
    if [ ${checkopts_given} -eq 1 ]; then
        check_pipeline_opts "${command_line}" ${afile} || exit 1
    else
        check_pipeline_opts "${command_line}" ${afile} || exit 1

        create_shared_dirs

        # NOTE: exclusive execution should be ensured after creating the output directory
        ensure_exclusive_execution || { echo "Error: exec_pipeline is being executed for the same output directory" ; exit 1; }

        print_command_line || exit 1
        
        execute_pipeline_steps "${command_line}" ${outd} ${afile} || exit 1    
    fi
fi
