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

# *- bash -*

unset_previous_vars_and_funcs()
{
    # Unset variables
    for var in $(compgen -v); do
        if [ "${var}" != "PATH" ]; then
            unset ${var}
        fi
    done

    # Unset functions
    unset -f $(compgen -A function)

    # Handle conda-related functions
    for conda_func in __conda_activate __conda_exe __conda_hashr __conda_reactivate conda; do
        unset "${conda_func}"
    done
}

debasher::load_debasher_module()
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

# Print variables and functions. Every associative array is declared first,
# with its type and contents (declare -p -A), leaving out bash's own and the
# read-only ones, which cannot be declared again: "set" prints an
# associative array without its type, NAME=([key]="value" ...), which read
# back creates an indexed array with every key evaluated as a number, and
# does not print one declared with no value at all. Declared first, the
# array keeps its type, and the line of "set" that follows fills it as it
# should. A loop and not a function, since every function defined here is
# unset above.
while IFS= read -r debasher_assoc_decl; do
    # The attributes are the second word, "-A" or "-Ar"
    debasher_assoc_attrs="${debasher_assoc_decl#declare }"
    debasher_assoc_attrs="${debasher_assoc_attrs%% *}"
    case "${debasher_assoc_decl}" in
        "declare ${debasher_assoc_attrs} BASH_"*) ;;
        *)
            case "${debasher_assoc_attrs}" in
                *r*) ;;
                *) echo "${debasher_assoc_decl}" ;;
            esac
            ;;
    esac
done < <(declare -p -A)
unset debasher_assoc_decl debasher_assoc_attrs
set
