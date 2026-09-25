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

# Prints the absolute path of a program file, resolved as
# load_debasher_module resolves a module: a relative path is looked for
# in the current directory and then in the directories of
# DEBASHER_MOD_DIR. Used by the ProgramLauncher of the runtime library,
# which runs it from the directory of the module that declares the node.

if [ "$#" -ne 1 ]; then
    echo "Usage: debasher_resolve_pfile <pfile>" >&2
    exit 1
fi

debasher::_resolve_pfile "$1"
