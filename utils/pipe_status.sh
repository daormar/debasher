# *- bash -*

# INCLUDE BASH LIBRARY
. ${bindir}/panpipe_lib || exit 1

########
print_desc()
{
    echo "pipe_status get status of pipeline steps"
    echo "type \"pipe_status --help\" to get usage information"
}

########
usage()
{
    echo "pipe_status              -d <string> [-s <string>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Directory where the pipeline steps are stored"
    echo "-s <string>               Step name whose status should be determined"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    s_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--version") version
                         exit 1
                         ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-s") shift
                  if [ $# -ne 0 ]; then
                      given_stepname=$1
                      s_given=1
                  fi
                  ;;
        esac
        shift
    done   
}

########
check_pars()
{
    if [ ${d_given} -eq 0 ]; then
        echo "Error! -d parameter not given!" >&2
        exit 1
    else
        if [ ! -d ${pdir} ]; then
            echo "Error! pipeline directory does not exist" >&2 
            exit 1
        fi

        if [ ! -f ${pdir}/command_line.sh ]; then
            echo "Error! ${pdir}/command_line.sh file is missing" >&2 
            exit 1
        fi
    fi
}

########
get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 ${command_line_file} | $AWK '{print $2}'` || return 1
    echo $workdir
}

########
get_cmdline()
{
    local command_line_file=$1
    local cmdline=`$TAIL -1 ${command_line_file}`
    echo $cmdline
}

########
get_pfile()
{
    local command_line_file=$1
    local cmdline=`$TAIL -1 ${command_line_file}`
    local pfile=`read_opt_value_from_line "$cmdline" "-p"` || return 1
    echo $pfile
}

########
process_status_for_pfile()
{
    local dirname=$1
    command_line_file=$dirname/command_line.sh
    
    # Extract information from command_line.sh file
    local orig_workdir=`get_orig_workdir ${command_line_file}` || return 1
    local cmdline=`get_cmdline ${command_line_file}` || return 1
    local pfile=`get_pfile ${command_line_file}` || return 1

    # Change directory
    cd ${orig_workdir}

    # Load pipeline modules
    load_pipeline_modules $pfile 2>/dev/null || return 1
        
    # Read information about the steps to be executed
    lineno=1
    pipeline_finished=1
    pipeline_in_progress=1
    pipeline_one_or_more_steps_in_progress=0
    while read jobspec; do
        local jobspec_comment=`pipeline_jobspec_is_comment "$jobspec"`
        local jobspec_ok=`pipeline_jobspec_is_ok "$jobspec"`
        if [ ${jobspec_comment} = "no" -a ${jobspec_ok} = "yes" ]; then
            # Extract step information
            local stepname=`extract_stepname_from_jobspec "$jobspec"`

            # If s option was given, continue to next iteration if step
            # name does not match with the given one
            if [ ${s_given} -eq 1 -a "${given_stepname}" != $stepname ]; then
                continue
            fi

            define_opts_for_script "${cmdline}" "${jobspec}" || return 1

            # Check step status
            local status=`get_step_status ${dirname} ${stepname}`

            # Print status
            echo "STEP: $stepname ; STATUS: $status"

            # Revise value of pipeline_finished variable
            if [ "${status}" != "${FINISHED_STEP_STATUS}" ]; then
                pipeline_finished=0
            fi

            # Revise value of pipeline_in_progress variable
            if [ "${status}" != "${FINISHED_STEP_STATUS}" -a "${status}" != "${INPROGRESS_STEP_STATUS}" ]; then
                pipeline_in_progress=0
            fi

            # Revise value of pipeline_in_progress variable
            if [ "${status}" = "${INPROGRESS_STEP_STATUS}" ]; then
                pipeline_one_or_more_steps_in_progress=1
            fi
            
        else
            if [ ${jobspec_comment} = "no" -a ${jobspec_ok} = "no" ]; then
                echo "Error: incorrect job specification at line $lineno of ${pfile}" >&2
                return 1
            fi
        fi
        
        # Increase lineno
        lineno=`expr $lineno + 1`
        
    done < ${pfile}

    # Return error if pipeline is not finished
    if [ ${pipeline_finished} -eq 1 ]; then
        return ${PIPELINE_FINISHED_EXIT_CODE}
    else
        if [ ${pipeline_in_progress} -eq 1 ]; then
            return ${PIPELINE_IN_PROGRESS_EXIT_CODE}
        else
            if [ ${pipeline_one_or_more_steps_in_progress} -eq 1 ]; then
                return ${PIPELINE_ONE_OR_MORE_STEPS_IN_PROGRESS_EXIT_CODE}
            else
                return ${PIPELINE_UNFINISHED_EXIT_CODE}
            fi
        fi
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars $@ || exit 1

check_pars || exit 1

process_status_for_pfile ${pdir} ${pfile}

exit $?
