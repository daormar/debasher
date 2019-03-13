# *- bash -*

# INCLUDE BASH LIBRARY
. ${panpipe_bindir}/panpipe_lib || exit 1

########
print_desc()
{
    echo "pipe_exec_batch executes a batch of pipelines"
    echo "type \"pipe_exec_batch --help\" to get usage information"
}

########
usage()
{
    echo "pipe_exec_batch           -f <string> -m <int> [-o <string> [-c]]"
    echo "                          [--help]"
    echo ""
    echo "-f <string>               File with a set of pipe_exec commands (one"
    echo "                          per line)"
    echo "-m <string>               Maximum number of pipelines executed simultaneously"
    echo "-o <string>               Output directory where the pipeline output should be"
    echo "                          moved (if not given, the output directories are"
    echo "                          provided by the pipe_exec commands)"
    echo "-c                        Clear content of destination directory of each"
    echo "                          pipeline"
    echo "                          when moving data (-o option should be given)"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    f_given=0
    m_given=0
    o_given=0
    c_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "-f") shift
                  if [ $# -ne 0 ]; then
                      file=$1
                      f_given=1
                  fi
                  ;;
            "-m") shift
                  if [ $# -ne 0 ]; then
                      maxp=$1
                      m_given=1
                  fi
                  ;;
            "-o") shift
                  if [ $# -ne 0 ]; then
                      outd=$1
                      o_given=1
                  fi
                  ;;
            "-c") if [ $# -ne 0 ]; then
                      c_given=1
                  fi
                  ;;
        esac
        shift
    done   
}

########
wait_simul_exec_reduction()
{
    # Example of passing associative array as function parameter
    # local _assoc_array=$(declare -p "$1")
    # eval "local -A assoc_array="${_assoc_array#*=}
    local maxp=$1
    local SLEEP_TIME=100
    local end=0
    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    
    while [ ${end} -eq 0 ] ; do
        # Iterate over active pipelines
        local num_finished_pipelines=0
        local num_unfinished_pipelines=0
        for pipeline_outd in "${!PIPELINE_COMMANDS[@]}"; do
            # Check if pipeline has finished execution
            ${panpipe_bindir}/pipe_status -d ${pipeline_outd} > /dev/null 2>&1
            local exit_code=$?

            case ${exit_code} in
                ${PIPELINE_FINISHED_EXIT_CODE})
                    num_finished_pipelines=`expr ${num_finished_pipelines} + 1`
                    ;;
                ${PIPELINE_UNFINISHED_EXIT_CODE})
                    num_unfinished_pipelines=`expr ${num_unfinished_pipelines} + 1`                    
                    ;;
            esac
        done
        
        # Sanity check: if maximum number of active pipelines has been
        # reached and all pipelines are unfinished, then it is not
        # possible to continue execution
        if [ ${num_active_pipelines} -ge ${maxp} -a ${num_unfinished_pipelines} -eq ${num_active_pipelines} ]; then
            if [ ${maxp} -gt 0 ]; then
                echo "Error: all active pipelines are unfinished and it is not possible to execute new ones" >&2
                return 1
            else
                echo "Error: all active pipelines are unfinished" >&2
                return 1
            fi
        fi
        
        # Obtain number of pending pipelines
        local pending_pipelines=`expr ${num_active_pipelines} - ${num_finished_pipelines}`

        # Wait if number of pending pipelines is equal or greater than
        # maximum
        if [ ${pending_pipelines} -ge ${maxp} ]; then
            sleep ${SLEEP_TIME}
        else
            end=1
        fi
    done
}

########
get_dest_dir_for_ppl()
{
    local pipeline_outd=$1
    local outd=$2    
    basedir=`$BASENAME ${pipeline_outd}`
    echo ${outd}/${basedir}
}

########
move_dir()
{
    local pipeline_outd=$1
    local outd=$2    
    destdir=`get_dest_dir_for_ppl ${pipeline_outd} ${outd}`
    
    # Remove destination directory if requested
    if [ ${c_given} -eq 1 ]; then
        if [ -d ${destdir} ]; then
            echo "Warning: removing ${destdir} directory" >&2
            rm -rf ${destdir} || return 1
        fi
    fi

    # Move directory
    if [ -d ${destdir} ]; then
        echo "Error: ${destdir} exists" >&2
        return 1
    else
        mv ${pipeline_outd} ${outd} || return 1
    fi
}

########
update_active_pipelines()
{
    local outd=$1
    
    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    echo "Previous number of active pipelines: ${num_active_pipelines}" >&2
    
    # Iterate over active pipelines
    for pipeline_outd in "${!PIPELINE_COMMANDS[@]}"; do
        # Check if pipeline has finished execution
        ${panpipe_bindir}/pipe_status -d ${pipeline_outd} > /dev/null 2>&1
        local exit_code=$?
        
        if [ ${exit_code} -eq ${PIPELINE_FINISHED_EXIT_CODE} ]; then
            echo "Pipeline stored in ${pipeline_outd} has completed execution" >&2
            # Remove pipeline from array of active pipelines
            unset PIPELINE_COMMANDS[${pipeline_outd}]
            # Move directory if requested
            if [ ! -z "${outd}" ]; then
                echo "Moving ${pipeline_outd} directory to ${outd}" >&2
                move_dir ${pipeline_outd} ${outd} || return 1
            fi
        fi
    done

    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    echo "Updated number of active pipelines: ${num_active_pipelines}" >&2
}

########
add_cmd_to_assoc_array()
{
    local cmd=$1

    # Extract output directory from command
    local dir=`read_opt_value_from_line "${cmd}" "-o"`

    # Add command to associative array if directory was sucessfully retrieved
    if [ ${dir} = ${OPT_NOT_FOUND} ]; then
        return 1
    else
        PIPELINE_COMMANDS[${dir}]=${cmd}
        return 0
    fi
}

########
wait_until_pending_ppls_finish()
{
    wait_simul_exec_reduction 1 || return 1
}

########
check_ppl_complete()
{
    local pipe_exec_cmd=$1
    local outd=$2
    
    if [ -z ${outd} ]; then
        # Results are not being moved to another directory, check if
        # pipeline has completed execution
        
        # Extract output directory from command
        local pipe_cmd_outd=`read_opt_value_from_line "${pipe_exec_cmd}" "--outdir"`
        if [ ${pipe_cmd_outd} = ${OPT_NOT_FOUND} ]; then
            return 1
        fi

        # Check pipeline status
        ${panpipe_bindir}/pipe_status -d ${pipe_cmd_outd} > /dev/null 2>&1
        exit_code=$?
        if [ ${exit_code} -eq 0 ]; then
            echo "yes"
        else
            echo "no"
        fi
    else
        # Check if complete pipeline was already moved to output
        # directory

        # Extract output directory from command
        local pipe_cmd_outd=`read_opt_value_from_line "${pipe_exec_cmd}" "--outdir"`
        if [ ${pipe_cmd_outd} = ${OPT_NOT_FOUND} ]; then
            return 1
        fi

        # Get pipeline directory after moving
        local destdir=`get_dest_dir_for_ppl ${pipe_cmd_outd} ${outd}`

        # Check pipeline status
        ${panpipe_bindir}/pipe_status -d ${destdir} > /dev/null 2>&1
        exit_code=$?
        if [ ${exit_code} -eq 0 ]; then
            echo "yes"
        else
            echo "no"
        fi
    fi
}

########
execute_batches()
{
    # Read file with pipe_exec commands
    lineno=1

    # Global variable declaration
    declare -A PIPELINE_COMMANDS

    # Process pipeline execution commands...
    while read pipe_exec_cmd; do

        echo "* Processing line ${lineno}..." >&2
        echo "" >&2
        
        echo "** Wait until number of simultaneous executions is below the given maximum..." >&2
        wait_simul_exec_reduction ${maxp} || return 1
        echo "" >&2
            
        echo "** Update array of active pipelines..." >&2
        update_active_pipelines "${outd}" || return 1
        echo "" >&2

        echo "** Check if pipeline is already completed..." >&2
        ppl_complete=`check_ppl_complete "${pipe_exec_cmd}" ${outd}` || { echo "Error: pipeline command does not contain -o option">&2 ; return 1; }
        echo ${ppl_complete}
        echo "" >&2

        if [ ${ppl_complete} = "no" ]; then
            echo "**********************" >&2
            echo "** Execute pipeline..." >&2
            echo ${pipe_exec_cmd} >&2
            ${pipe_exec_cmd} || return 1
            echo "**********************" >&2
            echo "" >&2
            
            echo "** Add pipeline command to associative array..." >&2
            add_cmd_to_assoc_array "${pipe_exec_cmd}" || { echo "Error: pipeline command does not contain -o option">&2 ; return 1; }
            echo "" >&2
        fi
        
        # Increase lineno
        lineno=`expr $lineno + 1`
        
    done < ${file}

    # Wait for all pipelines to finish
    echo "* Waiting for pending pipelines to finish..." >&2
    wait_until_pending_ppls_finish || return 1

    # Final update of active pipelines (necessary to finish moving
    # directories if requested)
    echo "* Final update of array of active pipelines..." >&2
    update_active_pipelines "${outd}" || return 1
    echo "" >&2
}

########
check_pars()
{
    if [ ${f_given} -eq 0 ]; then
        echo "Error! -f parameter not given!" >&2
        exit 1
    else
        if [ ! -f ${file} ]; then
            echo "Error! file ${file} does not exist" >&2 
            exit 1
        fi
    fi

    if [ ${m_given} -eq 0 ]; then
        echo "Error! -m parameter not given!" >&2
        exit 1
    fi

    if [ ${o_given} -eq 1 ]; then
        if [ ! -d ${outd} ]; then
            echo "Error! output directory does not exist" >&2 
            exit 1
        fi
    fi

    if [ ${c_given} -eq 1 -a ${o_given} -eq 0 ]; then
        echo "Error! -c option cannot be given without -o option" >&2 
        exit 1
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars $@ || exit 1

check_pars || exit 1

execute_batches || exit 1
