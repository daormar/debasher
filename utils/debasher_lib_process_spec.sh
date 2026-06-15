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
debasher::program_process_spec_is_ok()
{
    # NOTE: Process specification is a set of entries, each one
    # containing the process name, computational specifications and
    # additional specifications
    local process_spec=$1

    local fieldno=1
    local field
    for field in $process_spec; do
        fieldno=$((fieldno + 1))
    done

    if [ "${fieldno}" -gt 1 ]; then
        return 0
    else
        return 1
    fi
}

########
debasher::extract_comp_specs()
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
debasher::extract_additional_specs()
{
    local process_spec=$1

    # Keep text after the separator marking the beginning of additional
    # specs
    local specs="${process_spec#*${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}}"
    echo "$specs"
}

########
debasher::add_additional_spec()
{
    local process_spec=$1
    local procdeps=$2

    local additional_specs=$(debasher::extract_additional_specs "${process_spec}")
    if [ -z "${additional_specs}" ]; then
        echo "${process_spec} ${procdeps}"
    else
        echo "${process_spec} ${DEBASHER_ADDITIONAL_PROCSPECS_SEP} ${procdeps}"
    fi
}

########
debasher::extract_attr_from_process_comp_specs()
{
    local process_comp_specs=$1
    local attrname=$2

    local field
    for field in $process_comp_specs; do
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
debasher::extract_attr_from_process_additional_specs()
{
    local process_comp_specs=$1
    local attrname=$2

    IFS="${DEBASHER_ADDITIONAL_PROCSPECS_SEP}" read -r -a fields <<< "${process_comp_specs}"

    local field
    for field in "${fields[@]}"; do
        field=$(debasher::str_trim "${field}")
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
debasher::extract_processname_from_process_spec()
{
    local process_spec=$1
    local fields=( $process_spec )
    echo ${fields[0]}
}

########
debasher::extract_cpus_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "cpus"
}

########
debasher::extract_mem_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "mem"
}

########
debasher::extract_time_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "time"
}

########
debasher::extract_nodes_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "nodes"
}

########
debasher::extract_account_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "account"
}

########
debasher::extract_partition_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "partition"
}

########
debasher::extract_throttle_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(debasher::extract_comp_specs "${process_spec}")
    debasher::extract_attr_from_process_comp_specs "${process_comp_specs}" "throttle"
}

########
debasher::extract_processdeps_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "${DEBASHER_PROCESSDEPS_SPEC}"
}

########
debasher::extract_force_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_addictional_specs}" "force"
}

########
debasher::extract_alias_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(debasher::extract_additional_specs "${process_spec}")
    debasher::extract_attr_from_process_additional_specs "${process_addictional_specs}" "alias"
}
