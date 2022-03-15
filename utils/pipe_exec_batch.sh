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

# INCLUDE BASH LIBRARY
. "${panpipe_bindir}"/panpipe_lib || exit 1

#############
# CONSTANTS #
#############

PPL_IS_COMPLETED=0
PPL_REQUIRES_POST_FINISH_ACTIONS=1
PPL_FAILED=2
PPL_IS_NOT_COMPLETED=3
PPL_POST_FINISH_ACTIONS_SIGNAL_FILENAME=".ppl_post_finish_actions_signal"
export RESERVED_HOOK_EXIT_CODE=200

########
print_desc()
{
    echo "pipe_exec_batch executes a batch of pipelines"
    echo "type \"pipe_exec_batch --help\" to get usage information"
}

########
usage()
{
    echo "pipe_exec_batch           -f <string> -m <int> [-o <string>] [-u <int>]"
    echo "                          [-k <string>] [--help]"
    echo ""
    echo "-f <string>               File with a set of pipe_exec commands (one"
    echo "                          per line)"
    echo "-m <int>                  Maximum number of pipelines executed simultaneously"
    echo "-o <string>               Output directory where the pipeline output should be"
    echo "                          moved (if not given, the output directories are"
    echo "                          provided by the pipe_exec commands)"
    echo "-u <int>                  Maximum percentage of unfinished steps that is"
    echo "                          allowed when evaluating if pipeline completed"
    echo "                          execution (0 by default)"
    echo "-k <string>               Execute script implementing a software hook after"
    echo "                          each pipeline reaches finished status"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    f_given=0
    m_given=0
    o_given=0
    u_given=0
    max_unfinished_step_perc=0
    k_given=0
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
            "-u") shift
                  if [ $# -ne 0 ]; then
                      max_unfinished_step_perc=$1
                      u_given=1
                  fi
                  ;;
            "-k") shift
                  if [ $# -ne 0 ]; then
                      k_val=$1
                      k_given=1
                  fi
                  ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${f_given} -eq 0 ]; then
        echo "Error! -f parameter not given!" >&2
        exit 1
    else
        if [ ! -f "${file}" ]; then
            echo "Error! file ${file} does not exist" >&2
            exit 1
        fi
    fi

    if [ ${m_given} -eq 0 ]; then
        echo "Error! -m parameter not given!" >&2
        exit 1
    fi

    if [ ${o_given} -eq 1 ]; then
        if [ ! -d "${outd}" ]; then
            echo "Error! output directory does not exist" >&2
            exit 1
        fi
    fi

    if [ ${k_given} -eq 1 ]; then
        if [ ! -f "${k_val}" ]; then
            echo "Error! file ${k_val} does not exist" >&2
            exit 1
        fi

        if [ ! -x "${k_val}" ]; then
            echo "Error! file ${k_val} is not executable" >&2
            exit 1
        fi
    fi
}

########
absolutize_file_paths()
{
    if [ ${f_given} -eq 1 ]; then
        file=`get_absolute_path "${file}"`
    fi

    if [ ${o_given} -eq 1 ]; then
        outd=`get_absolute_path "${outd}"`
    fi

    if [ ${k_given} -eq 1 ]; then
        k_val=`get_absolute_path "${k_val}"`
    fi
}

########
get_unfinished_step_perc()
{
    local pipe_status_output_file=$1
    "$AWK" '{if ($1=="*") printf"%d",$(13)*100/$4}' "${pipe_status_output_file}"
}

########
exec_hook()
{
    local outd=$1

    # export variables
    export PIPE_EXEC_BATCH_PPL_OUTD="${outd}"
    export PIPE_EXEC_BATCH_PPL_CMD=${PIPELINE_COMMANDS["${outd}"]}

    # Execute script
    "${k_val}"
    local exit_code=$?

    # unset variables
    unset PPL_OUTD
    unset PPL_CMD

    return ${exit_code}
}

########
post_ppl_finish_actions_are_executed()
{
    local pipeline_outd=$1
    local outd=$2

    if [ -z "${outd}" ]; then
        if [ -f "${pipeline_outd}/${PPL_POST_FINISH_ACTIONS_SIGNAL_FILENAME}" ]; then
            return 0
        else
            return 1
        fi
    else
        destdir=`get_dest_dir_for_ppl "${pipeline_outd}" "${outd}"`
        if [ -f "${destdir}/${PPL_POST_FINISH_ACTIONS_SIGNAL_FILENAME}" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
signal_execution_of_post_ppl_finish_actions()
{
    local pipeline_outd=$1
    local outd=$2

    if [ -z "${outd}" ]; then
        touch "${pipeline_outd}/${PPL_POST_FINISH_ACTIONS_SIGNAL_FILENAME}"
    else
        destdir=`get_dest_dir_for_ppl "${pipeline_outd}" "${outd}"`
        touch "${destdir}/${PPL_POST_FINISH_ACTIONS_SIGNAL_FILENAME}"
    fi
}

########
exec_post_ppl_finish_actions()
{
    local pipeline_outd=$1
    local outd=$2

    # Check that ${pipeline_outd} directory exists
    if [ ! -d "${pipeline_outd}" ]; then
        echo "Error: post pipeline finish actions cannot be executed because ${pipeline_outd} directory no longer exists" >&2
        return 1
    fi

    # Execute hook if requested
    if [ ${k_given} -eq 1 ]; then
        echo "- Executing hook implemented in ${k_val} for pipeline stored in ${pipeline_outd}" >&2
        exec_hook ${pipeline_outd}
        local exit_code_hook=$?
        case ${exit_code_hook} in
            0) :
               ;;
            ${RESERVED_HOOK_EXIT_CODE}) return ${RESERVED_HOOK_EXIT_CODE}
                                        ;;
            *) echo "Error: hook execution failed for pipeline stored in ${pipeline_outd} directory" >&2
               return ${exit_code_hook}
               ;;
        esac
    fi

    # Move directory if requested
    if [ ! -z "${outd}" ]; then
        echo "- Moving ${pipeline_outd} directory to ${outd}" >&2
        move_dir "${pipeline_outd}" "${outd}" || return 1
    fi

    # Signal execution of post pipeline finish actions
    signal_execution_of_post_ppl_finish_actions "${pipeline_outd}" "${outd}"
}

########
extract_outd_from_pipe_exec_cmd()
{
    local pipe_exec_cmd=$1

    # Obtain command line from command string
    cmdline=`serialize_cmdexec "${pipe_exec_cmd}"`

    # Obtain out directory for pipe command
    local pipe_cmd_outd=`read_opt_value_from_line "${cmdline}" "--outdir"`

    echo ${pipe_cmd_outd}
}

########
get_ppl_status()
{
    local pipe_cmd_outd=$1
    local outd=$2

    # Check if final output directory was provided and also that these
    # directory is not the same as the original output directory
    if [ "${outd}" != "" -a "${outd}" ]; then
        # Get pipeline directory after moving
        local final_outdir=`get_dest_dir_for_ppl "${pipe_cmd_outd}" "${outd}"`
        if [ -d "${final_outdir}" ]; then
            # If output directory exists, it is assumed that the
            # pipeline completed execution
            return ${PPL_IS_COMPLETED}
        fi
    fi

    # If original output directory exists then check pipeline status
    if [ -d "${pipe_cmd_outd}" ]; then
        # Obtain pipeline status
        local tmpfile=`"${MKTEMP}"`
        "${panpipe_bindir}"/pipe_status -d "${pipe_cmd_outd}" > "${tmpfile}" 2>&1
        exit_code=$?

        # Obtain percentage of unfinished steps
        local unfinished_step_perc=`get_unfinished_step_perc "${tmpfile}"`
        rm "${tmpfile}"

        # Evaluate exit code of pipe_status
        case $exit_code in
            ${PIPELINE_FINISHED_EXIT_CODE}) if post_ppl_finish_actions_are_executed "${pipe_cmd_outd}"; then
                                                return ${PPL_IS_COMPLETED}
                                            else
                                                return ${PPL_REQUIRES_POST_FINISH_ACTIONS}
                                            fi
                                            ;;
            ${PIPELINE_UNFINISHED_EXIT_CODE}) if [ ${unfinished_step_perc} -gt ${max_unfinished_step_perc} ]; then
                                                  return ${PPL_FAILED}
                                              else
                                                  if post_ppl_finish_actions_are_executed "${pipe_cmd_outd}"; then
                                                      return ${PPL_IS_COMPLETED}
                                                  else
                                                      return ${PPL_REQUIRES_POST_FINISH_ACTIONS}
                                                  fi
                                              fi
                                              ;;
            *) return ${PPL_IS_NOT_COMPLETED}
               ;;
        esac
    else
        return ${PPL_IS_NOT_COMPLETED}
    fi
}

########
wait_simul_exec_reduction()
{
    local maxp=$1
    local SLEEP_TIME=60
    local end=0
    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}

    while [ ${end} -eq 0 ] ; do
        # Iterate over active pipelines
        local num_completed_pipelines=0
        local num_failed_pipelines=0
        for pipeline_outd in "${!PIPELINE_COMMANDS[@]}"; do
            # Check if pipeline has completed execution
            get_ppl_status "${pipeline_outd}" "${outd}"
            local exit_code=$?
            case $exit_code in
                ${PPL_IS_COMPLETED}) num_completed_pipelines=$((num_completed_pipelines+1))
                                     ;;
                ${PPL_REQUIRES_POST_FINISH_ACTIONS}) exec_post_ppl_finish_actions "${pipeline_outd}" "${outd}"
                                                     local exit_code_post_comp_actions=$?
                                                     case $exit_code_post_comp_actions in
                                                         0) :
                                                            ;;
                                                         ${RESERVED_HOOK_EXIT_CODE}) :
                                                                                     ;;
                                                         *) return ${exit_code_post_comp_actions}
                                                            ;;
                                                     esac
                                                     ;;
                ${PPL_FAILED}) num_failed_pipelines=$((num_failed_pipelines+1))
                               ;;
            esac
        done

        # Obtain number of pending pipelines
        local num_pending_pipelines=$((num_active_pipelines - num_completed_pipelines))

        # Decide whether to wait or end the loop
        if [ ${num_pending_pipelines} -eq ${num_failed_pipelines} ]; then
            if [ ${num_pending_pipelines} -ge ${maxp} ]; then
                echo "Error: all pending pipelines failed and maximum capacity was reached" >&2
                return 1
            else
                end=1
            fi
        else
            if [ ${num_pending_pipelines} -lt ${maxp} ]; then
                end=1
            fi
        fi

        # Sleep if not end
        if [ ${end} -eq 0 ]; then
            sleep ${SLEEP_TIME}
        fi

    done
}

########
get_dest_dir_for_ppl()
{
    local pipeline_outd=$1
    local outd=$2
    basedir=`"$BASENAME" "${pipeline_outd}"`
    echo "${outd}/${basedir}"
}

########
move_dir()
{
    local pipeline_outd=$1
    local outd=$2
    destdir=`get_dest_dir_for_ppl "${pipeline_outd}" "${outd}"`

    # Move directory
    if [ -d "${destdir}" ]; then
        echo "Error: ${destdir} exists" >&2
        return 1
    else
        mv "${pipeline_outd}" "${outd}" || return 1
    fi
}

########
update_active_pipeline()
{
    local pipeline_outd=$1
    local outd=$2

    # Check pipeline status
    get_ppl_status "${pipeline_outd}" "${outd}"
    local exit_code=$?

    case $exit_code in
        ${PPL_IS_COMPLETED}) echo "Pipeline stored in ${pipeline_outd} has completed execution" >&2
                             unset PIPELINE_COMMANDS["${pipeline_outd}"]
                             ;;
        ${PPL_REQUIRES_POST_FINISH_ACTIONS}) echo "Pipeline stored in ${pipeline_outd} has post-finish actions pending" >&2
                                           ;;
    esac
}

########
update_active_pipelines()
{
    local outd=$1

    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    echo "Previous number of active pipelines: ${num_active_pipelines}" >&2

    # Iterate over active pipelines
    for pipeline_outd in "${!PIPELINE_COMMANDS[@]}"; do
        update_active_pipeline "${pipeline_outd}" "${outd}" || return 1
    done

    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    echo "Updated number of active pipelines: ${num_active_pipelines}" >&2
}

########
add_cmd_to_assoc_array()
{
    local cmd=$1
    local dir=$2

    PIPELINE_COMMANDS["${dir}"]="${cmd}"
}

########
wait_until_pending_ppls_complete()
{
    wait_simul_exec_reduction 1 || return 1
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

        # Execute built-in tilde expansion to avoid problems with "~"
        # symbol in file and directory paths
        pipe_exec_cmd=`expand_tildes "${pipe_exec_cmd}"`

        echo "* Processing line ${lineno}..." >&2
        echo "" >&2

        echo "** Wait until number of simultaneous executions is below the given maximum..." >&2
        wait_simul_exec_reduction ${maxp} || return 1
        echo "" >&2

        echo "** Update array of active pipelines..." >&2
        update_active_pipelines "${outd}" || return 1
        echo "" >&2

        echo "** Extract output directory for pipeline..." >&2
        local pipe_cmd_outd
        pipe_cmd_outd=`extract_outd_from_pipe_exec_cmd "${pipe_exec_cmd}"` || { echo "Error: pipeline command does not contain --outdir option">&2; return 1; }
        echo "${pipe_cmd_outd}"
        echo "" >&2

        echo "** Check correctness of output directory..." >&2
        local base_pipe_cmd_outd=`"${DIRNAME}" "${pipe_cmd_outd}"`
        if dirnames_are_equal "${outd}" "${base_pipe_cmd_outd}"; then
            echo "Error: final output directory is equal to the directory containing the output directory for pipeline">&2
            return 1;
        else
            echo "yes" >&2
        fi
        echo "" >&2

        echo "** Check if pipeline already completed execution..." >&2
        get_ppl_status "${pipe_cmd_outd}" "${outd}"
        local exit_code=$?
        case $exit_code in
            ${PPL_IS_COMPLETED}) echo "yes">&2
                                 ;;
            ${PPL_REQUIRES_POST_FINISH_ACTIONS}) echo "no">&2
                                               ;;
            ${PPL_FAILED}) echo "no">&2
                           ;;
            ${PPL_IS_NOT_COMPLETED}) echo "no">&2
                                     ;;
        esac
        echo "" >&2

        if [ ${exit_code} -eq ${PPL_REQUIRES_POST_FINISH_ACTIONS} ]; then
            add_cmd_to_assoc_array "${pipe_exec_cmd}" "${pipe_cmd_outd}"
        fi

        if [ ${exit_code} -eq ${PPL_IS_NOT_COMPLETED} -o ${exit_code} -eq ${PPL_FAILED} ]; then
            echo "**********************" >&2
            echo "** Execute pipeline..." >&2
            echo "${pipe_exec_cmd}" >&2
            eval "${pipe_exec_cmd}" || return 1
            echo "**********************" >&2
            echo "" >&2

            echo "** Add pipeline command to associative array..." >&2
            add_cmd_to_assoc_array "${pipe_exec_cmd}" "${pipe_cmd_outd}" || { echo "Error: pipeline command does not contain --outdir option">&2 ; return 1; }
            echo "" >&2
        fi

        # Increase lineno
        lineno=$((lineno+1))

    done < "${file}"

    # Wait for all pipelines to complete
    echo "* Waiting for pending pipelines to complete..." >&2
    wait_until_pending_ppls_complete || return 1
    echo "" >&2

    # Final update of active pipelines
    echo "* Final update of array of active pipelines..." >&2
    update_active_pipelines "${outd}" || return 1
    echo "" >&2

    # Check if there are active pipelines
    local num_active_pipelines=${#PIPELINE_COMMANDS[@]}
    if [ ${num_active_pipelines} -eq 0 ]; then
        echo "All pipelines successfully completed execution" >&2
        echo "" >&2
    else
        echo "Warning: ${num_active_pipelines} pipelines did not complete execution" >&2
        echo "" >&2
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

absolutize_file_paths || exit 1

execute_batches || exit 1
