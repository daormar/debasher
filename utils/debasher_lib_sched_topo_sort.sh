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

###################################################
# SCHEDULER FUNCTIONS RELATED TO TOPOLOGICAL SORT #
###################################################

########
#!/usr/bin/env bash

# topo_sort <assoc_array_name_deps> <result_array_name>
debasher::topo_sort()
{
    local -n _deps=$1      # reference to the associative array of dependencies
    local -n _result=$2    # reference to the output array (final order)

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
        if [[ -n $depstr && $depstr != "none" ]]; then
            local IFS=','
            local dep
            for dep in $depstr; do
                if [[ -z ${_deps[$dep]+x} ]]; then
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
