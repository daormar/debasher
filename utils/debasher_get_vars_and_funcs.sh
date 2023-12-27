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

unset_previous_vars_and_funcs()
{
    unset -v $(compgen -v) && unset -f $(compgen -A function)

    for conda_func in __conda_activate __conda_exe __conda_hashr __conda_reactivate conda; do
        unset "${conda_func}"
    done
}

load_debasher_module()
{
    # NOTE: this function is intentionally defined void
    :
}

if [ "$#" -eq 0 ]; then
    echo "Usage: debasher_get_vars_and_funcs <file1> <file2> ... <filen>"
    exit 1
fi

# Unset previously defined variables and functions
unset_previous_vars_and_funcs

# Load all files given
for arg in "$@"; do
    source "${arg}"
done

# Print variables and functions
set
