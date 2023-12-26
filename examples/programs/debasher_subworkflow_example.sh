# DeBasher package
# Copyright (C) 2019,2020 Daniel Ortiz-Mart\'inez
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
load_debasher_module "debasher_array_example"
load_debasher_module "debasher_fifo_example"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_subworkflow_example_shared_dirs()
{
    :
}

######################
# PROGRAM PROCESSES #
######################

########
debasher_subworkflow_example_program()
{
    add_debasher_program "debasher_array_example" "test"
    add_debasher_program "debasher_fifo_example" "test"
}
