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
#
# The graceful counterpart to debasher_stop, for a resident program (see
# "`debasher_stop_resident`" in doc/design_doc_resident.md). Where
# debasher_stop ends a program at once (SIGKILL, no coordination), this one
# records the halted marker baseline of every node, kills the nodes of
# --kill, stops the Supervisor if the program has one, so that it cannot
# relaunch a node under the rest of this, asks every node to close a round
# (a halt), waits until the halted marker of each goes past its baseline,
# and only then stops it (SIGTERM to its whole process group). If that does
# not end within --timeout, it falls back to debasher_stop on the whole
# program.
#
# Exit codes: 0 is a clean, fully graceful stop; 1 is a usage or setup error
# (bad arguments, a directory that is not a resident program's, a name of
# -x or --kill that is no node, and the like); 2
# (DEBASHER_STOP_RESIDENT_FORCED_EXIT) means the graceful attempt did not
# finish and this fell back to debasher_stop's hard kill: the program did
# end, but not gracefully, and a caller that cares (the web UI, in
# particular) tells the two apart by this exit code. The warning written
# before the fallback says the same on stderr; it is the only trace of it
# that the escalation of a Supervisor leaves, since the fallback kills that
# Supervisor too.

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_lib_resident_tools || exit 1

DEBASHER_STOP_RESIDENT_FORCED_EXIT=2

########
print_desc()
{
    echo "debasher_stop_resident gracefully stops a resident program"
    echo "type \"debasher_stop_resident --help\" to get usage information"
}

########
usage()
{
    echo "debasher_stop_resident    -d <string> [-x <string>] [--kill <string>]"
    echo "                          [--timeout <int>] [--keep-supervisor] [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-x <string>               Comma-separated nodes to leave alone: a process"
    echo "                          name (every task, if it is an array) or"
    echo "                          <process>:<idx> (one task of an array)"
    echo "--kill <string>           Comma-separated nodes to kill (SIGKILL to the"
    echo "                          process group of each, if it still runs)"
    echo "                          before the graceful stop, named as for -x;"
    echo "                          usually also given to -x"
    echo "--timeout <int>           Seconds to wait for a clean stop before"
    echo "                          falling back to debasher_stop (default: 60)"
    echo "--keep-supervisor         Do not stop the program's Supervisor, if it"
    echo "                          has one (for a Supervisor calling this tool"
    echo "                          on itself; leaving it running is what lets"
    echo "                          it resolve on its own once every node it"
    echo "                          still watches is done)"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    excluded_csv=""
    killed_csv=""
    timeout_secs=60
    keep_supervisor=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 0
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-x") shift
                  if [ $# -ne 0 ]; then
                      excluded_csv=$1
                  fi
                  ;;
            "--kill") shift
                  if [ $# -ne 0 ]; then
                      killed_csv=$1
                  fi
                  ;;
            "--timeout") shift
                  if [ $# -ne 0 ]; then
                      timeout_secs=$1
                  fi
                  ;;
            "--keep-supervisor") keep_supervisor=1
                  ;;
            *) echo "Error! unknown option $1" >&2
               exit 1
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
        if [ ! -d "${pdir}" ]; then
            echo "Error! program directory does not exist" >&2
            exit 1
        fi

        if [ ! -f "${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}" ]; then
            echo "Error! ${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME} file is missing" >&2
            exit 1
        fi
    fi

    if ! debasher::_str_is_positive_integer "${timeout_secs}"; then
        echo "Error! --timeout must be a positive number of seconds" >&2
        exit 1
    fi
}

########
# Prints the halted marker baseline of the halted marker at $1: its
# content, or -1 if it does not exist yet (never a real epoch, see
# _write_halted_marker in engine/debasher_runtime_fbp.py).
read_halted_marker_or_baseline()
{
    local path=$1
    if [ -f "${path}" ]; then
        "${CAT}" "${path}" 2>/dev/null
    else
        echo "-1"
    fi
}

########
# Waits until the halted marker at $1 holds an epoch past its baseline $2,
# or the deadline $3 passes.
wait_for_fresh_halted_marker()
{
    local path=$1
    local baseline=$2
    local deadline=$3
    local current
    while :; do
        if [ -f "${path}" ]; then
            current=$("${CAT}" "${path}" 2>/dev/null)
            if [ -n "${current}" ] && [ "${current}" -gt "${baseline}" ] 2>/dev/null; then
                return 0
            fi
        fi
        if [ "$(debasher::_resident_tool_now_secs)" -ge "${deadline}" ]; then
            return 1
        fi
        "${SLEEP}" 0.2
    done
}

########
# Prints the PID of the process of node $2, in the output directory $1, as
# its .id names it, if that process still runs. Returns 1 with no .id, an
# empty one, or one whose task has ended.
read_running_pid_of_node()
{
    local absdirname=$1
    local node=$2

    local id_file id_info
    id_file=$(debasher::_resident_tool_node_id_filename "${absdirname}" "${node}")
    [ -f "${id_file}" ] || return 1
    id_info=$("${CAT}" "${id_file}" 2>/dev/null)
    [ -n "${id_info}" ] || return 1
    # The start time in the id keeps a process that got the PID of an ended
    # task from being taken for it
    debasher::_builtin_sched_get_running_task_pid "${id_info}"
}

########
# Sends the whole process group of node $2, in the output directory $1, a
# graceful stop signal (see debasher::_stop_pid_gracefully), if its process
# still runs (see read_running_pid_of_node); otherwise there is nothing to
# stop.
stop_node_gracefully()
{
    local absdirname=$1
    local node=$2

    local pid
    pid=$(read_running_pid_of_node "${absdirname}" "${node}") || return 0
    debasher::_stop_pid_gracefully "${pid}"
}

########
# Stops the Supervisor $2 of the program in the output directory $1, if
# there is one, with a graceful signal to its process group, and waits for
# its .finished until the deadline $4. Does nothing with no Supervisor, with
# $3 (keep_supervisor) set to 1, or with a .finished already there; warns
# and goes on if it does not run. Returns 1, with an error, if its
# .finished does not come in time.
stop_supervisor_if_any()
{
    local absdirname=$1
    local supervisor=$2
    local keep_supervisor=$3
    local deadline=$4

    # --keep-supervisor is for the escalation of a Supervisor, which runs
    # this tool on a thread of its own and ends by itself once the nodes are
    # done (see "Escalation on a permanent node failure" in the design doc)
    if [ -z "${supervisor}" ] || [ "${keep_supervisor}" -eq 1 ]; then
        return 0
    fi

    local finished_file
    finished_file=$(debasher::_get_process_finished_filename "${absdirname}" "${supervisor}")
    [ ! -f "${finished_file}" ] || return 0

    # A Supervisor that is gone relaunches nothing, and its .finished would
    # never come
    local pid
    if ! pid=$(read_running_pid_of_node "${absdirname}" "${supervisor}"); then
        echo "Warning: ${supervisor} (the Supervisor) is not running" >&2
        return 0
    fi
    debasher::_stop_pid_gracefully "${pid}"

    if ! debasher::_resident_tool_wait_for_file "${finished_file}" "${deadline}"; then
        echo "Error: ${supervisor} (the Supervisor) never exited cleanly after a stop signal" >&2
        return 1
    fi
}

########
# Records the halted marker baseline of each node of the array named $2,
# in the output directory $1, into the associative array named $3, keyed
# by node: the content of its halted marker, or -1 without one. The marker
# outlives the incarnation that wrote it, so only a marker past its
# baseline belongs to this halt. Called before anything triggers a round:
# read after it, a node whose round closed fast enough (a single idle node
# closes its round in well under that time) would show its fresh marker as
# the baseline, and the wait for it would last until the deadline.
capture_halted_marker_baselines()
{
    local absdirname=$1
    local -n captured_nodes_ref=$2
    local -n captured_baselines_ref=$3

    captured_baselines_ref=()
    local node
    for node in "${captured_nodes_ref[@]}"; do
        captured_baselines_ref["${node}"]=$(read_halted_marker_or_baseline "$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" halted)")
    done
}

########
# Waits until the halted marker of each node of the array named $2, in the
# output directory $1, goes past its baseline in the associative array
# named $3 (see wait_for_fresh_halted_marker), or the deadline $4 passes.
# Every node, not only initiators, since a halt round closes at every node
# the marker reaches, not just where it started.
wait_for_every_halted_marker()
{
    local absdirname=$1
    local -n waited_nodes_ref=$2
    local -n waited_baselines_ref=$3
    local deadline=$4

    local node marker_file
    for node in "${waited_nodes_ref[@]}"; do
        marker_file=$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" halted)
        if ! wait_for_fresh_halted_marker "${marker_file}" "${waited_baselines_ref[${node}]}" "${deadline}"; then
            echo "Error: ${node} never marked itself halted" >&2
            return 1
        fi
    done
}

########
# Signals every node of the array named $2, in the output directory $1,
# then waits for every one's own .finished until the deadline $3. Reads
# each .id file again here, not reusing anything read earlier: with the
# Supervisor already stopped (see stop_supervisor_if_any), nothing
# should relaunch a node between the wait above and this, but reading it
# fresh costs nothing and does not depend on that holding.
stop_every_node_and_wait_for_finished()
{
    local absdirname=$1
    local -n stopped_nodes_ref=$2
    local deadline=$3

    local node
    for node in "${stopped_nodes_ref[@]}"; do
        stop_node_gracefully "${absdirname}" "${node}"
    done

    local finished_file
    for node in "${stopped_nodes_ref[@]}"; do
        finished_file=$(debasher::_resident_tool_node_finished_filename "${absdirname}" "${node}")
        if ! debasher::_resident_tool_wait_for_file "${finished_file}" "${deadline}"; then
            echo "Error: ${node} never exited cleanly after a stop signal" >&2
            return 1
        fi
    done
}

########
# Kills, with SIGKILL to its whole process group (debasher::_stop_pid), the
# process of each node of the array named $2, in the output directory $1,
# that still runs; a node with no .id, or whose task has ended, is left as
# it is. For a node that cannot halt and may still hang, such as one that
# the Supervisor gave up on in its startup: a graceful stop leaves it alone
# (-x), and nothing else would end it.
kill_nodes()
{
    local absdirname=$1
    local -n killed_nodes_ref=$2

    local node pid
    for node in "${killed_nodes_ref[@]}"; do
        pid=$(read_running_pid_of_node "${absdirname}" "${node}") || continue
        debasher::_stop_pid "${pid}"
    done
}

########
# Stops the resident program whose output directory is $1, leaving out the
# nodes of the comma-separated list $2 (-x) and killing first those of $3
# (--kill), within $4 seconds (--timeout), and leaving its Supervisor
# running if $5 (--keep-supervisor) is 1. Prints that every node stopped
# cleanly and returns 0, or falls back to debasher_stop and returns
# DEBASHER_STOP_RESIDENT_FORCED_EXIT. Returns 1, with an error, on a program
# it cannot load or that is not a resident one, on a name that is no node,
# or on nodes that it cannot find.
stop_resident_program()
{
    local dirname=$1
    local excluded_csv=$2
    local killed_csv=$3
    local timeout_secs=$4
    local keep_supervisor=$5
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    debasher::_resident_tool_load_program "${absdirname}" debasher_stop_resident || return 1

    # One deadline for every step
    local deadline=$(( $(debasher::_resident_tool_now_secs) + timeout_secs ))

    # Every name checked before anything is touched
    local -a excluded_nodes=() killed_nodes=()
    debasher::_resident_tool_resolve_node_names "${absdirname}" "${excluded_csv}" "${deadline}" excluded_nodes || return 1
    debasher::_resident_tool_resolve_node_names "${absdirname}" "${killed_csv}" "${deadline}" killed_nodes || return 1

    local supervisor
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${absdirname}" "${excluded_csv}" "${deadline}" supervisor nodes || return 1
    # The baselines first, before anything that could make a node halt
    local -A baselines=()
    capture_halted_marker_baselines "${absdirname}" nodes baselines

    kill_nodes "${absdirname}" killed_nodes

    # The trigger is numbered with the time in milliseconds, as the
    # Supervisor numbers those it relays: no state is kept between calls,
    # and it stays above the epochs that initiators number themselves.
    # Every initiator opens its round with that one number, so a node that
    # the rounds of several initiators reach waits for markers of one epoch.
    # A step that fails ends the chain in the fallback below
    if stop_supervisor_if_any "${absdirname}" "${supervisor}" "${keep_supervisor}" "${deadline}" \
        && debasher::_resident_tool_trigger_every_node "${absdirname}" nodes shutdown "$(debasher::_now_ms)" "${deadline}" \
        && wait_for_every_halted_marker "${absdirname}" nodes baselines "${deadline}" \
        && stop_every_node_and_wait_for_finished "${absdirname}" nodes "${deadline}"
    then
        echo "Every node of ${dirname} stopped cleanly."
        return 0
    fi

    echo "Warning: could not stop ${dirname} gracefully within ${timeout_secs}s, forcing debasher_stop" >&2
    "${debasher_bindir}/debasher_stop" -d "${dirname}"
    # Always DEBASHER_STOP_RESIDENT_FORCED_EXIT here, not debasher_stop's own
    # exit code (typically 0: it does not treat "something was still running
    # to kill" as a failure): this is the one signal a caller redirecting
    # stderr can still see, see this file's own header comment.
    return "${DEBASHER_STOP_RESIDENT_FORCED_EXIT}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

stop_resident_program "${pdir}" "${excluded_csv}" "${killed_csv}" "${timeout_secs}" "${keep_supervisor}"

exit $?
