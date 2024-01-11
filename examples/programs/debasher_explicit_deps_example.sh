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

# Load modules
load_debasher_module "debasher_value_pass"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_explicit_deps_example_shared_dirs()
{
    :
}

#####################
# PROGRAM PROCESSES #
#####################

########
debasher_explicit_deps_example_program()
{
    add_debasher_process "value_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "value_reader" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:value_writer"
}
