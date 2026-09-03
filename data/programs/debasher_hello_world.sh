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
    document_process "Prints a hello world message."
}

########
hello_world_explain_opts()
{
    # -s option
    local description="String to be displayed ('Hello World!' by default)"
    explain_opt "-s" "<string>" "$description"
}

########
hello_world_identify_cmdline_opts()
{
    opt_is_non_mandatory_cmdline "-s"
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

    # -s option
    define_cmdline_opt_if_given "${cmdline}" "-s" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
hello_world()
{
    # Initialize variables
    local str=$(read_opt_value_from_func_args "-s" "$@")

    if [ "${str}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
        str="Hello World!"
    fi

    # Show message
    echo "${str}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_hello_world_program()
{
    add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
}
