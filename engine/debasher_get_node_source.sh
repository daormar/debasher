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

# INCLUDE BASH LIBRARY
. "${debasher_pkglibdir}"/debasher_lib || exit 1

########
print_desc()
{
    echo "debasher_get_node_source prints the Python code of a node of a resident program"
    echo "Usage: debasher_get_node_source <prgfile> <processname>"
    echo "Notes: the code is the text of the Python heredoc of the process, as the engine runs it; it is"
    echo "       what the node harness of the business tests builds the node from"
}

########

if [ $# -ne 2 ]; then
    print_desc >&2
    exit 1
fi

pfile=$(debasher::_resolve_pfile "$1") || exit 1
processname=$2

# The standard output carries the code alone: loading the module says
# nothing, and whatever the module itself prints goes to the standard
# error
DEBASHER_QUIET_MODULE_LOADING=1
debasher::load_debasher_module "${pfile}" >&2 || exit 1

if ! debasher::_get_resident_process_source "${processname}"; then
    echo "Error: process ${processname} has no Python heredoc in ${pfile}" >&2
    exit 1
fi
