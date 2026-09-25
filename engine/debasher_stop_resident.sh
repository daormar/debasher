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
# The graceful counterpart to debasher_stop, for a resident program (design
# doc doc/design_doc_resident.md, Conformance status, G2's third fix
# candidate). Where debasher_stop ends a program at once (SIGKILL, no
# coordination), this one asks every node to close a round first (a halt),
# waits until each one has (its own halted marker, see the design doc's
# Glossary), and only then stops it (SIGTERM to its whole process group,
# same as debasher_stop reaches with SIGKILL); if a node never gets there
# within --timeout, it falls back to debasher_stop on the whole program. If
# the program has a Supervisor, that is stopped first, the same graceful
# way, so it cannot relaunch a node out from under the rest of this.
#
# Exit codes: 0 is a clean, fully graceful stop; 1 is a usage or setup error
# (bad arguments, a directory that is not a resident program's, and the
# like); 2 (DEBASHER_STOP_RESIDENT_FORCED_EXIT) means the graceful attempt
# did not finish within --timeout and this fell back to debasher_stop's hard
# kill, which itself is not treated as an error here (it is, by design, a
# "just end it" backstop that always succeeds if anything is left running):
# the program did end, but not gracefully, and a caller that cares about
# that distinction (Supervisor's own escalation, in particular, since a
# graceful stop and a forced one both end the program the same way from the
# outside) must tell the two apart by this exit code, not by the warning
# below, which a caller redirecting stderr would never see.

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
    echo "debasher_stop_resident    -d <string> [-x <string>]"
    echo "                          [--timeout <int>] [--keep-supervisor] [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-x <string>               Comma-separated nodes to leave alone: a process"
    echo "                          name (every task, if it is an array) or"
    echo "                          <process>:<idx> (one task of an array)"
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
# Reads a node's own .id file and sends its whole process group a
# graceful stop signal (see debasher::_stop_pid_gracefully). A missing or
# empty .id file (never launched, or already gone) is not an error: there
# is nothing to stop.
stop_node_gracefully()
{
    local absdirname=$1
    local node=$2
    local id_file
    id_file=$(debasher::_resident_tool_node_id_filename "${absdirname}" "${node}")
    if [ ! -f "${id_file}" ]; then
        return 0
    fi
    local pid
    pid=$("${CAT}" "${id_file}" 2>/dev/null)
    if [ -z "${pid}" ]; then
        return 0
    fi
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
# twice over. First, the signal targets the same process group the calling
# Python interpreter already runs in, and that interpreter is blocked, on
# a thread of its own, on this very tool call returning: a graceful stop
# waits for its .finished, which cannot appear until that thread
# unblocks, which cannot happen until this tool returns, a deadlock this
# tool's own --timeout only escapes by giving up on grace entirely, into
# debasher_stop's hard kill, every single time. Second, even without that
# deadlock, killing the Supervisor here is premature on its own terms: it
# already resolves itself, on its own, once every node it still watches is
# either done or given up on (see "Clean-completion detection"), which is
# exactly what stopping the other, reachable nodes below is for.
stop_supervisor_if_any()
{
    local absdirname=$1
    local deadline=$2

    if [ -z "${DEBASHER_RESIDENT_TOOL_SUPERVISOR}" ] || [ "${keep_supervisor}" -eq 1 ]; then
        return 0
    fi

    stop_node_gracefully "${absdirname}" "${DEBASHER_RESIDENT_TOOL_SUPERVISOR}"

    local finished_file
    finished_file=$(debasher::_get_process_finished_filename "${absdirname}" "${DEBASHER_RESIDENT_TOOL_SUPERVISOR}")
    if ! debasher::_resident_tool_wait_for_file "${finished_file}" "${deadline}"; then
        echo "Error: ${DEBASHER_RESIDENT_TOOL_SUPERVISOR} (the Supervisor) never exited cleanly after a stop signal" >&2
        return 1
    fi
}

########
# Records, for every node, its halted marker's content right now (-1 if
# it does not exist yet), into the global HALTED_MARKER_BASELINE, before
# anything triggers a round: read after triggering instead, a node whose
# round closes fast enough could already show its fresh marker by the
# time this runs, making it look like the baseline itself, and
# wait_for_every_halted_marker would then wait forever for a second halt
# that is never coming (found with a real debasher_exec run, 2026-09-22:
# a single, otherwise idle node closed its round in well under the time
# this function used to take to get around to reading it).
capture_halted_marker_baselines()
{
    local absdirname=$1

    declare -gA HALTED_MARKER_BASELINE=()
    local node
    for node in "${DEBASHER_RESIDENT_TOOL_NODES[@]}"; do
        HALTED_MARKER_BASELINE["${node}"]=$(read_halted_marker_or_baseline "$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" halted)")
    done
}

########
# Waits for every node's halted marker to go beyond the baseline
# capture_halted_marker_baselines recorded before the trigger was sent
# (see wait_for_fresh_halted_marker): every node, not only initiators,
# since a halt round closes at every node the marker reaches, not just
# where it started.
wait_for_every_halted_marker()
{
    local absdirname=$1
    local deadline=$2

    local node marker_file
    for node in "${DEBASHER_RESIDENT_TOOL_NODES[@]}"; do
        marker_file=$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" halted)
        if ! wait_for_fresh_halted_marker "${marker_file}" "${HALTED_MARKER_BASELINE[${node}]}" "${deadline}"; then
            echo "Error: ${node} never marked itself halted" >&2
            return 1
        fi
    done
}

########
# Signals every node, then waits for every one's own .finished. Reads
# each .id file again here, not reusing anything read earlier: with the
# Supervisor already stopped (see stop_supervisor_if_any), nothing
# should relaunch a node between the wait above and this, but reading it
# fresh costs nothing and does not depend on that holding.
stop_every_node_and_wait_for_finished()
{
    local absdirname=$1
    local deadline=$2

    local node
    for node in "${DEBASHER_RESIDENT_TOOL_NODES[@]}"; do
        stop_node_gracefully "${absdirname}" "${node}"
    done

    local finished_file
    for node in "${DEBASHER_RESIDENT_TOOL_NODES[@]}"; do
        finished_file=$(debasher::_resident_tool_node_finished_filename "${absdirname}" "${node}")
        if ! debasher::_resident_tool_wait_for_file "${finished_file}" "${deadline}"; then
            echo "Error: ${node} never exited cleanly after a stop signal" >&2
            return 1
        fi
    done
}

########
stop_resident_program()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    debasher::_resident_tool_load_program "${absdirname}" debasher_stop_resident || return 1

    local deadline=$(( $(debasher::_resident_tool_now_secs) + timeout_secs ))

    debasher::_resident_tool_find_supervisor_and_nodes "${absdirname}" "${excluded_csv}" "${deadline}" || return 1
    capture_halted_marker_baselines "${absdirname}"

    if stop_supervisor_if_any "${absdirname}" "${deadline}" \
        && debasher::_resident_tool_trigger_every_node "${absdirname}" shutdown "$(debasher::_resident_tool_now_ms)" "${deadline}" \
        && wait_for_every_halted_marker "${absdirname}" "${deadline}" \
        && stop_every_node_and_wait_for_finished "${absdirname}" "${deadline}"
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
