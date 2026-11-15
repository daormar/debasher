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
# asks every node to close a round first (a halt), waits until each one has
# (its own halted marker, see the design doc's Glossary), and only then stops
# it (SIGTERM to its whole process group, same as debasher_stop reaches with
# SIGKILL); if a node never gets there within --timeout, it falls back to
# debasher_stop on the whole program. If the program has a Supervisor, that is
# stopped first, the same graceful way, so it cannot relaunch a node out from
# under the rest of this.
#
# Exit codes: 0 is a clean, fully graceful stop; 1 is a usage or setup error
# (bad arguments, a directory that is not a resident program's, and the
# like); 2 (DEBASHER_STOP_RESIDENT_FORCED_EXIT) means the graceful attempt
# did not finish within --timeout and this fell back to debasher_stop's hard
# kill, which itself is not treated as an error here (it is, by design, a
# "just end it" backstop that always succeeds if anything is left running):
# the program did end, but not gracefully, and a caller that cares about
# that distinction (the web UI, in particular) tells the two apart by this
# exit code. The warning written before the fallback says the same on
# stderr; it is the only trace of it that the escalation of a Supervisor
# leaves, since the fallback kills that Supervisor too.

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
}

########
# The content of a node's halted marker, or -1 if it does not exist yet
# (never a real epoch, see engine/debasher_runtime_fbp.py's
# _write_halted_marker): the baseline this tool compares a fresh one
# against, so a marker left over from an earlier, already-resumed halt of
# this same node is never mistaken for this run's own.
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
# Waits until the halted marker at $1 holds an integer strictly greater
# than the baseline $2, or the deadline $3 passes.
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
# If the program has a Supervisor, stops it (graceful signal to its own
# process group) and waits for its .finished to appear, so it is
# confirmed gone, not just signalled, before anything else here touches a
# node it could otherwise still relaunch. A no-op, returning success at
# once, if the program has none, or if --keep-supervisor was given: that
# flag is for a Supervisor calling this tool on itself (its own escalation
# after a permanent node failure, see the design doc's "Escalation on a
# permanent node failure"), where stopping it here would be self-defeating
# twice over. First, that Supervisor is blocked, on a thread of its own, on
# this very tool call returning: a graceful stop waits for its .finished,
# which cannot appear until that thread unblocks, which cannot happen until
# this tool returns, a deadlock this tool's own --timeout only escapes by
# giving up on grace entirely, into debasher_stop's hard kill, every single
# time; running the tool in a session of its own does not change it, since
# the Supervisor is found by the PID in its .id. Second, even without that
# deadlock, killing the Supervisor here is premature on its own terms: it
# already resolves itself, on its own, once every node it still watches is
# either done or given up on (see "Clean-completion detection"), which is
# exactly what stopping the other, reachable nodes below is for.
stop_supervisor_if_any()
{
    local absdirname=$1
    local supervisor=$2
    local deadline=$3

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
stop_resident_program()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    debasher::_resident_tool_load_program "${absdirname}" debasher_stop_resident || return 1

    local deadline=$(( $(debasher::_resident_tool_now_secs) + timeout_secs ))

    # Every name checked before anything is touched
    local -a excluded_nodes=() killed_nodes=()
    debasher::_resident_tool_resolve_node_names "${absdirname}" "${excluded_csv}" "${deadline}" excluded_nodes || return 1
    debasher::_resident_tool_resolve_node_names "${absdirname}" "${killed_csv}" "${deadline}" killed_nodes || return 1

    local supervisor
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${absdirname}" "${excluded_csv}" "${deadline}" supervisor nodes || return 1
    local -A baselines=()
    capture_halted_marker_baselines "${absdirname}" nodes baselines

    kill_nodes "${absdirname}" killed_nodes

    # The trigger is numbered with the time in milliseconds, as the
    # Supervisor numbers those it relays: no state is kept between calls,
    # and it stays above the epochs that initiators number themselves.
    # Every initiator opens its round with that one number, so a node that
    # the rounds of several initiators reach waits for markers of one epoch.
    if stop_supervisor_if_any "${absdirname}" "${supervisor}" "${deadline}" \
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

stop_resident_program "${pdir}"

exit $?
