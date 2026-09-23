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
    echo "-x <string>               Comma-separated process names to leave alone"
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
configure_scheduler()
{
    local sched=$1
    if [ ${sched} = ${DEBASHER_OPT_NOT_FOUND} ]; then
        # If the scheduler was not set in the command line, it is
        # automatically determined
        local sched=$(debasher::_determine_scheduler)
        debasher::_set_debasher_scheduler "${sched}" || return 1
    else
        debasher::_set_debasher_scheduler "${sched}" || return 1
    fi
}

########
now_epoch()
{
    date +%s
}

########
# Waits until $1 (a file path) exists, or $2 (an epoch second) passes.
wait_for_file()
{
    local path=$1
    local deadline=$2
    while [ ! -e "${path}" ]; do
        if [ "$(now_epoch)" -ge "${deadline}" ]; then
            return 1
        fi
        sleep 0.2
    done
    return 0
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
        if [ "$(now_epoch)" -ge "${deadline}" ]; then
            return 1
        fi
        sleep 0.2
    done
}

########
# Reads a process's own .id file and sends its whole process group a
# graceful stop signal (see debasher::_stop_pid_gracefully). A missing or
# empty .id file (never launched, or already gone) is not an error: there
# is nothing to stop.
stop_processname_gracefully()
{
    local absdirname=$1
    local processname=$2
    local id_file
    id_file=$(debasher::_get_processid_filename "${absdirname}" "${processname}")
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
# Populates SUPERVISOR_PROCESSNAME (empty if the program has none) and
# NODE_PROCESSNAMES (every other process, minus $1's comma-separated
# names, if any) from DEBASHER_PROGRAM_PROCESSES, already populated by
# the caller. Reuses debasher::_classify_resident_process_role, the same
# classifier debasher::_validate_resident_program_processes already uses,
# rather than reinventing it here.
find_supervisor_and_nodes()
{
    local excluded_csv=$1

    local -A excluded=()
    if [ -n "${excluded_csv}" ]; then
        # IFS=... read, not "local IFS=,": local only scopes a variable to
        # this function, not to the one statement that needs the comma as
        # a separator, and a leaked IFS of "," broke word-splitting in
        # every function called afterwards, including
        # debasher::_classify_resident_process_role below (found with a
        # real debasher_exec run, 2026-09-22).
        local -a names=()
        IFS=',' read -ra names <<< "${excluded_csv}"
        local name
        for name in "${names[@]}"; do
            excluded["${name}"]=1
        done
    fi

    SUPERVISOR_PROCESSNAME=""
    NODE_PROCESSNAMES=()

    local processname role
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        role=$(debasher::_classify_resident_process_role "${processname}") || {
            echo "Error: cannot classify process ${processname} (not a resident program?)" >&2
            return 1
        }
        case "${role}" in
            supervisor)
                if [ -n "${SUPERVISOR_PROCESSNAME}" ]; then
                    echo "Error: a resident program can have at most one Supervisor process, but both ${SUPERVISOR_PROCESSNAME} and ${processname} are" >&2
                    return 1
                fi
                SUPERVISOR_PROCESSNAME="${processname}"
                ;;
            fbpprocess)
                if [ -z "${excluded[${processname}]+x}" ]; then
                    NODE_PROCESSNAMES+=("${processname}")
                fi
                ;;
            *)
                echo "Error: process ${processname} does not derive from FBPProcess or Supervisor" >&2
                return 1
                ;;
        esac
    done
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

    if [ -z "${SUPERVISOR_PROCESSNAME}" ] || [ "${keep_supervisor}" -eq 1 ]; then
        return 0
    fi

    stop_processname_gracefully "${absdirname}" "${SUPERVISOR_PROCESSNAME}"

    local finished_file
    finished_file=$(debasher::_get_process_finished_filename "${absdirname}" "${SUPERVISOR_PROCESSNAME}")
    if ! wait_for_file "${finished_file}" "${deadline}"; then
        echo "Error: ${SUPERVISOR_PROCESSNAME} (the Supervisor) never exited cleanly after a stop signal" >&2
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
    local processname execdir
    for processname in "${NODE_PROCESSNAMES[@]}"; do
        execdir=$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")
        HALTED_MARKER_BASELINE["${processname}"]=$(read_halted_marker_or_baseline "${execdir}/halted")
    done
}

########
# The shutdown trigger, numbered with the epoch $1: every initiator that
# gets it opens its halt with that same number, so a node that the halts
# of several initiators reach waits for markers of one epoch, not of
# several.
shutdown_interact_json()
{
    local epoch=$1
    echo "{\"type\": \"INTERACT\", \"payload\": {\"command\": \"shutdown\", \"args\": {\"epoch\": ${epoch}}}}"
}

########
# Writes the shutdown trigger into every node's own control ports (an
# initiator's own; most nodes have none, and the round reaches them from
# elsewhere in the graph, see the design doc's Glossary entry for
# "control ports file"). Waits (briefly, against the overall deadline)
# for a node that has not written its control_ports file yet, rather than
# giving up on it at once: a program can still be starting up when this
# runs. The epoch is the time in milliseconds, the same numbering a
# Supervisor uses for the triggers it relays: it needs no state kept
# between calls and stays above the epochs that initiators number
# themselves.
trigger_shutdown_for_all_nodes()
{
    local absdirname=$1
    local deadline=$2

    local shutdown_json
    shutdown_json=$(shutdown_interact_json "$(date +%s%3N)")

    local processname execdir cp_file fifo
    for processname in "${NODE_PROCESSNAMES[@]}"; do
        execdir=$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")
        cp_file="${execdir}/control_ports"
        if ! wait_for_file "${cp_file}" "${deadline}"; then
            echo "Error: ${processname} never wrote its control_ports file" >&2
            return 1
        fi
        while IFS= read -r fifo; do
            [ -n "${fifo}" ] || continue
            if ! timeout 5 bash -c 'echo "$1" > "$2"' _ "${shutdown_json}" "${fifo}"; then
                echo "Error: could not write the shutdown trigger to ${fifo}" >&2
                return 1
            fi
        done < "${cp_file}"
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

    local processname execdir marker_file
    for processname in "${NODE_PROCESSNAMES[@]}"; do
        execdir=$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")
        marker_file="${execdir}/halted"
        if ! wait_for_fresh_halted_marker "${marker_file}" "${HALTED_MARKER_BASELINE[${processname}]}" "${deadline}"; then
            echo "Error: ${processname} never marked itself halted" >&2
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

    local processname
    for processname in "${NODE_PROCESSNAMES[@]}"; do
        stop_processname_gracefully "${absdirname}" "${processname}"
    done

    local finished_file
    for processname in "${NODE_PROCESSNAMES[@]}"; do
        finished_file=$(debasher::_get_process_finished_filename "${absdirname}" "${processname}")
        if ! wait_for_file "${finished_file}" "${deadline}"; then
            echo "Error: ${processname} never exited cleanly after a stop signal" >&2
            return 1
        fi
    done
}

########
stop_resident_program()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")
    local command_line_file="${absdirname}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"

    local pfile
    pfile=$(debasher::_get_abspfile_from_command_line_file "${command_line_file}") || return 1
    local sched
    sched=$(debasher::_get_sched_from_command_line_file "${command_line_file}") || return 1

    local orig_outdir
    orig_outdir=$(debasher::_get_orig_outdir_from_command_line_file "${command_line_file}") || return 1
    if debasher::_dirnames_are_equal "${orig_outdir}" "${absdirname}"; then
        :
    else
        echo "Warning: program output directory was moved (original directory: ${orig_outdir})" >&2
    fi

    debasher::load_debasher_module "$pfile" || return 1
    configure_scheduler $sched || return 1
    debasher::_resolve_program_type "${pfile}" || return 1

    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        echo "Error: ${pfile} is not a resident program (debasher_stop_resident is only for those; use debasher_stop otherwise)" >&2
        return 1
    fi

    debasher::_exec_program_func_for_module "${pfile}"

    find_supervisor_and_nodes "${excluded_csv}" || return 1
    capture_halted_marker_baselines "${absdirname}"

    local deadline=$(( $(now_epoch) + timeout_secs ))

    if stop_supervisor_if_any "${absdirname}" "${deadline}" \
        && trigger_shutdown_for_all_nodes "${absdirname}" "${deadline}" \
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
