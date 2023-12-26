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
host1_document()
{
    process_description "Executes an array of n tasks. Each task creates a file containing host name."
}

########
host1_explain_cmdline_opts()
{
    # -n option
    local description="Number of array tasks"
    explain_cmdline_req_opt "-n" "<int>" "$description"
}

########
host1_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -n option
    local n_opt=$(get_cmdline_opt "$cmdline" "-n")

    # Save option list so as to execute process n times
    for id in $(seq "${n_opt}"); do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        define_opt "-outf" "${process_outdir}/${id}" specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
host1()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Show host name
    hostname

    # Create file
    echo -n "" > "${outf}"
}

########
host2_explain_cmdline_opts()
{
    # -n option
    local description="Number of array tasks"
    explain_cmdline_req_opt "-n" "<int>" "$description"
}

########
host2_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -n option
    local n_opt=$(get_cmdline_opt "$cmdline" "-n")

    # Obtain output directory for host1
    local host1_outdir=`get_process_outdir_adaptive "host1"`

    # Save option list so as to execute process n times
    for id in $(seq "${n_opt}"); do
        local specific_optlist=${optlist}
        define_opt "-infile" "${host1_outdir}/${id}" specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
host2()
{
    # Initialize variables
    local infile=$(read_opt_value_from_func_args "-infile" "$@")

    # Show host name
    hostname
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_host_workflow_program()
{
    add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64"
    add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64"
}
