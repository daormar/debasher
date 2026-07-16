# DeBasher package
# Copyright (C) 2019-2024 Daniel Ortiz-Mart\'inez
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
