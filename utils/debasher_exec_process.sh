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

# INCLUDE BASH LIBRARY
. "${debasher_bindir}"/debasher_lib || exit 1

########
print_desc()
{
    echo "debasher_process_debug executes a program process for debugging purposes"
    echo "Usage: debasher_process_debug <prgfile> <processname> <options>"
}

########
load_modules()
{
    echo "* Loading debasher modules..." >&2

    local pfile=$1

    load_debasher_module "${pfile}" || return 1

    echo "" >&2
}

########

if [ $# -lt 3 ]; then
    print_desc
    exit 1
fi

# Read parameters
pfile=$1
shift
processname=$1
shift

load_modules "${pfile}" || exit 1

echo "Executing: $processname $opts" >&2
"${processname}" "$@" || exit 1
