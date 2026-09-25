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
# Starts a snapshot round in a running resident program, from outside it,
# with or without a Supervisor: writes a start_snapshot trigger, numbered
# with the time in milliseconds, into the control ports of every node, and
# waits until every node has a checkpoint of that round (or of a newer one).
# With --every, it does so again every given number of seconds, each round
# having until the next one to close, and ends by itself once no node of the
# program is running any more.
#
# Exit codes: 0 is a round that closed at every node (with --every, a
# program that stopped); 1 is a usage or setup error (bad arguments, a
# directory that is not a resident program's, a program that is not
# running, and the like); 2 (DEBASHER_SNAPSHOT_RESIDENT_NOT_CLOSED_EXIT)
# means the round did not close at every node within --timeout: a trigger
# that could not be written, a node that is down, a newer round still open,
# or a node that closed the round without writing a checkpoint because its
# outbound backlog was over its cap.

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_lib_resident_tools || exit 1

DEBASHER_SNAPSHOT_RESIDENT_NOT_CLOSED_EXIT=2

########
print_desc()
{
    echo "debasher_snapshot_resident starts a snapshot round in a resident program"
    echo "type \"debasher_snapshot_resident --help\" to get usage information"
}

########
usage()
{
    echo "debasher_snapshot_resident -d <string> [--timeout <int> | --every <int>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "--timeout <int>           Seconds to wait for the round to close at every"
    echo "                          node (default: 60)"
    echo "--every <int>             Start a round every <int> seconds, each having"
    echo "                          until the next one to close, until no node of"
    echo "                          the program is running"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    timeout_given=0
    timeout_secs=60
    every_secs=""
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
            "--timeout") shift
                  if [ $# -ne 0 ]; then
                      timeout_secs=$1
                      timeout_given=1
                  fi
                  ;;
            "--every") shift
                  if [ $# -ne 0 ]; then
                      every_secs=$1
                  fi
                  ;;
        esac
        shift
    done
}

########
is_positive_int()
{
    [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -gt 0 ]
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

    if ! is_positive_int "${timeout_secs}"; then
        echo "Error! --timeout must be a positive number of seconds" >&2
        exit 1
    fi

    if [ -n "${every_secs}" ]; then
        if ! is_positive_int "${every_secs}"; then
            echo "Error! --every must be a positive number of seconds" >&2
            exit 1
        fi
        if [ ${timeout_given} -eq 1 ]; then
            echo "Error! --timeout and --every cannot be given together (with --every, a round has until the next one to close)" >&2
            exit 1
        fi
    fi
}

########
# Waits until every node has a checkpoint of the round numbered $2 or of a
# newer one, or the deadline $3 passes. Returns 0 if the round closed at
# every node, 1 if the deadline passed first (naming the nodes it did not
# close at), and 2 if the program stopped meanwhile.
wait_for_round_to_close()
{
    local absdirname=$1
    local epoch=$2
    local deadline=$3

    local -a pending=("${DEBASHER_RESIDENT_TOOL_NODES[@]}")
    local -a still_pending
    local node
    local polls=0
    while :; do
        still_pending=()
        for node in "${pending[@]}"; do
            if ! debasher::_resident_tool_node_has_checkpoint_since "${absdirname}" "${node}" "${epoch}"; then
                still_pending+=("${node}")
            fi
        done
        pending=("${still_pending[@]}")
        if [ ${#pending[@]} -eq 0 ]; then
            return 0
        fi
        if [ "$(debasher::_resident_tool_now_secs)" -ge "${deadline}" ]; then
            echo "Error: no checkpoint of round ${epoch} or of a newer one at ${pending[*]}" >&2
            return 1
        fi
        # Whether the program is still running, about once a second
        polls=$(( polls + 1 ))
        if [ $(( polls % 5 )) -eq 0 ] && ! debasher::_resident_tool_some_node_is_running "${absdirname}"; then
            return 2
        fi
        "${SLEEP}" 0.2
    done
}

########
# Waits until the deadline $2 passes. Returns 1 as soon as no node of the
# program is running any more.
sleep_while_running()
{
    local absdirname=$1
    local deadline=$2

    while [ "$(debasher::_resident_tool_now_secs)" -lt "${deadline}" ]; do
        if ! debasher::_resident_tool_some_node_is_running "${absdirname}"; then
            return 1
        fi
        "${SLEEP}" 1
    done
    return 0
}

########
# Starts one round and waits for it until the deadline $3. Returns what
# wait_for_round_to_close does, and 1 as well if the trigger could not be
# written.
snapshot_once()
{
    local absdirname=$1
    local epoch=$2
    local deadline=$3

    debasher::_resident_tool_trigger_every_node "${absdirname}" start_snapshot "${epoch}" "${deadline}" || return 1
    wait_for_round_to_close "${absdirname}" "${epoch}" "${deadline}"
}

########
# Starts a round every every_secs seconds, until no node of the program is
# running. A round that has not closed when the next one starts is only
# warned about: the next one replaces it.
snapshot_periodically()
{
    local dirname=$1
    local absdirname=$2

    # Checked before every round, not only while waiting: with a short
    # period the deadline of a round can pass before any check, and a
    # trigger for a node that is gone blocks for its whole timeout.
    local next epoch status
    while debasher::_resident_tool_some_node_is_running "${absdirname}"; do
        next=$(( $(debasher::_resident_tool_now_secs) + every_secs ))
        epoch=$(debasher::_now_ms)
        snapshot_once "${absdirname}" "${epoch}" "${next}"
        status=$?
        case ${status} in
            0) echo "Round ${epoch} closed at every node of ${dirname}."
               ;;
            1) echo "Warning: round ${epoch} did not close at every node of ${dirname} before the next one" >&2
               ;;
            *) break
               ;;
        esac
        sleep_while_running "${absdirname}" "${next}" || break
    done

    echo "No node of ${dirname} is running any more, no more rounds."
    return 0
}

########
snapshot_resident_program()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    debasher::_resident_tool_load_program "${absdirname}" debasher_snapshot_resident || return 1

    local wait_secs=${every_secs:-${timeout_secs}}
    local deadline=$(( $(debasher::_resident_tool_now_secs) + wait_secs ))

    debasher::_resident_tool_find_supervisor_and_nodes "${absdirname}" "" "${deadline}" || return 1

    if ! debasher::_resident_tool_some_node_is_running "${absdirname}"; then
        echo "Error: no node of ${dirname} is running" >&2
        return 1
    fi

    if [ -n "${every_secs}" ]; then
        snapshot_periodically "${dirname}" "${absdirname}"
        return $?
    fi

    local epoch
    epoch=$(debasher::_now_ms)
    if snapshot_once "${absdirname}" "${epoch}" "${deadline}"; then
        echo "Round ${epoch} closed at every node of ${dirname}."
        return 0
    fi

    echo "Warning: round ${epoch} did not close at every node of ${dirname} within ${timeout_secs}s" >&2
    return "${DEBASHER_SNAPSHOT_RESIDENT_NOT_CLOSED_EXIT}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

snapshot_resident_program "${pdir}"

exit $?
