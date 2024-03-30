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

# *- bash -*

extract_sched_funcs()
{
    # Define functions to be kept
    declare -A funcs_to_keep
    funcs_to_keep["get_scheduler"]=1
    funcs_to_keep["seq_execute"]=1
    funcs_to_keep["write_env_vars_and_funcs"]=1

    # Load scheduler functions
    source "${debasher_libexecdir}/debasher_lib_sched"

    # Extract functions
    while IFS= read -r varfunc; do
        if [[ ! -v funcs_to_keep["$varfunc"] ]]; then
            echo "${varfunc}"
        fi
    done < <(compgen -A function)
}

unset_previous_vars_and_funcs()
{
    # Unset variables
    while IFS= read -r varname; do
        if [ "${varname}" != "debasher_libexecdir" ] && [ "${varname}" != "debasher_bindir" ] && [ "${varname}" != "funcs_to_unset" ]; then
            unset "${varname}"
        fi
    done < <(compgen -v)

    # Unset functions
    while IFS= read -r varfunc; do
        if [ "${varfunc}" != "unset_vars_and_funcs" ]; then
            unset "${varfunc}"
        fi
    done < <(compgen -A function)

    # Unset conda-related functions
    for conda_func in __conda_activate __conda_exe __conda_hashr __conda_reactivate conda; do
        unset "${conda_func}"
    done
}

unset_vars_and_funcs()
{
    local funcs_to_unset=$1
    while read -r funcname; do
        unset "${funcname}"
    done <<< "${funcs_to_unset}"
}

if [ "$#" -gt 0 ]; then
    echo "Usage: debasher_get_deblib_vars_and_funcs"
    exit 1
fi

# Extract functions to be unset
funcs_to_unset=`extract_sched_funcs`

# Unset previously defined variables and functions
unset_previous_vars_and_funcs

# Load variables and functions
source "${debasher_bindir}/debasher_lib"

# Unset unnecessary variables and functions
unset_vars_and_funcs "${funcs_to_unset}"
unset "funcs_to_unset"

# Print variables and functions
set
