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

if [ "$#" -ne 2 ]; then
    echo "Usage: debasher_get_verbatim_func_source <file> <funcname>" >&2
    exit 1
fi

file=$1
funcname=$2

# extdebug must already be active *before* sourcing "$file" so that
# every function it defines (not just ones defined afterwards) is
# recorded with its (file, line) origin -- see
# debasher::_get_verbatim_func_source in engine/debasher_lib_utils.sh.
shopt -s extdebug
source "$file" || exit 1

debasher::_get_verbatim_func_source "${funcname}"
