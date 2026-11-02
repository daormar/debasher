# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
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
. "${debasher_pkglibdir}"/debasher_lib || exit 1

#############
# CONSTANTS #
#############

PRG_IS_COMPLETED=0
PRG_REQUIRES_POST_FINISH_ACTIONS=1
PRG_FAILED=2
PRG_IS_NOT_COMPLETED=3
PRG_IS_IN_PROGRESS=4
PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME=".prg_post_finish_actions_signal"
export RESERVED_HOOK_EXIT_CODE=200
# The exit status of the batch when every line was processed but some run
# did not complete, as debasher_exec ends with 3 when a process of its run
# did not finish
BATCH_WITH_FAILED_PROGRAMS_EXIT_CODE=3
# Seconds between two looks at the runs while waiting for a free slot
DEFAULT_POLL_SECS=60

########
print_desc()
{
    echo "debasher_exec_batch executes a batch of programs"
    echo "type \"debasher_exec_batch --help\" to get usage information"
}

########
usage()
{
    echo "debasher_exec_batch       -f <string> -m <int> [-o <string>] [-u <int>]"
    echo "                          [-k <string>] [--help]"
    echo ""
    echo "-f <string>               File with a set of debasher_exec commands (one"
    echo "                          per line)"
    echo "-m <int>                  Maximum number of programs executed simultaneously."
    echo "                          The next line is launched when the debasher_exec"
    echo "                          of a line returns: a debasher_exec that waits for"
    echo "                          its run (the built-in scheduler, or Slurm with"
    echo "                          --wait) runs the lines one after the other,"
    echo "                          whatever this maximum"
    echo "-o <string>               Output directory where the program output should be"
    echo "                          moved (if not given, the output directories are"
    echo "                          provided by the debasher_exec commands)"
    echo "-u <int>                  Maximum percentage of unfinished processes that is"
    echo "                          allowed when evaluating if program completed"
    echo "                          execution (0 by default)"
    echo "-k <string>               Execute script implementing a software hook after"
    echo "                          each program reaches finished status"
    echo "--help                    Display this help and exit"
    echo ""
    echo "A run that fails (more unfinished processes than -u allows, or a"
    echo "debasher_exec command that cannot be launched) frees its slot, and the"
    echo "other lines go on. A run that is still in progress from an earlier launch"
    echo "of the batch is waited for, not launched again."
    echo ""
    echo "Exit status: 0 when every run completed, 3 when some run did not (they are"
    echo "listed at the end), and 1 on an error of the batch itself."
    echo ""
    echo "DEBASHER_EXEC_BATCH_POLL_SECS, when set, gives the seconds between two looks"
    echo "at the runs while waiting (${DEFAULT_POLL_SECS} by default)."
}

########
read_pars()
{
    f_given=0
    m_given=0
    o_given=0
    u_given=0
    max_unfinished_process_perc=0
    k_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 0
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
                      max_unfinished_process_perc=$1
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
        file=$(debasher::_get_absolute_path "${file}")
    fi

    if [ ${o_given} -eq 1 ]; then
        outd=$(debasher::_get_absolute_path "${outd}")
    fi

    if [ ${k_given} -eq 1 ]; then
        k_val=$(debasher::_get_absolute_path "${k_val}")
    fi
}

########
# Prints the percentage of the processes of a program that are not
# finished, from the summary line of debasher_status ("* SUMMARY:
# num_processes= N ; finished= F ; ..."): every process that is not
# finished counts, whether it is unfinished, still to do or runnable
# again.
get_unfinished_process_perc()
{
    local status_output_file=$1
    "$AWK" '{if ($1=="*" && $3=="num_processes=" && $6=="finished=") printf"%d",($4-$7)*100/$4}' "${status_output_file}"
}

########
exec_hook()
{
    local outd=$1

    # export variables
    export DEBASHER_EXEC_BATCH_PRG_OUTD="${outd}"
    export DEBASHER_EXEC_BATCH_PRG_CMD=${PROGRAM_COMMANDS["${outd}"]}

    # Execute script
    "${k_val}"
    local exit_code=$?

    # unset variables
    unset DEBASHER_EXEC_BATCH_PRG_OUTD
    unset DEBASHER_EXEC_BATCH_PRG_CMD

    return ${exit_code}
}

########
post_prg_finish_actions_are_executed()
{
    local program_outd=$1
    local outd=$2

    if [ -z "${outd}" ]; then
        if [ -f "${program_outd}/${PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME}" ]; then
            return 0
        else
            return 1
        fi
    else
        destdir=$(get_dest_dir_for_prg "${program_outd}" "${outd}")
        if [ -f "${destdir}/${PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME}" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
signal_execution_of_post_prg_finish_actions()
{
    local program_outd=$1
    local outd=$2

    if [ -z "${outd}" ]; then
        touch "${program_outd}/${PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME}"
    else
        destdir=$(get_dest_dir_for_prg "${program_outd}" "${outd}")
        touch "${destdir}/${PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME}"
    fi
}

########
exec_post_prg_finish_actions()
{
    local program_outd=$1
    local outd=$2

    # Check that ${program_outd} directory exists
    if [ ! -d "${program_outd}" ]; then
        echo "Error: post program finish actions cannot be executed because ${program_outd} directory no longer exists" >&2
        return 1
    fi

    # Execute hook if requested
    if [ ${k_given} -eq 1 ]; then
        echo "- Executing hook implemented in ${k_val} for program stored in ${program_outd}" >&2
        exec_hook ${program_outd}
        local exit_code_hook=$?
        case ${exit_code_hook} in
            0) :
               ;;
            ${RESERVED_HOOK_EXIT_CODE}) return ${RESERVED_HOOK_EXIT_CODE}
                                        ;;
            *) echo "Error: hook execution failed for program stored in ${program_outd} directory" >&2
               return ${exit_code_hook}
               ;;
        esac
    fi

    # Move directory if requested
    if [ ! -z "${outd}" ]; then
        echo "- Moving ${program_outd} directory to ${outd}" >&2
        move_dir "${program_outd}" "${outd}" || return 1
    fi

    # Signal execution of post program finish actions
    signal_execution_of_post_prg_finish_actions "${program_outd}" "${outd}"
}

########
extract_outd_from_debasher_exec_cmd()
{
    local debasher_exec_cmd=$1

    debasher::_get_opt_value_from_quoted_cmd "$debasher_exec_cmd" "--outdir"
}

########
# The state of the run whose output directory the command names, for the
# batch: completed (moved to the final directory, or finished with its
# post finish actions done), waiting for its post finish actions, failed
# (more unfinished processes than -u allows), in progress (debasher_status
# finds a process of it still running), or not completed (anything else,
# such as a run never launched).
get_prg_status()
{
    local prg_cmd_outd=$1
    local outd=$2

    # Check if final output directory was provided and also that this
    # directory is not the same as the original output directory
    if [ "${outd}" != "" ]; then
        # Get program directory after moving
        local final_outdir=$(get_dest_dir_for_prg "${prg_cmd_outd}" "${outd}")
        if [ -d "${final_outdir}" ]; then
            # If output directory exists, it is assumed that the
            # program completed execution
            return ${PRG_IS_COMPLETED}
        fi
    fi

    # If original output directory exists then check program status
    if [ ! -d "${prg_cmd_outd}" ]; then
        return ${PRG_IS_NOT_COMPLETED}
    fi

    # Obtain program status
    local tmpfile=$("${MKTEMP}")
    local exit_code=0
    "${debasher_bindir}"/debasher_status -d "${prg_cmd_outd}" > "${tmpfile}" 2>&1 || exit_code=$?

    # Obtain percentage of unfinished processes
    local unfinished_process_perc=$(get_unfinished_process_perc "${tmpfile}")
    "${RM}" "${tmpfile}"

    # Evaluate exit code of debasher_status
    case ${exit_code} in
        ${DEBASHER_PROGRAM_FINISHED_EXIT_CODE})
            if post_prg_finish_actions_are_executed "${prg_cmd_outd}"; then
                return ${PRG_IS_COMPLETED}
            else
                return ${PRG_REQUIRES_POST_FINISH_ACTIONS}
            fi
            ;;
        ${DEBASHER_PROGRAM_UNFINISHED_EXIT_CODE})
            if [ "${unfinished_process_perc:-100}" -gt "${max_unfinished_process_perc}" ]; then
                return ${PRG_FAILED}
            elif post_prg_finish_actions_are_executed "${prg_cmd_outd}"; then
                return ${PRG_IS_COMPLETED}
            else
                return ${PRG_REQUIRES_POST_FINISH_ACTIONS}
            fi
            ;;
        ${DEBASHER_PROGRAM_IN_PROGRESS_EXIT_CODE})
            return ${PRG_IS_IN_PROGRESS}
            ;;
        *)
            return ${PRG_IS_NOT_COMPLETED}
            ;;
    esac
}

########
prg_has_processes_to_rerun()
{
    local debasher_exec_cmd=$1
    local prg_cmd_outd=$2
    local outd=$3

    # Check if final output directory was provided and also that this
    # directory is not the same as the original output directory
    if [ "${outd}" != "" ]; then
        # Get program directory after moving
        local final_outdir=$(get_dest_dir_for_prg "${prg_cmd_outd}" "${outd}")
        if [ -d "${final_outdir}" ]; then
            # If output directory exists, it is assumed that the
            # program completed execution
            return 1
        fi
    fi

    # Check if debasher_exec reports processes to be re-executed
    local rerun_processes_warning=$(eval "${debasher_exec_cmd}" --validate 2>&1 | "${GREP}" "${DEBASHER_RERUN_PROCESSES_WARNING}")
    if [ ! -z "${rerun_processes_warning}" ]; then
        return 0
    else
        return 1
    fi
}

########
# The state of a run when the batch reaches its line: that of
# get_prg_status, except that a run that is not in progress and that
# debasher_exec would partly run again (a process to rerun) is not
# completed.
get_initial_prg_status()
{
    local debasher_exec_cmd=$1
    local prg_cmd_outd=$2
    local outd=$3

    local status=0
    get_prg_status "${prg_cmd_outd}" "${outd}" || status=$?

    # A run in progress is waited for: asking debasher_exec about it would
    # be refused, since its debasher_exec holds the lock
    if [ ${status} -eq ${PRG_IS_IN_PROGRESS} ]; then
        return ${status}
    fi

    if prg_has_processes_to_rerun "${debasher_exec_cmd}" "${prg_cmd_outd}" "${outd}"; then
        return ${PRG_IS_NOT_COMPLETED}
    fi

    return ${status}
}

########
# The seconds between two looks at the runs while waiting
get_poll_secs()
{
    local secs=${DEBASHER_EXEC_BATCH_POLL_SECS:-${DEFAULT_POLL_SECS}}
    if [[ ! "${secs}" =~ ^[0-9]+$ ]]; then
        secs=${DEFAULT_POLL_SECS}
    fi
    echo "${secs}"
}

########
# Waits until fewer than $1 runs are active, looking at them every few
# seconds (see update_active_programs). A failed run is not active: it
# frees its slot. Fails only on an error of the batch itself.
wait_simul_exec_reduction()
{
    local maxp=$1

    while true; do
        update_active_programs "${outd}" || return 1
        [ ${#PROGRAM_COMMANDS[@]} -lt ${maxp} ] && return 0
        "${SLEEP}" "$(get_poll_secs)"
    done
}

########
get_dest_dir_for_prg()
{
    local program_outd=$1
    local outd=$2
    basedir=$("$BASENAME" "${program_outd}")
    echo "${outd}/${basedir}"
}

########
move_dir()
{
    local program_outd=$1
    local outd=$2
    destdir=$(get_dest_dir_for_prg "${program_outd}" "${outd}")

    # Move directory
    if [ -d "${destdir}" ]; then
        echo "Error: ${destdir} exists" >&2
        return 1
    else
        "${MV}" "${program_outd}" "${outd}" || return 1
    fi
}

########
# Takes the run of $1 out of the active runs and records it as failed,
# with the reason $2; a failed run frees its slot and is listed at the end
mark_program_as_failed()
{
    local program_outd=$1
    local reason=$2

    echo "Program stored in ${program_outd} did not complete execution: ${reason}" >&2
    FAILED_PROGRAMS["${program_outd}"]="${reason}"
    unset 'PROGRAM_COMMANDS["${program_outd}"]'
}

########
# Looks at one active run: a completed one leaves the active runs, one
# that finished gets its post finish actions (the hook, the move) and then
# leaves them, a failed one is marked as failed, and one in progress or
# not completed yet stays. Fails only when the post finish actions fail,
# an error of the batch, not of the run.
update_active_program()
{
    local program_outd=$1
    local outd=$2

    local status=0
    get_prg_status "${program_outd}" "${outd}" || status=$?

    case ${status} in
        ${PRG_IS_COMPLETED})
            echo "Program stored in ${program_outd} has completed execution" >&2
            unset 'PROGRAM_COMMANDS["${program_outd}"]'
            ;;
        ${PRG_REQUIRES_POST_FINISH_ACTIONS})
            local post_status=0
            exec_post_prg_finish_actions "${program_outd}" "${outd}" || post_status=$?
            case ${post_status} in
                0)
                    echo "Program stored in ${program_outd} has completed execution" >&2
                    unset 'PROGRAM_COMMANDS["${program_outd}"]'
                    ;;
                # The hook asks to be run again at the next look
                ${RESERVED_HOOK_EXIT_CODE})
                    :
                    ;;
                *)
                    return 1
                    ;;
            esac
            ;;
        ${PRG_FAILED})
            mark_program_as_failed "${program_outd}" "more unfinished processes than -u allows (see debasher_status -d ${program_outd})"
            ;;
    esac
}

########
# Looks at every active run (see update_active_program)
update_active_programs()
{
    local outd=$1

    local program_outd
    for program_outd in "${!PROGRAM_COMMANDS[@]}"; do
        update_active_program "${program_outd}" "${outd}" || return 1
    done
}

########
add_cmd_to_assoc_array()
{
    local cmd=$1
    local dir=$2

    PROGRAM_COMMANDS["${dir}"]="${cmd}"
}

########
# Processes a line of the batch, once a slot is free: checks its output
# directory, and launches its run unless it completed, is in progress from
# an earlier launch of the batch (it is waited for) or only waits for its
# post finish actions. A run is active once launched; one whose
# debasher_exec cannot launch it is failed. Fails only on an error of the
# batch itself, such as a line without --outdir.
process_batch_line()
{
    local debasher_exec_cmd=$1

    echo "** Extract output directory for program..." >&2
    local prg_cmd_outd
    prg_cmd_outd=$(extract_outd_from_debasher_exec_cmd "${debasher_exec_cmd}") || { echo "Error: program command does not contain --outdir option" >&2; return 1; }
    echo "${prg_cmd_outd}" >&2
    echo "" >&2

    echo "** Check correctness of output directory..." >&2
    local base_prg_cmd_outd=$("${DIRNAME}" "${prg_cmd_outd}")
    if debasher::_dirnames_are_equal "${outd}" "${base_prg_cmd_outd}"; then
        echo "Error: final output directory is equal to the directory containing the output directory for program" >&2
        return 1
    fi
    echo "yes" >&2
    echo "" >&2

    echo "** Check if program already completed execution..." >&2
    local status=0
    get_initial_prg_status "${debasher_exec_cmd}" "${prg_cmd_outd}" "${outd}" || status=$?
    case ${status} in
        ${PRG_IS_COMPLETED})
            echo "yes" >&2
            return 0
            ;;
        ${PRG_REQUIRES_POST_FINISH_ACTIONS})
            echo "no, its post finish actions are pending" >&2
            add_cmd_to_assoc_array "${debasher_exec_cmd}" "${prg_cmd_outd}"
            return 0
            ;;
        ${PRG_IS_IN_PROGRESS})
            echo "no, it is still in progress from an earlier launch: waiting for it" >&2
            add_cmd_to_assoc_array "${debasher_exec_cmd}" "${prg_cmd_outd}"
            return 0
            ;;
    esac
    echo "no" >&2
    echo "" >&2

    # A run launched again, such as one with a process to rerun, gets its
    # post finish actions again once it finishes: the signal of the ones
    # that an earlier launch did goes
    "${RM}" -f "${prg_cmd_outd}/${PRG_POST_FINISH_ACTIONS_SIGNAL_FILENAME}"

    # A run that ends with 3 (the built-in scheduler waits for its run) did
    # not finish every process, which -u judges as for any other run; any
    # other status other than 0 means that the run could not be launched
    echo "**********************" >&2
    echo "** Execute program..." >&2
    echo "${debasher_exec_cmd}" >&2
    local exec_status=0
    eval "${debasher_exec_cmd}" || exec_status=$?
    echo "**********************" >&2
    echo "" >&2
    unset 'FAILED_PROGRAMS["${prg_cmd_outd}"]'
    case ${exec_status} in
        0|${DEBASHER_PROGRAM_UNFINISHED_EXIT_CODE})
            add_cmd_to_assoc_array "${debasher_exec_cmd}" "${prg_cmd_outd}"
            ;;
        *)
            mark_program_as_failed "${prg_cmd_outd}" "debasher_exec could not launch it (exit status ${exec_status})"
            ;;
    esac
}

########
# Prints, at the end, the runs that did not complete, and fails when there
# is any
report_failed_programs()
{
    local num_failed=${#FAILED_PROGRAMS[@]}
    if [ ${num_failed} -eq 0 ]; then
        echo "All programs successfully completed execution" >&2
        return 0
    fi

    echo "Warning: ${num_failed} programs did not complete execution:" >&2
    local program_outd
    for program_outd in "${!FAILED_PROGRAMS[@]}"; do
        echo "- ${program_outd}: ${FAILED_PROGRAMS[${program_outd}]}" >&2
    done
    return 1
}

########
# Runs the lines of the batch, at most maxp at the same time, and waits for
# the last ones. Returns 0 when every run completed,
# BATCH_WITH_FAILED_PROGRAMS_EXIT_CODE when some did not, and 1 on an
# error of the batch itself.
execute_batches()
{
    # The active runs (running, or waiting for their post finish actions)
    # and the failed ones, by output directory
    declare -A PROGRAM_COMMANDS
    declare -A FAILED_PROGRAMS

    local lineno=1
    local debasher_exec_cmd
    while read -r debasher_exec_cmd; do
        # Execute built-in tilde expansion to avoid problems with "~"
        # symbol in file and directory paths
        debasher_exec_cmd=$(debasher::_expand_tildes "${debasher_exec_cmd}")

        echo "* Processing line ${lineno}..." >&2
        echo "" >&2

        echo "** Wait until number of simultaneous executions is below the given maximum..." >&2
        wait_simul_exec_reduction "${maxp}" || return 1
        echo "" >&2

        process_batch_line "${debasher_exec_cmd}" || return 1

        lineno=$((lineno+1))
    done < "${file}"

    # Wait for all programs to complete
    echo "* Waiting for pending programs to complete..." >&2
    wait_simul_exec_reduction 1 || return 1
    echo "" >&2

    report_failed_programs || return ${BATCH_WITH_FAILED_PROGRAMS_EXIT_CODE}
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

absolutize_file_paths || exit 1

execute_batches
