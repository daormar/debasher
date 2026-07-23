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

################################################
# SCHEDULER FUNCTIONS RELATED TO PROCESS RERUN #
################################################

########
debasher::_mark_process_as_rerun()
{
    local processname=$1
    local reason=$2

    if [ "${DEBASHER_RERUN_PROCESSES[${processname}]}" = "" ]; then
        DEBASHER_RERUN_PROCESSES[${processname}]=${reason}
    else
        local curr_val="${DEBASHER_RERUN_PROCESSES[${processname}]}"
        if [[ ",$curr_val," != *",$reason,"* ]]; then
            DEBASHER_RERUN_PROCESSES[${processname}]="${curr_val},${reason}"
        fi
    fi
}

########
debasher::_num_processes_marked_as_rerun()
{
    echo "${#DEBASHER_RERUN_PROCESSES[@]}"
}

########
debasher::_there_are_processes_to_rerun()
{
    local num_procs_rerun="${#DEBASHER_RERUN_PROCESSES[@]}"

    if (( num_procs_rerun > 0 )); then
        return 0
    else
        return 1
    fi
}

########
debasher::_get_rerun_processes_as_string()
{
    local result=""
    for processname in "${!DEBASHER_RERUN_PROCESSES[@]}"; do
        if [ "${result}" = "" ]; then
            result=${processname}
        else
            result="${result},${processname}"
        fi
    done

    echo ${result}
}

########
debasher::_process_marked_as_rerun()
{
    local processname=$1

    if [ "${DEBASHER_RERUN_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        return 0
    fi
}
