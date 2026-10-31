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

###########################################
# PROCESS SPECIFICATION-RELATED FUNCTIONS #
###########################################

########
# Checks that every attribute of the list $3, whose attributes are
# separated by $4, is one of the names in $5, and names the process $1, the
# part $2 and the attribute otherwise: one of the names in $6, those of the
# other part, is written in the wrong part, and any other is unknown. Either
# would be ignored with no message.
debasher::_check_spec_attr_names()
{
    local processname=$1
    local part=$2
    local attr_list=$3
    local sep=$4
    local names=$5
    local other_names=$6

    local -a fields
    IFS="${sep}" read -r -a fields <<< "${attr_list}"
    local field name
    for field in "${fields[@]}"; do
        field=$(debasher::_str_trim "${field}")
        [ -n "${field}" ] || continue
        name=${field%%=*}
        if [[ " ${names} " == *" ${name} "* ]]; then
            continue
        fi
        if [[ " ${other_names} " == *" ${name} "* ]]; then
            local other_part="additional"
            [ "${part}" = "additional" ] && other_part="computational"
            echo "Error: ${name} is written among the ${part} specifications of process ${processname}, where it is not read; write it among the ${other_part} specifications" >&2
        else
            echo "Error: process ${processname} has an unknown ${part} specification: ${field}; the ${part} specifications are: ${names}" >&2
        fi
        return 1
    done
}

########
debasher::_program_process_spec_is_ok()
{
    # NOTE: Process specification is a set of entries, each one
    # containing the process name, computational specifications and
    # additional specifications. The two types of specifications are
    # separated by a especial symbol
    local process_spec=$1

    if [[ "${process_spec}" != *"${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}"* ]]; then
        echo "Error: process specification (\"${process_spec}\") is not correct: it lacks the separator of the additional specifications" >&2
        return 1
    fi

    # Extract process information
    local processname=$(debasher::_extract_processname_from_process_spec "$process_spec")

    # Every attribute is one that the engine reads, in its own part
    local comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    local comp_sep="${DEBASHER_LEGACY_PROCSPECS_SEP}"
    [[ "${comp_specs}" == *"${DEBASHER_PROCSPECS_SEP}"* ]] && comp_sep="${DEBASHER_PROCSPECS_SEP}"
    debasher::_check_spec_attr_names "${processname}" "computational" "${comp_specs}" "${comp_sep}" "${DEBASHER_COMP_SPEC_NAMES}" "${DEBASHER_ADDITIONAL_SPEC_NAMES}" || return 1
    debasher::_check_spec_attr_names "${processname}" "additional" "$(debasher::extract_process_additional_specs "${process_spec}")" "${DEBASHER_PROCSPECS_SEP}" "${DEBASHER_ADDITIONAL_SPEC_NAMES}" "${DEBASHER_COMP_SPEC_NAMES}" || return 1

    # Check if basic computational specifications were provided
    local cpus=$(debasher::_extract_cpus_from_process_spec "$process_spec")
    if [ "$cpus" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        echo "Error: cpus computational specification not given for process ${processname}" >&2
        return 1
    fi

    local mem=$(debasher::_extract_mem_from_process_spec "$process_spec")
    if [ "$mem" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        echo "Error: mem computational specification not given for process ${processname}" >&2
        return 1
    fi

    local time=$(debasher::_extract_time_from_process_spec "$process_spec")
    if [ "$time" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        echo "Error: time computational specification not given for process ${processname}" >&2
        return 1
    fi

    # The limits that a resident process reads, when given, must be positive
    # numbers: checked here, when the program is loaded, rather than by the
    # node when it starts, after it has been launched
    local specname
    for specname in ${DEBASHER_RESIDENT_COMP_SPEC_NAMES}; do
        local value=$(debasher::extract_attr_from_process_comp_specs "${comp_specs}" "${specname}")
        if [ "${value}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && ! debasher::_str_is_positive_number "${value}"; then
            echo "Error: ${specname} computational specification of process ${processname} must be a positive number, got \"${value}\"" >&2
            return 1
        fi
    done
    local batch_sched=$(debasher::extract_attr_from_process_comp_specs "${comp_specs}" "${DEBASHER_BATCH_SCHED_COMP_SPEC_NAME}")
    if [ "${batch_sched}" != "${DEBASHER_ATTR_NOT_FOUND}" ] \
           && [ "${batch_sched}" != "${DEBASHER_BUILTIN_SCHEDULER}" ] \
           && [ "${batch_sched}" != "${DEBASHER_SLURM_SCHEDULER}" ]; then
        echo "Error: ${DEBASHER_BATCH_SCHED_COMP_SPEC_NAME} computational specification of process ${processname} must be ${DEBASHER_BUILTIN_SCHEDULER} or ${DEBASHER_SLURM_SCHEDULER}, got \"${batch_sched}\"" >&2
        return 1
    fi

    return 0
}

########
debasher::extract_process_comp_specs()
{
    local process_spec=$1

    # Keep text before the separator marking the beginning of additional
    # specs
    local specs="${process_spec%%${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}*}"

    # Keep everything except the first word, which is the name of
    # process
    read -r first rest <<< "$specs"
    echo "$rest"
}

########
debasher::_get_process_comp_specs()
{
    local processname=$1

    debasher::extract_process_comp_specs "${DEBASHER_INITIAL_PROCESS_SPEC[${processname}]}"
}

########
debasher::extract_process_additional_specs()
{
    local process_spec=$1

    # Keep text after the separator marking the beginning of additional
    # specs
    local specs="${process_spec#*${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}}"
    echo "$specs"
}

########
debasher::_add_additional_spec()
{
    local process_spec=$1
    local procdeps=$2

    local additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    if [ -z "${additional_specs}" ]; then
        echo "${process_spec} ${procdeps}"
    else
        echo "${process_spec} ${DEBASHER_PROCSPECS_SEP} ${procdeps}"
    fi
}

########
debasher::_extract_attr_from_list_given_sep()
{
    local attr_list=$1
    local attrname=$2
    local sep=$3

    local -a fields
    IFS="${sep}" read -r -a fields <<< "${attr_list}"
    local field
    for field in "${fields[@]}"; do
        field=$(debasher::_str_trim "${field}")
        if [[ "${field}" = "${attrname}="* ]]; then
            echo "${field#"${attrname}="}"
            return 0
        fi
    done

    echo "${DEBASHER_ATTR_NOT_FOUND}"
}

########
debasher::extract_attr_from_process_comp_specs()
{
    local process_comp_specs=$1
    local attrname=$2

    if [[ "${process_comp_specs}" == *"${DEBASHER_PROCSPECS_SEP}"* ]]; then
        debasher::_extract_attr_from_list_given_sep "${process_comp_specs}" "${attrname}" "${DEBASHER_PROCSPECS_SEP}"
    else
        debasher::_extract_attr_from_list_given_sep "${process_comp_specs}" "${attrname}" "${DEBASHER_LEGACY_PROCSPECS_SEP}"
    fi
}

########
debasher::extract_attr_from_process_additional_specs()
{
    local process_additional_specs=$1
    local attrname=$2

    debasher::_extract_attr_from_list_given_sep "${process_additional_specs}" "${attrname}" "${DEBASHER_PROCSPECS_SEP}"
}

########
debasher::_extract_processname_from_process_spec()
{
    local process_spec=$1

    local processname rest
    read -r processname rest <<< "${process_spec}"
    echo "${processname}"
}

########
debasher::_extract_cpus_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "cpus"
}

########
debasher::_extract_mem_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "mem"
}

########
debasher::_extract_time_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "time"
}

########
debasher::_extract_nodes_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "nodes"
}

########
debasher::_extract_account_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "account"
}

########
debasher::_extract_partition_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "partition"
}

########
debasher::_extract_throttle_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "throttle"
}

########
debasher::_extract_processdeps_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "${DEBASHER_PROCESSDEPS_SPEC}"
}

########
debasher::_extract_force_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "force"
}

########
debasher::_extract_alias_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "alias"
}

########
debasher::_extract_alias_opt_map_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "alias_opt_map"
}

########
debasher::_extract_sched_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "sched"
}

########
debasher::_extract_ext_alias_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "ext_alias"
}

########
debasher::_get_processdeps_from_detailed_spec()
{
    local processdeps_spec=$1
    local pdeps=""
    local result

    # Iterate over the elements of the process specification: type1:processname1,...,typen:processnamen or type1:processname1?...?typen:processnamen
    local -a deps_array
    local separator
    debasher::_split_processdeps "${processdeps_spec}" deps_array separator
    local dep_spec
    for dep_spec in "${deps_array[@]}"; do
        local processname=$(debasher::_get_processname_part_in_dep ${dep_spec})
        if [ -z "${result}" ]; then
            result="$processname"
        else
            result=${result}${DEBASHER_PROCESSDEPS_SEP_COMMA}${processname}
        fi
    done

    echo ${result}
}

########
# Checks the explicit dependencies of a process, the value of its
# processdeps additional specification: none, or a list of
# <type>:<process> separated by "," (every one has to hold) or by "?"
# (one of them is enough), but not by both, with no empty element and a
# known dependency type in each. In a list joined by ",", the dependencies
# on the same process have to be satisfiable together, as inferred ones
# are (see debasher::_merge_deptypes); the list is kept as written. Whether
# each process exists is checked by the caller. Prints an error and
# returns 1 on the first violation found.
debasher::_check_explicit_processdeps()
{
    local processname=$1
    local procdeps=$2

    [ "${procdeps}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] && return 0

    if [[ "${procdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_COMMA}"* && "${procdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_INTERR}"* ]]; then
        echo "Error: the dependencies of process ${processname} (${procdeps}) are separated by both \"${DEBASHER_PROCESSDEPS_SEP_COMMA}\" and \"${DEBASHER_PROCESSDEPS_SEP_INTERR}\"; use one of them" >&2
        return 1
    fi

    local -a deps_array
    local separator
    debasher::_split_processdeps "${procdeps}" deps_array separator

    local -A merged=()
    local dep
    for dep in "${deps_array[@]}"; do
        if [ -z "${dep}" ]; then
            echo "Error: the dependencies of process ${processname} (${procdeps}) have an empty element" >&2
            return 1
        fi
        local deptype="${dep%%${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}*}"
        local depproc="${dep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"
        if [ "${dep}" = "${deptype}" ] || [ -z "${deptype}" ] || [ -z "${depproc}" ]; then
            echo "Error: dependency \"${dep}\" of process ${processname} is not of the form <type>${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}<process>" >&2
            return 1
        fi
        if ! debasher::_deptype_is_known "${deptype}"; then
            echo "Error: dependency \"${dep}\" of process ${processname} has an unknown type: ${deptype}" >&2
            return 1
        fi
        [ "${separator}" = "${DEBASHER_PROCESSDEPS_SEP_INTERR}" ] && continue
        local merged_deptype
        if ! debasher::_merge_deptypes "${merged[${depproc}]:-}" "${deptype}" merged_deptype 2> /dev/null; then
            echo "Error: the dependencies of process ${processname} on ${depproc} (${merged[${depproc}]} and ${deptype}, which all have to hold) cannot both be satisfied by any run of ${depproc}; keep one of them, or join them by \"${DEBASHER_PROCESSDEPS_SEP_INTERR}\" if one is enough" >&2
            return 1
        fi
        merged["${depproc}"]=${merged_deptype}
    done
}

########
debasher::_gen_final_procspec()
{
    local cmdline=$1

    # Iterate over process specifications
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local process_spec="${DEBASHER_INITIAL_PROCESS_SPEC[${processname}]}"
        # The check says what is wrong
        debasher::_program_process_spec_is_ok "$process_spec" || exit 1

        # Extract dependencies from process specification
        local procdeps=$(debasher::_extract_processdeps_from_process_spec "${process_spec}")

        # Check if dependencies were given
        if [ "${procdeps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # Dependencies not given, so they should be obtained
            procdeps=$(debasher::_get_procdeps_for_process_cached "${cmdline}" "${process_spec}") || exit 1

            # Register dependencies
            DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED["${processname}"]=$(debasher::_get_processdeps_from_detailed_spec "${procdeps}")

            # Register process spec
            local augmented_process_spec
            augmented_process_spec=$(debasher::_add_additional_spec "${process_spec}" "${procdeps}")
            DEBASHER_FINAL_PROCESS_SPEC["${processname}"]="${augmented_process_spec}"
        else
            # Dependencies were given
            debasher::_check_explicit_processdeps "${processname}" "${procdeps}" || exit 1

            # Register dependencies
            DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED["${processname}"]=$(debasher::_get_processdeps_from_detailed_spec "${procdeps}")

            # Register process spec
            DEBASHER_FINAL_PROCESS_SPEC["${processname}"]="${process_spec}"
        fi

        # Check that dependencies are correct

        # Iterate over dependencies, checking that the dependent process exists
        local -a deps_array
        IFS="${DEBASHER_PROCESSDEPS_SEP_COMMA}" read -ra deps_array <<< "${DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED[${processname}]}"
        local proc
        for proc in "${deps_array[@]}"; do
            if [[ "${proc}" != "${DEBASHER_NONE_PROCESSDEP_TYPE}" && ! -v DEBASHER_PROGRAM_PROCESSES["${proc}"] ]]; then
                echo "Error: process ${proc} is given as a dependency for ${processname}, but it does not exist" >&2
                exit 1
            fi
        done

    done
}

########
debasher::_print_final_procspec()
{
    local cmdline=$1

    # Iterate over process specifications
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local process_spec="${DEBASHER_FINAL_PROCESS_SPEC[${processname}]}"
        echo "${process_spec}"
    done
}
