# PanPipe package
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
panpipe_host_workflow_shared_dirs()
{
    :
}

#######################################
# PIPELINE SOFTWARE TESTING PROCESSES #
#######################################

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

    # -f option
    define_cmdline_opt "$cmdline" "-n" optlist || return 1

    # Define output FIFO
    local fifoname="proc_a_fifo"
    define_fifo "${fifoname}"

    # Get absolute name of output FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for output FIFO
    define_opt "-outf" "${abs_fifoname}" optlist || return 1

    # Get absolute name of input FIFO
    local fifo_proc_b=$(get_adaptive_processname "process_b")
    local fifoname="proc_b_fifo"
    local abs_fifoname=$(get_absolute_fifoname "${fifo_proc_b}" "${fifoname}")

    # Define option for input FIFO
    define_opt "-inf" "${abs_fifoname}" optlist || return 1

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
        value=$((value + 1))
    done

    # Send END message
    echo "END" > "${outf}"
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

    # Define output FIFO
    local fifoname="proc_b_fifo"
    define_fifo "${fifoname}"

    # Get absolute name of output FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for output FIFO
    define_opt "-outf" "${abs_fifoname}" optlist || return 1

    # Get absolute name of input FIFO
    local fifo_proc_a=$(get_adaptive_processname "process_a")
    local fifoname="proc_a_fifo"
    local abs_fifoname=$(get_absolute_fifoname "${fifo_proc_a}" "${fifoname}")

    # Define option for input FIFO
    define_opt "-inf" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_b()
{
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Execute loop until the END message is received
    while true; do
        value=$(cat "${inf}")
        echo "Received value ${value}"
        if [ "${value}" = "END" ]; then
            break
        fi
        echo "${value}" > "${outf}"
    done
}

##################################
# PIPELINE DEFINED BY THE MODULE #
##################################

########
panpipe_cycle_pipeline()
{
    add_panpipe_process "process_a" "cpus=1 mem=32 time=00:10:00"
    add_panpipe_process "process_b" "cpus=1 mem=32 time=00:10:00"
}
