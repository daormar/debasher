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
debasher::_program_process_spec_is_ok()
{
    # NOTE: Process specification is a set of entries, each one
    # containing the process name, computational specifications and
    # additional specifications. The two types of specifications are
    # separated by a especial symbol
    local process_spec=$1

    if [[ "${process_spec}" != *"${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}"* ]]; then
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

    IFS="${sep}" read -r -a fields <<< "${attr_list}"
    local field
    for field in "${fields[@]}"; do
        field=$(debasher::_str_trim "${field}")
        if [[ "${field}" = "${attrname}="* ]]; then
            local attrname_len=${#attrname}
            local start=$((attrname_len + 1))
            local attr_val=${field:${start}}
            echo ${attr_val}
            return 0
        fi
    done

    echo ${DEBASHER_ATTR_NOT_FOUND}
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
    local fields=( $process_spec )
    echo ${fields[0]}
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
debasher::_extract_ext_alias_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "ext_alias"
}

########
debasher::_get_initial_process_spec_info()
{
    local procspec_file=$1

    DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED=1

    while read process_spec; do
        # Store process specification
        local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
        DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]=${process_spec}

        # Extract dependencies from process specification
        local procdeps=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`

        # Check if dependencies were given
        if [ "${procdeps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED=0
        fi
    done < "${procspec_file}"
}

########
debasher::_get_processdeps_from_detailed_spec()
{
    local processdeps_spec=$1
    local pdeps=""
    local result

    # Iterate over the elements of the process specification: type1:processname1,...,typen:processnamen or type1:processname1?...?typen:processnamen
    local separator=`debasher::_get_processdeps_separator ${processdeps_spec}`
    if [ "${separator}" = "" ]; then
        local processdeps_spec_blanks=${processdeps_spec}
    else
        local processdeps_spec_blanks=`debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps_spec}`
    fi
    local dep_spec
    for dep_spec in ${processdeps_spec_blanks}; do
        local processname=`debasher::_get_processname_part_in_dep ${dep_spec}`
        if [ -z "${result}" ]; then
            result="$processname"
        else
            result=${result}${DEBASHER_PROCESSDEPS_SEP_COMMA}${processname}
        fi
    done

    echo ${result}
}

########
debasher::_gen_final_procspec_info()
{
    local cmdline=$1
    local initial_procspec_file=$2

    # Iterate over process specifications
    while read process_spec; do
        if ! debasher::_program_process_spec_is_ok "$process_spec"; then
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi

        # Extract process information
        local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

        # Extract dependencies from process specification
        local procdeps=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`

        # Check if dependencies were given
        if [ "${procdeps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # Dependencies not given, so they should be obtained
            procdeps=`debasher::_get_procdeps_for_process_cached "${cmdline}" "${process_spec}"`

            # Register dependencies
            DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED["${processname}"]=`debasher::_get_processdeps_from_detailed_spec "${procdeps}"`

            # Print process specification plus process dependencies
            local augmented_process_spec
            augmented_process_spec=`debasher::_add_additional_spec "${process_spec}" "${procdeps}"`
            echo "${augmented_process_spec}"

            # Register process spec
            DEBASHER_FINAL_PROCESS_SPEC["${processname}"]="${augmented_process_spec}"
        else
            # Dependencies were given

            # Register dependencies
            DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED["${processname}"]=`debasher::_get_processdeps_from_detailed_spec "${procdeps}"`

            # Since the dependencies were given, just print process
            # specification
            echo "${process_spec}"

            # Register process spec
            DEBASHER_FINAL_PROCESS_SPEC["${processname}"]="${process_spec}"
        fi

        # Check that dependencies are correct

        # Iterate over dependencies, checking that the dependent process exists
        local -a deps_array
        IFS="${DEBASHER_PROCESSDEPS_SEP_COMMA}" read -ra deps_array <<< "${DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED[${processname}]}"
        for proc in "${deps_array[@]}"; do
            if [[ "${proc}" != "${DEBASHER_NONE_PROCESSDEP_TYPE}" && ! -v DEBASHER_PROGRAM_PROCESSES["${proc}"] ]]; then
                echo "Error: process ${proc} is given as a dependency for ${processname}, but it does not exist" >&2
                exit 1
            fi
        done

    done < "${initial_procspec_file}"
}
