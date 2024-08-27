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
debasher_cycle_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
process_a_document()
{
    process_description "Executes a process reading and writing from fifos."
}

########
process_a_explain_cmdline_opts()
{
    # -n option
    local description="Number of cycles to execute"
    explain_cmdline_req_opt "-n" "<int>" "$description"
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

    # -n option
    define_cmdline_opt "$cmdline" "-n" optlist || return 1

    # Define option for output FIFO
    local fifoname="proc_a_fifo"
    define_fifo_opt "-outf" "${fifoname}" optlist || return 1

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "process_b" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_a()
{
    # Initialize variables
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Increase value iteratively until it reaches n
    local value=1
    while [ "${value}" -le "${n}" ]; do
        echo "${value}" > "${outf}"
        echo "Sent value ${value}"
        value=$(cat "${inf}")
        echo "Received value ${value}"
        echo ""
    done

    # Send shutdown token
    echo "${SHUTDOWN_TOKEN}" > "${outf}"
}

########
process_b_document()
{
    process_description "Executes a process reading and writing from fifos."
}

########
process_b_explain_cmdline_opts()
{
    :
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

    # Define option for output FIFO
    local fifoname="proc_b_fifo"
    define_fifo_opt "-outf" "${fifoname}" optlist || return 1

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "process_a" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_b()
{
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Execute loop until the shutdown token is received
    while true; do
        value=$(cat "${inf}")
        echo "Received value ${value}"
        if [ "${value}" = "${SHUTDOWN_TOKEN}" ]; then
            break
        fi
        value=$((value + 1))
        echo "Transformed value ${value}"
        echo ""
        echo "${value}" > "${outf}"
    done
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_cycle_program()
{
    add_debasher_process "process_a" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "process_b" "cpus=1 mem=32 time=00:10:00"
}
