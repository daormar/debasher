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
debasher_host_workflow_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
process_a_document()
{
    process_description "Takes a string as input and prints it to a file"
}

########
process_a_explain_cmdline_opts()
{
    # -s option
    local description="Input string"
    explain_cmdline_req_opt "-s" "<string>" "$description"
}

########
process_a_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -s option
    define_cmdline_opt "$cmdline" "-s" optlist || return 1

    # -outf option
    define_opt "-outf" "${process_outdir}/outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_a()
{
    # Initialize variables
    local str=$(read_opt_value_from_func_args "-s" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Print string to file
    echo "${str}" > "${outf}"
}

########
process_b_explain_cmdline_opts()
{
    # -inf option
    local description="Input file"
    explain_cmdline_req_opt "-inf" "<str>" "$description"
}

########
process_b_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -inf option
    define_cmdline_opt "$cmdline" "-inf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_b()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Print content of input file to the standard output
    cat "${inf}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_net_reconf_1_program()
{
    add_debasher_process "process_a" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "process_b" "cpus=1 mem=32 time=00:10:00"
}
