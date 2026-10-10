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

#######################
# SCHEDULER FUNCTIONS #
#######################

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib_sched_slurm || exit 1
. "${debasher_pkglibdir}"/debasher_lib_sched_builtin || exit 1
. "${debasher_pkglibdir}"/debasher_lib_sched_procs || exit 1
. "${debasher_pkglibdir}"/debasher_lib_sched_rerun || exit 1
. "${debasher_pkglibdir}"/debasher_lib_sched_topo_sort || exit 1

########
debasher::_set_debasher_outdir()
{
    local abs_outd=$1

    DEBASHER_PROGRAM_OUTDIR=${abs_outd}
}

########
debasher::_get_prg_outd()
{
    echo "${DEBASHER_PROGRAM_OUTDIR}"
}

########
debasher::_set_debasher_scheduler()
{
    local sched=$1

    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            # Verify SLURM availability
            if ! command -v "$SBATCH" >/dev/null 2>&1; then
                echo "Error: SLURM scheduler is not installed in your system"
                return 1
            fi
            DEBASHER_SCHEDULER=${DEBASHER_SLURM_SCHEDULER}
            debasher::_init_slurm_scheduler
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            DEBASHER_SCHEDULER=${DEBASHER_BUILTIN_SCHEDULER}
            ;;
        *)  echo "Error: ${sched} is not a valid scheduler"
            DEBASHER_SCHEDULER=""
            return 1
            ;;
    esac
}

########
debasher::_set_debasher_default_nodes()
{
    local value=$1

    DEBASHER_DEFAULT_NODES=$value
}

########
debasher::_set_debasher_default_array_task_throttle()
{
    local value=$1

    DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE=$value
}

########
debasher::_determine_scheduler()
{
    # Check if scheduler was already specified
    if [ -z "${DEBASHER_SCHEDULER}" ]; then
        # Scheduler not specified: pick one based on what's actually
        # available on this machine right now (not at package build
        # time, see configure.ac)
        if ! command -v "${SBATCH}" >/dev/null 2>&1; then
            echo ${DEBASHER_BUILTIN_SCHEDULER}
        else
            echo ${DEBASHER_SLURM_SCHEDULER}
        fi
    else
        echo ${DEBASHER_SCHEDULER}
    fi
}

########
debasher::_get_scheduler()
{
    echo ${DEBASHER_SCHEDULER}
}

########
debasher::_create_script()
{
    # Init variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4

    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_create_slurm_script "${cmdline}" "${dirname}" "$processname" "${opt_array_size}"
            ;;
    esac
}

########
debasher::_get_scheduler_throttle()
{
    local process_spec_throttle=$1

    if [ "${process_spec_throttle}" = ${DEBASHER_ATTR_NOT_FOUND} ]; then
        echo "${DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE}"
    else
        echo "${process_spec_throttle}"
    fi
}

########
# Whether a debasher_exec holds the lock of an output directory, which it
# does for as long as it prepares or runs a program there: with the
# built-in scheduler, until the program ends. The check takes the lock for
# an instant, which debasher_exec waits for (see
# DEBASHER_EXEC_LOCK_WAIT_SECS), and creates no lock file where there is
# none.
#
# $1 - Absolute path of the output directory.
debasher::_outdir_is_locked()
{
    local dirname=$1
    local lockfile="${dirname}/${DEBASHER_LOCK_BASENAME}"

    [ -f "${lockfile}" ] || return 1
    ! "${FLOCK}" -n "${lockfile}" true
}

########
# Stops the debasher_exec that is preparing or running a program in an
# output directory, if any, and waits until it has ended. That
# debasher_exec holds the lock of the directory for as long as it runs, and
# with the built-in scheduler it keeps launching tasks until the program
# ends, so stopping the tasks that run would not stop the program: it is
# stopped first. It is sent SIGTERM, which the built-in scheduler takes as a
# request to launch nothing more, and SIGKILL if it has not ended within
# DEBASHER_EXEC_STOP_GRACE_SECS. The lock being free is what proves that it
# has ended: the tasks it launched do not hold the lock. Returns 1 if the
# lock is still held after that.
#
# $1 - Absolute path of the output directory.
debasher::_stop_run_scheduler()
{
    local dirname=$1
    local lockfile="${dirname}/${DEBASHER_LOCK_BASENAME}"

    debasher::_outdir_is_locked "${dirname}" || return 0

    local pid
    pid=$("${CAT}" "${lockfile}")
    if ! debasher::_str_is_positive_integer "${pid}"; then
        echo "Error: the output directory ${dirname} is locked, but its lock file does not give the process that holds it" >&2
        return 1
    fi

    echo "Stopping debasher_exec (process ${pid}), so that it launches nothing more..." >&2
    kill -TERM "${pid}" 2>/dev/null || true
    if ! "${FLOCK}" -w "${DEBASHER_EXEC_STOP_GRACE_SECS}" "${lockfile}" true; then
        echo "Warning: debasher_exec (process ${pid}) did not stop within ${DEBASHER_EXEC_STOP_GRACE_SECS}s, killing it" >&2
        kill -KILL "${pid}" 2>/dev/null || true
        if ! "${FLOCK}" -w "${DEBASHER_EXEC_STOP_GRACE_SECS}" "${lockfile}" true; then
            echo "Error: the output directory ${dirname} is still locked" >&2
            return 1
        fi
    fi
}

########
# Whether the throttle of a process, its own or the default one (see
# debasher::_get_scheduler_throttle), lets every task of the process run at
# once: true for a process with no throttle, and for one whose throttle is
# not smaller than its number of tasks. The built-in scheduler in oneshot
# mode never waits for a task to end, so the tasks that a throttle holds
# back would never be launched.
#
# $1 - Name of the process.
# $2 - Final specification of the process.
debasher::_throttle_lets_all_tasks_run()
{
    local processname=$1
    local process_spec=$2

    local throttle=$(debasher::_get_scheduler_throttle "$(debasher::_extract_throttle_from_process_spec "${process_spec}")")
    [ "${throttle}" -eq "${DEBASHER_ARRAY_TASK_NOTHROTTLE}" ] && return 0

    local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
    [ "${throttle}" -ge "${num_tasks}" ]
}

########
debasher::_get_num_attempts()
{
    # Initialize variables
    local time=$1
    local mem=$2

    # Obtain arrays for time and memory limits
    local time_array
    local mem_array
    IFS="$DEBASHER_ATTEMPT_SEP" read -r -a time_array <<< "${time}"
    IFS="$DEBASHER_ATTEMPT_SEP" read -r -a mem_array <<< "${mem}"

    # Return length of longest array
    if [ ${#time_array[@]} -gt ${#mem_array[@]} ]; then
        echo ${#time_array[@]}
    else
        echo ${#mem_array[@]}
    fi
}

########
debasher::_get_mem_attempt_value()
{
    # Initialize variables
    local mem=$1
    local attempt_no=$2

    # Obtain array for memory limits
    local mem_array
    IFS="$DEBASHER_ATTEMPT_SEP" read -r -a mem_array <<< "${mem}"

    # Return value for attempt
    local array_idx=$(( attempt_no - 1 ))
    local array_len=${#mem_array[@]}
    if [ ${array_idx} -lt  ${array_len} ]; then
        echo ${mem_array[${array_idx}]}
    else
        local last_array_idx=$(( array_len - 1 ))
        echo ${mem_array[${last_array_idx}]}
    fi
}

########
debasher::_get_time_attempt_value()
{
    # Initialize variables
    local time=$1
    local attempt_no=$2

    # Obtain array for time limits
    local time_array
    IFS="$DEBASHER_ATTEMPT_SEP" read -r -a time_array <<< "${time}"

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
debasher::_launch()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local processdeps=$6
    local outvar=$7

    # Launch process
    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER}) ## Launch using slurm
            debasher::_slurm_launch "${dirname}" "${processname}" "${array_size}" "${task_array_list}" "${process_spec}" "${processdeps}" "${outvar}" || return 1
            ;;
    esac
}

########
debasher::_get_primary_id()
{
    # Returns the primary id of a process. The primary id is the
    # job/process directly executing the process (additional jobs/processes
    # may be necessary to complete process execution)
    local launch_id_info=$1

    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_get_primary_id_slurm "${launch_id_info}"
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            echo "${launch_id_info}"
            ;;
    esac
}

########
debasher::_get_global_id()
{
    # Returns the global id of a process. The global id is the job/process
    # registering the process as finished. It is only executed when all of
    # the others jobs/processes are completed
    local launch_id_info=$1

    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_get_global_id_slurm "${launch_id_info}"
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            echo "${launch_id_info}"
            ;;
    esac
}

########
debasher::_stop_pid()
{
    local pid=$1

    # Kill the whole process group ("-$pid"), not just $pid:
    # debasher_builtin_sched::_launch starts each process's script with
    # job control enabled so it becomes its own process group leader
    # (pgid == pid) precisely so this can reach every child it forks
    # (its own stdout-capturing tee pipeline, plus a mirrored fifo's
    # background tap, if any) instead of leaving them running as
    # orphans.
    kill -9 -- "-$pid" > /dev/null 2>&1 || return 1

    return 0
}

########
debasher::_stop_pid_gracefully()
{
    local pid=$1

    # SIGTERM, not SIGKILL, and still the whole process group, for the
    # same reason as _stop_pid: without it, a single-pid SIGTERM only
    # reaches this process's own wrapper script (see
    # debasher_builtin_sched::_print_script_trap), never a resident
    # process's own Python interpreter, which sits below it in the fork
    # tree. The wrapper survives this same broadcast (that trap again) so
    # it can still finish its own post-processing once whatever it is
    # running actually exits (FBPProcess and Supervisor both install a
    # SIGTERM handler of their own for exactly this, see
    # engine/debasher_runtime_fbp.py and engine/debasher_runtime_supervisor.py).
    kill -TERM -- "-$pid" > /dev/null 2>&1 || return 1

    return 0
}

########
debasher::_id_exists()
{
    local id=$1

    # Check id depending on the scheduler
    local sched=$(debasher::_get_scheduler)
    local exit_code
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_slurm_id_exists "$id"
            exit_code=$?
            return "${exit_code}"
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_builtin_sched_id_exists "$id"
            exit_code=$?
            return "${exit_code}"
        ;;
    esac
}

########
# Whether the dependencies of a process can still hold when some of them
# name processes that are not launched in this run, and so have no id to
# give the scheduler (a scheduler, such as Slurm, that takes only the
# dependencies on launched processes). A process with no id has either
# finished in an earlier run, and a dependency on it holds unless it is
# afternotok, which asks for it to have failed, or it has not finished and
# is not launched either, and no dependency on it will ever hold. A
# dependency on a process with an id is left to the scheduler. With ","
# every dependency has to be able to hold, with "?" one is enough.
#
# $1 - Dependencies of the process, as its final specification gives them
#      (the value of processdeps).
# $2 - Output directory of the run.
# $3 - Name of the associative array with the id of each launched process.
debasher::_deps_without_ids_can_hold()
{
    local processdeps_spec=$1
    local dirname=$2
    local -n deps_ids_ref=$3

    [ -z "${processdeps_spec}" ] && return 0
    [ "${processdeps_spec}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] && return 0

    local separator=$(debasher::_get_processdeps_separator "${processdeps_spec}")
    local -a deps_array
    if [ -z "${separator}" ]; then
        deps_array=("${processdeps_spec}")
    else
        IFS="${separator}" read -r -a deps_array <<< "${processdeps_spec}"
    fi

    local dep any_can=0
    for dep in "${deps_array[@]}"; do
        local deptype=$(debasher::_get_deptype_part_in_dep "${dep}")
        local depproc=$(debasher::_get_processname_part_in_dep "${dep}")
        local can=0
        if [ "${deptype}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] || [ -n "${deps_ids_ref[${depproc}]:-}" ]; then
            can=1
        elif [ "${deptype}" != "${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}" ] \
                 && [ "$(debasher::_get_process_status "${dirname}" "${depproc}")" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]; then
            can=1
        fi
        if [ "${separator}" = "${DEBASHER_PROCESSDEPS_SEP_INTERR}" ]; then
            [ ${can} -eq 1 ] && any_can=1
        else
            [ ${can} -eq 0 ] && return 1
        fi
    done
    if [ "${separator}" = "${DEBASHER_PROCESSDEPS_SEP_INTERR}" ]; then
        [ ${any_can} -eq 1 ]
    fi
}

########
debasher::_map_deptype_if_necessary()
{
    local deptype=$1

    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_map_deptype_if_necessary_slurm "${deptype}"
            ;;
        *)
            echo "${deptype}"
            ;;
    esac
}


########
# Writes into the given file the context that the script of every process
# starts with: the variables and functions of the shell that calls it,
# which is debasher_exec once the program is fully defined, so that a
# process sees exactly the engine, the modules and the program that
# debasher_exec loaded (the code at the top level of a module runs once,
# in debasher_exec, and its results travel to the processes as they
# are). Left out are:
#
# - the variables that bash defines on its own, and the read-only ones,
#   which cannot be declared again;
# - the exported variables and functions, which a process inherits from
#   its own environment (on Slurm, the one of the node where it runs),
#   except PATH and the DEBASHER_* variables, which it gets as
#   debasher_exec had them;
# - the options of every task (DEBASHER_OPT_LIST_*), one array per task
#   of an array process, which the tasks read from .sched_opts instead,
#   and the scratch arrays that hold them while they are being read.
#
# The locals of this function start with _ctx_ and are left out as well.
debasher::_write_exec_context()
{
    local _ctx_fname=$1

    # Names of the variables bash defines on its own, from a bash started
    # with an empty environment
    local -A _ctx_excluded=()
    local _ctx_name
    while IFS= read -r _ctx_name; do
        _ctx_excluded["${_ctx_name}"]=1
    done < <(exec -c "${BASH}" --norc --noprofile -c 'compgen -v')

    # Read-only variables
    local _ctx_line
    while IFS= read -r _ctx_line; do
        if [[ "${_ctx_line}" =~ ^declare\ -[a-zA-Z]*\ ([A-Za-z_][A-Za-z_0-9]*) ]]; then
            _ctx_excluded["${BASH_REMATCH[1]}"]=1
        fi
    done < <(readonly -p)

    # Exported variables, but PATH and DEBASHER_*
    while IFS= read -r _ctx_name; do
        _ctx_excluded["${_ctx_name}"]=1
    done < <(compgen -A export)
    unset '_ctx_excluded[PATH]'

    # The names come from declare -p, not from compgen -v, which leaves out
    # a variable declared with no value: an associative array still empty
    # when the context is written would otherwise reach the processes as
    # an undeclared name, which bash takes for an indexed array
    local -a _ctx_vars=()
    local -A _ctx_seen=()
    local _ctx_decl_line
    while IFS= read -r _ctx_decl_line; do
        [[ "${_ctx_decl_line}" =~ ^declare\ -[-a-zA-Z]*\ ([A-Za-z_][A-Za-z_0-9]*)(=|$) ]] || continue
        _ctx_name=${BASH_REMATCH[1]}
        [[ -v _ctx_seen["${_ctx_name}"] ]] && continue
        _ctx_seen["${_ctx_name}"]=1
        case "${_ctx_name}" in
            _ctx_*|DEBASHER_OPT_LIST_*|DEBASHER_CURRENT_PROCESS_OPT_LIST|DEBASHER_DESERIALIZED_ARGS)
                continue
                ;;
            DEBASHER_*)
                ;;
            *)
                [[ -v _ctx_excluded["${_ctx_name}"] ]] && continue
                ;;
        esac
        # A line of a value that spans several lines could look like a
        # declaration of its own: only a name that is declared counts
        declare -p "${_ctx_name}" > /dev/null 2>&1 || continue
        _ctx_vars+=("${_ctx_name}")
    done < <(declare -p)

    # Functions, but the exported ones
    local -a _ctx_funcs=()
    local _ctx_decl _ctx_attrs
    while read -r _ctx_decl _ctx_attrs _ctx_name; do
        [[ "${_ctx_attrs}" == *x* ]] && continue
        _ctx_funcs+=("${_ctx_name}")
    done < <(declare -F)

    {
        declare -p "${_ctx_vars[@]}" || return 1
        declare -f "${_ctx_funcs[@]}" || return 1
    } > "${_ctx_fname}"
}

########
# Writes the context of a process script (see debasher::_write_exec_context)
debasher::_write_env_vars_and_funcs()
{
    local dirname=$1

    "${CAT}" "$(debasher::_get_exec_context_fname "${dirname}")"
}

########
# Public: Runs a function or command as a step: from the process
# function of a task, it runs it, waits for it to end and returns an
# error if it fails.
#
# Under the built-in scheduler the function runs in the shell of the
# task; under the Slurm scheduler it runs as a job step through srun
# (see seq_execute_slurm), with the computational specifications of
# the function when it is a sequential process (see
# add_debasher_seq_process). The step reads the standard input of the
# call, so a step inside a loop that reads its standard input takes
# its own from /dev/null.
#
# $1 - Function or command to execute.
# $2.. - Its arguments, passed as they are given.
#
# Examples
#
#   seq_execute transform "${value}" "${outd}/result.txt" < /dev/null
#
# Returns 1 if the step failed or could not be launched.
debasher::seq_execute()
{
    local sched=$(debasher::_get_scheduler)

    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::seq_execute_slurm "$@"
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_seq_execute_builtin "$@"
            ;;
        *)
            local process_to_launch=$1
            # Execute process
            shift
            "${process_to_launch}" "$@" || return 1
            ;;
    esac
}

########
# Public: Runs a function or command as a step: from the process
# function of a task, it runs it, waits for it to end and returns an
# error if it fails.
#
# Under the built-in scheduler the function runs in the shell of the
# task; under the Slurm scheduler it runs as a job step through srun
# (see seq_execute_slurm), with the computational specifications of
# the function when it is a sequential process (see
# add_debasher_seq_process). The step reads the standard input of the
# call, so a step inside a loop that reads its standard input takes
# its own from /dev/null.
#
# $1 - Function or command to execute.
# $2.. - Its arguments, passed as they are given.
#
# Examples
#
#   seq_execute transform "${value}" "${outd}/result.txt" < /dev/null
#
# Returns 1 if the step failed or could not be launched.
seq_execute() { debasher::seq_execute "$@"; }

########
# Public: Marks a step as done, by creating its step marker, an empty
# file named after the id of the step in the given directory.
#
# The engine never reads a step marker: a process that wants to skip
# the steps that an earlier run finished checks them itself with
# is_step_done. The marker is created atomically, so that of two
# callers that mark the same step only one succeeds.
#
# $1 - Directory of the step marker.
# $2 - Id of the step, unique within the directory.
#
# Examples
#
#   debasher::mark_step_done "${outd}" "${id}_${base}"
#
# Returns 1 if the marker could not be created or already existed.
debasher::mark_step_done()
{
    local dir="$1"
    local id="$2"

    if ( set -o noclobber; : > "$dir/${DEBASHER_STEP_MARKER_PREFIX}${id}" ) 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

########
# Public: Marks a step as done, by creating its step marker (see
# debasher::mark_step_done). The engine never reads a step marker: a
# process that wants to skip the steps that an earlier run finished
# checks them itself with is_step_done.
#
# $1 - Directory of the step marker.
# $2 - Id of the step, unique within the directory.
#
# Examples
#
#   mark_step_done "${outd}" "${id}_${base}_${checksum}"
#
# Returns 1 if the marker could not be created or already existed.
mark_step_done() { debasher::mark_step_done "$@"; }

########
# Public: Tells whether a step has been marked as done with
# mark_step_done.
#
# $1 - Directory of the step marker.
# $2 - Id of the step.
#
# Returns 0 if the step marker exists, 1 otherwise.
debasher::is_step_done()
{
    local dir="$1"
    local id="$2"

    [ -e "$dir/${DEBASHER_STEP_MARKER_PREFIX}${id}" ]
}

########
# Public: Tells whether a step has been marked as done with
# mark_step_done.
#
# $1 - Directory of the step marker.
# $2 - Id of the step.
#
# Examples
#
#   is_step_done "${outd}" "${id}_${base}_${checksum}" || seq_execute work "${base}"
#
# Returns 0 if the step marker exists, 1 otherwise.
is_step_done() { debasher::is_step_done "$@"; }

########
debasher::_format_elapsed_time()
{
    local elapsed_ms=$1
    printf "%d.%03d" \
        $((elapsed_ms / 1000)) \
        $((elapsed_ms % 1000))
}

########
debasher::_get_elapsed_time_from_logfile()
{
    local log_filename=$1
    local start_date=$(debasher::_get_process_start_date "${log_filename}")
    local finish_date=$(debasher::_get_process_finish_date "${log_filename}")

    local elapsed_ms
    if [ -n "${start_date}" ] && [ -n "${finish_date}" ] \
        && elapsed_ms=$(debasher::_datetime_diff_ms "${start_date}" "${finish_date}"); then
        debasher::_format_elapsed_time "${elapsed_ms}"
    else
        echo "${DEBASHER_UNKNOWN_ELAPSED_TIME_FOR_PROCESS}"
    fi
}

########
# Converts an elapsed time as debasher::_format_elapsed_time writes it
# (seconds, a dot and three digits of milliseconds) into milliseconds.
# Fails for anything else, such as an unknown elapsed time.
debasher::_elapsed_time_to_ms()
{
    local elapsed=$1

    if [[ ! "${elapsed}" =~ ^([0-9]+)\.([0-9]{3})$ ]]; then
        return 1
    fi
    echo $(( 10#${BASH_REMATCH[1]} * 1000 + 10#${BASH_REMATCH[2]} ))
}

########
# Prints the elapsed time of the finished tasks of an array process as
# "<total> : <idx>-><time> ; <idx>-><time> ; ...", where the total is the
# sum of the times of the tasks, or unknown when the time of any of them
# is. The log of each task is the one printed by the function named in
# $3, called with the output directory, the process name and the task
# index, since each scheduler keeps it in its own place.
debasher::_get_elapsed_time_for_array_process()
{
    local dirname=$1
    local processname=$2
    local task_logf_funcname=$3

    local result=""
    local total_ms=0
    local total_known=1
    local taskidx
    for taskidx in $(debasher::_get_finished_array_task_indices "${dirname}" ${processname}); do
        local log_filename=$("${task_logf_funcname}" "${dirname}" "${processname}" "${taskidx}")
        local difft=$(debasher::_get_elapsed_time_from_logfile "${log_filename}")
        local difft_ms
        if difft_ms=$(debasher::_elapsed_time_to_ms "${difft}"); then
            total_ms=$((total_ms + difft_ms))
        else
            total_known=0
        fi
        if [ -n "${result}" ]; then
            result="${result} "
        fi
        result="${result}${taskidx}->${difft} ;"
    done

    local total=${DEBASHER_UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
    if [ ${total_known} -eq 1 ]; then
        total=$(debasher::_format_elapsed_time "${total_ms}")
    fi
    echo "${total} : ${result}"
}

########
debasher::_get_elapsed_time_for_process()
{
    local dirname=$1
    local processname=$2

    # Get name of log file
    local sched=$(debasher::_get_scheduler)
    local log_filename
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_get_elapsed_time_for_process_slurm "${dirname}" "${processname}"
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_get_elapsed_time_for_process_builtin "${dirname}" "${processname}"
            ;;
    esac
}
