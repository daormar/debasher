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

# Resets a stopped resident program to a clean start (see
# "debasher_reset_resident: a clean start" in doc/design_doc_resident.md):
# the next debasher_exec on the same output directory starts every node
# with no checkpoint and an empty input log, as on its first run. A node
# keeps its state across runs in its checkpoints, its input log and its
# halted marker, in the process's own __exec__ directory, and in the output
# directory of the process, none of which the engine resets. This tool sets
# all of them aside, and the notice of the node with them, under __reset__/<timestamp>/ in the output directory of
# the program, or deletes them with --delete. It resets the whole program,
# never one node: a node that starts afresh numbers the messages of its
# channels from the start again, and a reader that kept its own state would
# drop everything it sends as duplicates. It refuses to run while a
# debasher_exec holds the lock of the output directory for a run, or while
# any process of the program is in progress.

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_lib_resident_tools || exit 1

# The directory of the program's output directory under which the state of
# each reset is set aside, one subdirectory per reset
DEBASHER_RESET_RESIDENT_DIRNAME="__reset__"

########
print_desc()
{
    echo "debasher_reset_resident resets a stopped resident program to a clean start"
    echo "type \"debasher_reset_resident --help\" to get usage information"
}

########
usage()
{
    echo "debasher_reset_resident   -d <string> [--delete] [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "--delete                  Delete the state of the nodes instead of"
    echo "                          setting it aside under ${DEBASHER_RESET_RESIDENT_DIRNAME}/<timestamp>/"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    delete_state=0
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
            "--delete") delete_state=1
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
}

########
# Prints, one per line, the paths that hold the state of the nodes of process
# $2: in the process's __exec__ directory, the checkpoints, the input log, the
# halted marker and the notice of each task, named as the node's runtime names
# them (see _get_execdir_entry in engine/debasher_runtime_transport.py), and the
# output directory of the process unless it is empty. Only the paths that
# exist.
state_paths_of_process()
{
    local absdirname=$1
    local processname=$2

    # A process never launched has no script and no state in its execdir,
    # but it may still have its output directory
    local script_file=$(debasher::_get_script_filename "${absdirname}" "${processname}")
    if [ -f "${script_file}" ]; then
        local process_nodes node name path
        # No wait: the script is there
        process_nodes=$(debasher::_resident_tool_list_nodes_of_process "${absdirname}" "${processname}" 0) || return 1
        while IFS= read -r node; do
            # node_info and control_ports are left: nothing reads them back,
            # and every incarnation writes them again
            for name in checkpoints log halted notice; do
                path=$(debasher::_resident_tool_node_execdir_entry "${absdirname}" "${node}" "${name}")
                if [ -e "${path}" ]; then
                    echo "${path}"
                fi
            done
        done <<< "${process_nodes}"
    fi

    # An empty output directory is left, as the reset itself leaves it, so
    # that a program with nothing left to reset says so
    local outdir=$(debasher::_get_process_outdir_given_dirname "${absdirname}" "${processname}")
    if [ -d "${outdir}" ] && [ -n "$("${FIND}" "${outdir}" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
        echo "${outdir}"
    fi
}

########
# Returns 1, with an error, if some process of the program is running.
ensure_program_is_stopped()
{
    local absdirname=$1
    local processname status
    local -a running=()
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        status=$(debasher::_get_process_status "${absdirname}" "${processname}")
        if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
            running+=("${processname}")
        fi
    done
    if [ ${#running[@]} -gt 0 ]; then
        echo "Error: ${running[*]} still running; stop the program first (debasher_stop_resident or debasher_stop)" >&2
        return 1
    fi
}

########
# Sets aside, or deletes if $4 (delete_state) is 1, what $2 names: a path in
# the program's output directory $1. Set aside, it keeps its path relative to
# $1 under $3. Returns 1 if it cannot.
reset_path()
{
    local absdirname=$1
    local path=$2
    local reset_dir=$3
    local delete_state=$4

    if [ ${delete_state} -eq 1 ]; then
        "${RM}" -rf "${path}"
        return
    fi

    local target="${reset_dir}/${path#${absdirname}/}"
    "${MKDIR}" -p "${target%/*}" || return 1
    "${MV}" "${path}" "${target}"
}

########
# Resets the resident program whose output directory is $1: sets aside the
# state of every node under __reset__, or deletes it if $2 (--delete) is 1.
# Prints what it did, or that there was nothing to reset. Returns 1, with an
# error, while a debasher_exec holds the lock for a run or a process is in
# progress, on a program it cannot load or that is not a resident one, and
# on a path that it cannot reset.
reset_resident_program()
{
    local dirname=$1
    local delete_state=$2
    local absdirname=$(debasher::_get_absolute_path "${dirname}")

    # A debasher_exec that holds the lock prepares the run and launches the
    # nodes before any of them is in progress. The lock is taken only for an
    # instant, to look at it, never kept: debasher_stop would take a reset
    # that kept it for the scheduler of a run
    if debasher::_outdir_is_locked_for_a_run "${absdirname}"; then
        echo "Error: a debasher_exec is preparing or running the program in ${dirname}; stop it first (debasher_stop_resident or debasher_stop)" >&2
        return 1
    fi

    debasher::_resident_tool_load_program "${absdirname}" debasher_reset_resident || return 1

    # After the loading, which gives the processes to look at
    ensure_program_is_stopped "${absdirname}" || return 1

    local stamp
    printf -v stamp '%(%Y%m%d_%H%M%S)T' -1
    local reset_dir="${absdirname}/${DEBASHER_RESET_RESIDENT_DIRNAME}/${stamp}"
    # A second reset within the same second gets a directory of its own
    local num_same_stamp=0
    while [ -e "${reset_dir}" ]; do
        num_same_stamp=$((num_same_stamp + 1))
        reset_dir="${absdirname}/${DEBASHER_RESET_RESIDENT_DIRNAME}/${stamp}_${num_same_stamp}"
    done

    local where=" (in ${reset_dir})"
    if [ ${delete_state} -eq 1 ]; then
        where=""
    fi

    # Every process, the Supervisor included: the whole program, never one
    # node
    local processname path num_paths=0
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        while IFS= read -r path; do
            [ -n "${path}" ] || continue
            # Nothing is undone: running the tool again moves what is left
            # and does not find what it already moved
            reset_path "${absdirname}" "${path}" "${reset_dir}" "${delete_state}" || {
                echo "Error: could not reset ${path}; what came before it is already reset${where}: run debasher_reset_resident again once the cause is fixed" >&2
                return 1
            }
            num_paths=$((num_paths + 1))
        done < <(state_paths_of_process "${absdirname}" "${processname}")
    done

    # The output directory of every process is left there empty, as the
    # engine leaves it before a first run
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        path=$(debasher::_get_process_outdir_given_dirname "${absdirname}" "${processname}")
        "${MKDIR}" -p "${path}" || return 1
    done

    if [ ${num_paths} -eq 0 ]; then
        echo "Nothing to reset in ${dirname}."
    elif [ ${delete_state} -eq 1 ]; then
        echo "Reset ${dirname}: deleted the state of every node."
    else
        echo "Reset ${dirname}: the state of every node is kept in ${reset_dir}."
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

reset_resident_program "${pdir}" "${delete_state}"

exit $?
