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

###################################################
# SCHEDULER FUNCTIONS RELATED TO TOPOLOGICAL SORT #
###################################################

########
# debasher::_topo_sort <dependency_separator> <assoc_array_name_deps> <result_array_name>
debasher::_topo_sort()
{
    local dep_sep=$1       # Character used as dependency separator
    local -n _deps=$2      # reference to the associative array of dependencies
    local -n _result=$3    # reference to the output array (final order)

    local -A _state        # 0=unvisited, 1=in progress, 2=done
    local _order=()

    _visit() {
        local node=$1
        local st=${_state[$node]:-0}

        # Already processed: nothing to do
        (( st == 2 )) && return 0

        # "In progress" within the same recursion branch => cycle
        if (( st == 1 )); then
            echo "Error: circular dependency detected at '$node'" >&2
            exit 1
        fi

        _state[$node]=1

        local depstr=${_deps[$node]}
        if [[ -n $depstr && $depstr != "${DEBASHER_NONE_PROCESSDEP_TYPE}" ]]; then
            local -a deps_array
            IFS="${dep_sep}" read -ra deps_array <<< "${depstr}"
            local dep
            for dep in "${deps_array[@]}"; do
                if [[ ! -v _deps[$dep] ]]; then
                    echo "Error: '$dep' (dependency of '$node') is not defined" >&2
                    exit 1
                fi
                _visit "$dep"
            done
        fi

        _state[$node]=2
        _order+=("$node")
    }

    local key
    for key in "${!_deps[@]}"; do
        _visit "$key"
    done

    _result=("${_order[@]}")
}

########
debasher::_topo_sort_processes()
{
    debasher::_topo_sort "${DEBASHER_PROCESSDEPS_SEP_COMMA}" DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED DEBASHER_PROGRAM_PROCESSES_TOPO_SORT
}
