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
debasher_host_workflow_expl_deps_shared_dirs()
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
host1_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # -n option
    local n_opt=$(get_cmdline_opt "$cmdline" "-n")

    echo ${n_opt}
}

########
host1_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # Save option list
    define_opt "-id" ${task_idx} optlist || return 1
    save_opt_list optlist
}

########
host1()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")

    # Show host name
    hostname
}

########
host2_explain_cmdline_opts()
{
    # -n option
    local description="Number of array tasks"
    explain_cmdline_req_opt "-n" "<int>" "$description"
}

########
host2_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # -n option
    local n_opt=$(get_cmdline_opt "$cmdline" "-n")

    echo "${n_opt}"
}

########
host2_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # Save option list
    define_opt "-id" $task_idx optlist || return 1
    save_opt_list optlist
}

########
host2()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")

    # Show host name
    hostname
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_host_workflow_expl_deps_program()
{
    add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=none"
    add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=aftercorr:host1"
}
