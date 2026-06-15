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
program_process_spec_is_ok()
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
extract_comp_specs()
{
    local process_spec=$1

    # Keep text before the separator marking the beginning of additional
    # specs
    local specs="${process_spec%%${BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}*}"

    # Keep everything except the first word, which is the name of
    # process
    read -r first rest <<< "$specs"
    echo "$rest"
}

########
extract_additional_specs()
{
    local process_spec=$1

    # Keep text after the separator marking the beginning of additional
    # specs
    local specs="${process_spec#*${BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}}"
    echo "$specs"
}

########
add_additional_spec()
{
    local process_spec=$1
    local procdeps=$2

    local additional_specs=$(extract_additional_specs "${process_spec}")
    if [ -z "${additional_specs}" ]; then
        echo "${process_spec} ${procdeps}"
    else
        echo "${process_spec} ${ADDITIONAL_PROCSPECS_SEP} ${procdeps}"
    fi
}

########
extract_attr_from_process_comp_specs()
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

    echo ${ATTR_NOT_FOUND}
}

########
extract_attr_from_process_additional_specs()
{
    local process_comp_specs=$1
    local attrname=$2

    IFS="${ADDITIONAL_PROCSPECS_SEP}" read -r -a fields <<< "${process_comp_specs}"

    local field
    for field in "${fields[@]}"; do
        field=$(str_trim "${field}")
        if [[ "${field}" = "${attrname}="* ]]; then
            local attrname_len=${#attrname}
            local start=$((attrname_len + 1))
            local attr_val=${field:${start}}
            echo ${attr_val}
            return 0
        fi
    done

    echo ${ATTR_NOT_FOUND}
}

########
extract_processname_from_process_spec()
{
    local process_spec=$1
    local fields=( $process_spec )
    echo ${fields[0]}
}

########
extract_cpus_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "cpus"
}

########
extract_mem_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "mem"
}

########
extract_time_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "time"
}

########
extract_nodes_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "nodes"
}

########
extract_account_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "account"
}

########
extract_partition_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "partition"
}

########
extract_throttle_from_process_spec()
{
    local process_spec=$1
    local process_comp_specs=$(extract_comp_specs "${process_spec}")
    extract_attr_from_process_comp_specs "${process_comp_specs}" "throttle"
}

########
extract_processdeps_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(extract_additional_specs "${process_spec}")
    extract_attr_from_process_additional_specs "${process_additional_specs}" "${PROCESSDEPS_SPEC}"
}

########
extract_force_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(extract_additional_specs "${process_spec}")
    extract_attr_from_process_additional_specs "${process_addictional_specs}" "force"
}

########
extract_alias_from_process_spec()
{
    local process_spec=$1
    local process_additional_specs=$(extract_additional_specs "${process_spec}")
    extract_attr_from_process_additional_specs "${process_addictional_specs}" "alias"
}
