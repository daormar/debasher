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

########################################
# PROCESS DEPENDENCY-RELATED FUNCTIONS #
########################################

########
debasher::_get_processdeps_separator()
{
    local processdeps=$1
    if [[ "${processdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_COMMA}"* ]]; then
        echo "${DEBASHER_PROCESSDEPS_SEP_COMMA}"
    else
        if [[ "${processdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_INTERR}"* ]]; then
            echo "${DEBASHER_PROCESSDEPS_SEP_INTERR}"
        else
            echo ""
        fi
    fi
}

########
debasher::_get_deptype_part_in_dep()
{
    local dep=$1
    local str_array
    IFS="${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
debasher::_get_processname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ]; then
        echo ${dep}
    else
        local str_array
        IFS="${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"
        echo ${str_array[1]}
    fi
}

########
# Check whether the argument at position $1 is a candidate to generate
# a process dependency. Returns 0 and writes the associated option index
# into the caller-provided variable if it is a candidate; returns 1
# otherwise. The locals below must not share a name with the caller's
# variable (the callers pass "j"): the nameref would resolve to the local
# one instead, and the caller's variable would never be written.
debasher::_deserialized_args_idx_is_dep_candidate()
{
    local i=$1
    local -n idx_ref=$2

    local value="${DEBASHER_DESERIALIZED_ARGS[i]}"
    if ! debasher::_is_absolute_path "${value}"; then
        return 1
    fi

    local opt_idx=$((i-1))
    if [ ${opt_idx} -lt 0 ]; then
        return 1
    fi

    local opt="${DEBASHER_DESERIALIZED_ARGS[opt_idx]}"
    if ! debasher::_str_is_option "${opt}" || debasher::_str_is_output_option "${opt}"; then
        return 1
    fi

    if [[ ! -v DEBASHER_OUT_VALUE_TO_PROCESSES[${value}] ]]; then
        return 1
    fi

    idx_ref=${opt_idx}
    return 0
}

########
debasher::_deptype_is_known()
{
    local deptype=$1

    case "${deptype}" in
        "${DEBASHER_NONE_PROCESSDEP_TYPE}"|"${DEBASHER_AFTER_PROCESSDEP_TYPE}"|\
        "${DEBASHER_AFTEROK_PROCESSDEP_TYPE}"|"${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}"|\
        "${DEBASHER_AFTERANY_PROCESSDEP_TYPE}"|"${DEBASHER_AFTERCORR_PROCESSDEP_TYPE}")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
# Merges two dependency types that a process has on the same producer
# into the weakest type that asks for everything both of them ask for,
# and writes it into the caller-provided variable (no subshell). Every
# type other than none implies after (the producer started); afterok
# implies afterany and aftercorr; aftercorr together with afterany asks
# for every task finished and the corresponding one successful, which
# only afterok covers. Fails, with an error, for an unknown type and
# for two types that no run of the producer satisfies at once (afterok
# or aftercorr together with afternotok). An empty type counts as none.
debasher::_merge_deptypes()
{
    local deptype_a=${1:-${DEBASHER_NONE_PROCESSDEP_TYPE}}
    local deptype_b=${2:-${DEBASHER_NONE_PROCESSDEP_TYPE}}
    local -n merged_ref=$3

    local deptype
    for deptype in "${deptype_a}" "${deptype_b}"; do
        if ! debasher::_deptype_is_known "${deptype}"; then
            echo "Error: unknown process dependency type: ${deptype}" >&2
            return 1
        fi
    done

    if [ "${deptype_a}" = "${deptype_b}" ]; then
        merged_ref=${deptype_a}
        return 0
    fi

    # none and after are implied by every other type
    local weakest
    for weakest in "${DEBASHER_NONE_PROCESSDEP_TYPE}" "${DEBASHER_AFTER_PROCESSDEP_TYPE}"; do
        if [ "${deptype_a}" = "${weakest}" ]; then
            merged_ref=${deptype_b}
            return 0
        fi
        if [ "${deptype_b}" = "${weakest}" ]; then
            merged_ref=${deptype_a}
            return 0
        fi
    done

    # The remaining types are afterok, afternotok, afterany and aftercorr
    if [ "${deptype_a}" = "${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}" ] || [ "${deptype_b}" = "${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}" ]; then
        if [ "${deptype_a}" = "${DEBASHER_AFTERANY_PROCESSDEP_TYPE}" ] || [ "${deptype_b}" = "${DEBASHER_AFTERANY_PROCESSDEP_TYPE}" ]; then
            merged_ref=${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}
            return 0
        fi
        echo "Error: process dependency types ${deptype_a} and ${deptype_b} on the same process cannot both be satisfied" >&2
        return 1
    fi

    # Any two of afterok, afterany and aftercorr
    merged_ref=${DEBASHER_AFTEROK_PROCESSDEP_TYPE}
}

########
debasher::_get_procdeps_for_process()
{
    # Writes the result into the caller-provided variable name (no subshell,
    # no fork: this avoids the cost of command substitution at the call site).
    # Still forks internally when invoking the user-defined callback, since
    # that callback's contract is to echo its result.
    debasher::_get_deptype_using_func()
    {
        local define_opt_deps_funcname=$1
        local opt=$2
        local producer_process=$3
        local -n result_ref=$4

        if [ "${define_opt_deps_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            result_ref=""
        else
            result_ref=$("${define_opt_deps_funcname}" "${opt}" "${producer_process}")
        fi
    }

    # Merges into the dependencies of a task, an associative array from
    # producer to type, the dependency that its option opt gives through
    # a fifo: none unless _define_opt_deps says otherwise, and none for
    # the fifo of the process itself
    debasher::_add_fifo_dep()
    {
        local define_opt_deps_funcname=$1
        local processname=$2
        local opt=$3
        local augm_fifoname=$4
        local -n fifo_depdict_ref=$5

        local proc_plus_idx="${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}"
        local processowner="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

        [ "${processowner}" = "${processname}" ] && return 0

        local deptype
        debasher::_get_deptype_using_func "${define_opt_deps_funcname}" "${opt}" "${processowner}" deptype
        [ -z "${deptype}" ] && deptype="${DEBASHER_NONE_PROCESSDEP_TYPE}"
        [ "${deptype}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] && return 0

        local merged_deptype
        debasher::_merge_deptypes "${fifo_depdict_ref[$processowner]}" "${deptype}" merged_deptype || return 1
        fifo_depdict_ref["${processowner}"]=${merged_deptype}
    }

    # Merges into the dependencies of a task, an associative array from
    # producer to type, those that its option opt gives on each process
    # that produces the file value: afterok, or aftercorr when both
    # processes are arrays and the task reads the task of its own index,
    # unless _define_opt_deps says otherwise; none for the process itself
    debasher::_add_file_deps()
    {
        local define_opt_deps_funcname=$1
        local processname=$2
        local num_tasks=$3
        local task_idx=$4
        local opt=$5
        local value=$6
        local -n file_depdict_ref=$7
        local processes="${DEBASHER_OUT_VALUE_TO_PROCESSES[${value}]}"

        while [ -n "${processes}" ]; do
            local proc_plus_idx="${processes%%${DEBASHER_ASSOC_ARRAY_PROC_SEP}*}"
            local proc="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
            local idx="${proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"

            # Advance to the next process in the list up-front, so any
            # "continue" below doesn't risk an infinite loop
            local processes_aux="${processes#"${proc_plus_idx}${DEBASHER_ASSOC_ARRAY_PROC_SEP}"}"
            if [ "${processes}" = "${processes_aux}" ]; then
                processes=""
            else
                processes=${processes_aux}
            fi

            [ "${processname}" = "${proc}" ] && continue

            local deptype
            debasher::_get_deptype_using_func "${define_opt_deps_funcname}" "${opt}" "${proc}" deptype
            if [ -z "${deptype}" ]; then
                # aftercorr pairs a task with the task of the same
                # index of another array, so both have to be arrays
                if [ "$num_tasks" -gt 1 ] && [ "${DEBASHER_PROCESS_OPT_LIST_LEN[${proc}]:-1}" -gt 1 ] && [ "$task_idx" = "$idx" ]; then
                    deptype=${DEBASHER_AFTERCORR_PROCESSDEP_TYPE}
                else
                    deptype=${DEBASHER_AFTEROK_PROCESSDEP_TYPE}
                fi
            fi
            # A none from the callback asks for no dependency at all,
            # as it does for a fifo
            [ "${deptype}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] && continue

            local merged_deptype
            debasher::_merge_deptypes "${file_depdict_ref[$proc]}" "${deptype}" merged_deptype || return 1
            file_depdict_ref["${proc}"]=${merged_deptype}
        done
    }

    # Prints an associative array from producer to type in the format of
    # processdeps: <type>:<process>,...
    debasher::_serialize_depdict()
    {
        local -n serialized_depdict_ref=$1

        local processdeps=""
        local proc
        for proc in "${!serialized_depdict_ref[@]}"; do
            local dep="${serialized_depdict_ref[$proc]}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${proc}"
            if [ -z "$processdeps" ]; then
                processdeps=${dep}
            else
                processdeps="${processdeps}${DEBASHER_PROCESSDEPS_SEP_COMMA}${dep}"
            fi
        done

        echo "${processdeps}"
    }

    debasher::_get_procdeps_for_process_task()
    {
        local cmdline=$1
        local processname=$2
        local define_opt_deps_funcname=$3
        local num_tasks=$4
        local task_idx=$5
        declare -A depdict

        local opts
        opts=$(debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}") || return 1
        debasher::_deserialize_args "${opts}"

        local i
        for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
            # Skip early: is this argument even a dependency candidate?
            local j
            if ! debasher::_deserialized_args_idx_is_dep_candidate "$i" j; then
                continue
            fi

            local opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
            local value="${DEBASHER_DESERIALIZED_ARGS[i]}"

            local augm_fifoname
            augm_fifoname=$(debasher::_get_augm_fifoname_from_absname "${value}")
            if [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                debasher::_add_fifo_dep "${define_opt_deps_funcname}" "${processname}" "${opt}" "${augm_fifoname}" depdict || return 1
            else
                debasher::_add_file_deps "${define_opt_deps_funcname}" "${processname}" "${num_tasks}" "${task_idx}" "${opt}" "${value}" depdict || return 1
            fi
        done

        debasher::_serialize_depdict depdict
    }

    debasher::_get_procdeps_for_task_array()
    {
        # Initialize variables
        local cmdline=$1
        local processname=$2
        local define_opt_deps_funcname=$3
        local num_tasks=$4
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Obtain dependencies for task
            local prdeps_idx
            prdeps_idx=$(debasher::_get_procdeps_for_process_task "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}" "${task_idx}") || return 1

            # Iterate over dependencies
            local -a processdeps_idx
            IFS=${DEBASHER_PROCESSDEPS_SEP_COMMA} read -r -a processdeps_idx <<< "${prdeps_idx}"
            local processdep
            for processdep in "${processdeps_idx[@]}"; do
                # Extract dependency information
                local deptype="${processdep%%${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}*}"
                local proc="${processdep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"

                # Update associative array of dependencies
                local merged_deptype
                debasher::_merge_deptypes "${depdict[$proc]}" "${deptype}" merged_deptype || return 1
                depdict["${proc}"]=${merged_deptype}
            done
        done

        debasher::_serialize_depdict depdict
    }

    local cmdline=$1
    local processname=$2

    # Get name of function to define option dependencies for process
    # (if defined)
    local define_opt_deps_funcname
    define_opt_deps_funcname=$(debasher::_get_define_opt_deps_funcname "${processname}")

    # Determine whether the process has multiple tasks
    local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        debasher::_get_procdeps_for_process_task "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        debasher::_get_procdeps_for_task_array "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}"
    fi
}

########
debasher::_get_procdeps_for_process_cached()
{
    local cmdline=$1
    local process_spec=$2

    # Extract process information
    local processname=$(debasher::_extract_processname_from_process_spec "$process_spec")

    # Check if process dependencies were already obtained
    if [[ -v DEBASHER_PROCESS_DEPENDENCIES["$processname"] ]]; then
        echo "${DEBASHER_PROCESS_DEPENDENCIES[$processname]}"
    else
        # Extract dependencies from process specification if given
        local deps=$(debasher::_extract_processdeps_from_process_spec "${process_spec}")
        if [ "${deps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # No dependencies are provided in specification
            deps=$(debasher::_get_procdeps_for_process "${cmdline}" "$processname") || return 1
            if [ -z "${deps}" ]; then
                deps="${DEBASHER_NONE_PROCESSDEP_TYPE}"
            fi
            # Add prefix to result
            deps="${DEBASHER_PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            DEBASHER_PROCESS_DEPENDENCIES["$processname"]=${deps}
            echo "$deps"
        else
            # Add prefix to result
            deps="${DEBASHER_PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            DEBASHER_PROCESS_DEPENDENCIES["$processname"]=${deps}
            echo "$deps"
        fi
    fi
}

########
debasher::_register_fifos_read_by_process()
{
    debasher::_register_fifos_read_by_process_task()
    {
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        local task_idx=$4

        local opts
        opts=$(debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}") || return 1
        debasher::_deserialize_args "${opts}"

        local i
        for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
            # Skip early: is this argument even a dependency candidate?
            local j
            if ! debasher::_deserialized_args_idx_is_dep_candidate "$i" j; then
                continue
            fi

            local value="${DEBASHER_DESERIALIZED_ARGS[i]}"

            local augm_fifoname
            augm_fifoname=$(debasher::_get_augm_fifoname_from_absname "${value}")
            [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]] || continue

            # The option through which the task that owns the fifo defines it
            # does not make the task a reader of it (a fifo fed from outside
            # that the owner reads, defined through an input option). Any
            # other option does: that of another task of the same array, and
            # that of the owner itself when it reads what it writes (a
            # self-loop)
            local this_task="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}"
            if [ "${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}" = "${this_task}" ] \
                   && [ "${DEBASHER_DESERIALIZED_ARGS[j]}" = "${DEBASHER_FIFO_OWNER_OPTS["${augm_fifoname}"]:-}" ]; then
                continue
            fi

            # A fifo has a single reader: each line written into it reaches
            # only one of the processes that open it for reading, and a
            # second reader would wait forever for the lines the first one
            # takes. Registering the same task and option again is not an
            # error
            local opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
            local prev_reader="${DEBASHER_FIFO_READERS["${augm_fifoname}"]:-${DEBASHER_EXTERNAL_FIFO_END}}"
            if [ "${prev_reader}" != "${DEBASHER_EXTERNAL_FIFO_END}" ] \
                   && { [ "${prev_reader}" != "${this_task}" ] || [ "${DEBASHER_FIFO_READER_OPTS["${augm_fifoname}"]:-}" != "${opt}" ]; }; then
                echo "Error: fifo ${augm_fifoname} is read by ${prev_reader//${DEBASHER_ASSOC_ARRAY_ELEM_SEP}/ task } (option ${DEBASHER_FIFO_READER_OPTS["${augm_fifoname}"]:-}) and by ${processname} task ${task_idx} (option ${opt}); a fifo has a single reader" >&2
                return 1
            fi

            # Register the current task as the reader of the fifo, and the option
            # through which it reads it
            DEBASHER_FIFO_READERS["${augm_fifoname}"]=${this_task}
            DEBASHER_FIFO_READER_OPTS["${augm_fifoname}"]=${DEBASHER_DESERIALIZED_ARGS[j]}
        done
    }

    debasher::_register_fifos_read_by_task_array()
    {
        # Initialize variables
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Register fifos for task
            debasher::_register_fifos_read_by_process_task "${cmdline}" "${processname}" "${num_tasks}" "${task_idx}" || return 1
        done
    }

    local cmdline=$1
    local processname=$2

    # Determine whether the process has multiple tasks
    local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        debasher::_register_fifos_read_by_process_task "${cmdline}" "${processname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        debasher::_register_fifos_read_by_task_array "${cmdline}" "${processname}" "${num_tasks}"
    fi
}

########
# Prints the task indices given, in increasing order and with runs of
# consecutive ones joined, as "task 3" or as "tasks 0-2, 5".
debasher::_describe_task_indices()
{
    # The indices of an indexed array come out in increasing order
    local -a present=()
    local idx
    for idx in "$@"; do
        present[idx]=1
    done

    local -a ranges=()
    local first="" last=""
    for idx in "${!present[@]}"; do
        if [ -n "${last}" ] && [ "${idx}" -eq $((last + 1)) ]; then
            last=${idx}
            continue
        fi
        [ -z "${first}" ] || ranges+=("$(debasher::_describe_task_range "${first}" "${last}")")
        first=${idx}
        last=${idx}
    done
    [ -z "${first}" ] || ranges+=("$(debasher::_describe_task_range "${first}" "${last}")")

    local joined
    joined=$(printf '%s, ' "${ranges[@]}")
    if [ "${#present[@]}" -eq 1 ]; then
        echo "task ${joined%, }"
    else
        echo "tasks ${joined%, }"
    fi
}

########
# Prints the range of task indices from $1 to $2, as "3" or "0-2".
debasher::_describe_task_range()
{
    if [ "$1" -eq "$2" ]; then
        echo "$1"
    else
        echo "$1-$2"
    fi
}

########
# Checks that the fifos that the tasks of a process define through the same
# option are read inside the program for every task or for none. When only
# some of them are, the others are almost always a mistake (a reader with
# fewer tasks than the process, or a connection made with
# define_opt_from_proc_out, which takes only the first task), and their
# owners would block for ever waiting for a reader. A fifo with a tag is
# left out, since its owner reads it. Prints an error and returns 1 for the
# first option found whose fifos are read for some tasks only.
debasher::_check_fifos_read_alike()
{
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"

    # The tasks whose fifo is read inside the program, and those whose fifo
    # is not, for each process and option
    local -A read_tasks=()
    local -A unread_tasks=()
    local augm_fifoname owner group
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        [ -z "${DEBASHER_FIFO_KINDS[${augm_fifoname}]:-}" ] || continue
        owner="${DEBASHER_PROGRAM_FIFOS[${augm_fifoname}]}"
        group="${owner%%${sep}*}${sep}${DEBASHER_FIFO_OWNER_OPTS[${augm_fifoname}]:-}"
        if [ "${DEBASHER_FIFO_READERS[${augm_fifoname}]:-${DEBASHER_EXTERNAL_FIFO_END}}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
            unread_tasks["${group}"]+=" ${owner##*${sep}}"
        else
            read_tasks["${group}"]+=" ${owner##*${sep}}"
        fi
    done

    for group in "${!unread_tasks[@]}"; do
        [[ -v read_tasks["${group}"] ]] || continue
        local processname="${group%%${sep}*}"
        local opt="${group#*${sep}}"
        local -a unread=(${unread_tasks[${group}]})
        local owners="whose owner"
        [ "${#unread[@]}" -eq 1 ] || owners="whose owners"
        echo "Error: the fifos that process ${processname} defines through ${opt} are read inside the program for $(debasher::_describe_task_indices ${read_tasks[${group}]}) but not for $(debasher::_describe_task_indices "${unread[@]}"), ${owners} would block waiting for a reader: a reader with fewer tasks than ${processname}, or a connection to ${processname} made with define_opt_from_proc_out, which takes only its first task" >&2
        return 1
    done
}
