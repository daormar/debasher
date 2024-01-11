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

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_hello_world_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
hello_world_document()
{
    process_description "Prints a hello world message."
}

########
hello_world_explain_cmdline_opts()
{
    # -n option
    local description="Name to be included in hello message"
    explain_cmdline_opt "-n" "<string>" "$description"
}

########
hello_world_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Obtain value of -n option
    local name=`get_cmdline_opt "${cmdline}" "-n"`
    echo "****** $name"
    
    # -n option
    if [ "${name}" = "${OPT_NOT_FOUND}" ]; then
        define_opt "-n" "World" optlist || return 1
    else
        define_opt "-n" "$name" optlist || return 1
    fi

    # Save option list
    save_opt_list optlist
}

########
hello_world()
{
    # Initialize variables
    local name=$(read_opt_value_from_func_args "-n" "$@")

    # Show message
    echo "Hello ${name}!"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_hello_world_program()
{
    add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00,00:02:00,00:03:00"
}
