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
# all of them aside, under __reset__/<timestamp>/ in the output directory of
# the program, or deletes them with --delete. It resets the whole program,
# never one node: a node that starts afresh numbers the messages of its
# channels from the start again, and a reader that kept its own state would
# drop everything it sends as duplicates. It refuses to run while any
# process of the program is.

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1

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
# The number of tasks of process $2, from the script the scheduler wrote for
# it (its DEBASHER_NUM_TASKS line), or nothing if it was never launched and
# so has no state to reset.
num_tasks_of_process()
{
    local absdirname=$1
    local processname=$2
    local script_file
    script_file=$(debasher::_get_script_filename "${absdirname}" "${processname}")
    [ -f "${script_file}" ] || return 0
    local line
    while IFS= read -r line; do
        case "${line}" in
            DEBASHER_NUM_TASKS=*)
                echo "${line#DEBASHER_NUM_TASKS=}"
                return 0
                ;;
        esac
    done < "${script_file}"
}

########
# Prints, one per line, the paths that hold the state of the nodes of process
# $2: in the process's __exec__ directory, the checkpoints, the input log and
# the halted marker of each task, named as the node's runtime names them (see
# _execdir_entry in engine/debasher_runtime_transport.py), and the output
# directory of the process. Only the paths that exist.
state_paths_of_process()
{
    local absdirname=$1
    local processname=$2

    local num_tasks
    num_tasks=$(num_tasks_of_process "${absdirname}" "${processname}")
    if [ -n "${num_tasks}" ]; then
        local execdir=$(debasher::_get_prg_exec_dir_for_process "${absdirname}" "${processname}")
        local name idx suffix
        for (( idx = 0; idx < num_tasks; idx++ )); do
            suffix=""
            if [ "${num_tasks}" -gt 1 ]; then
                suffix="_${idx}"
            fi
            for name in checkpoints log halted; do
                if [ -e "${execdir}/${name}${suffix}" ]; then
                    echo "${execdir}/${name}${suffix}"
                fi
            done
        done
    fi

    local outdir=$(debasher::_get_process_outdir_given_dirname "${absdirname}" "${processname}")
    if [ -d "${outdir}" ]; then
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
# Sets aside, or deletes if --delete was given, what $2 names: a path in the
# program's output directory $1. Set aside, it keeps its path relative to $1
# under $3.
reset_path()
{
    local absdirname=$1
    local path=$2
    local reset_dir=$3

    if [ ${delete_state} -eq 1 ]; then
        "${RM}" -rf "${path}"
        return
    fi

    local target="${reset_dir}/${path#${absdirname}/}"
    "${MKDIR}" -p "${target%/*}" || return 1
    "${MV}" "${path}" "${target}"
}

########
reset_resident_program()
{
    local dirname=$1
    local absdirname=$(debasher::_get_absolute_path "${dirname}")
    local command_line_file="${absdirname}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"

    local pfile
    pfile=$(debasher::_get_abspfile_from_command_line_file "${command_line_file}") || return 1
    local sched
    sched=$(debasher::_get_sched_from_command_line_file "${command_line_file}") || return 1

    debasher::load_debasher_module "$pfile" || return 1
    configure_scheduler $sched || return 1
    debasher::_resolve_program_type "${pfile}" || return 1

    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        echo "Error: ${pfile} is not a resident program (debasher_reset_resident is only for those)" >&2
        return 1
    fi

    debasher::_exec_program_func_for_module "${pfile}"

    ensure_program_is_stopped "${absdirname}" || return 1

    local stamp
    printf -v stamp '%(%Y%m%d_%H%M%S)T' -1
    local reset_dir="${absdirname}/${DEBASHER_RESET_RESIDENT_DIRNAME}/${stamp}"

    local processname path num_paths=0
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        while IFS= read -r path; do
            [ -n "${path}" ] || continue
            reset_path "${absdirname}" "${path}" "${reset_dir}" || {
                echo "Error: could not reset ${path}" >&2
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

reset_resident_program "${pdir}"

exit $?
