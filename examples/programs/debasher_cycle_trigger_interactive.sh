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
debasher_cycle_trigger_interactive_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
master_document()
{
    process_description "Executes a process reading and writing from fifos."
}

########
master_explain_cmdline_opts()
{
    # -n option
    local description="Value limit used to stop cycling"
    explain_cmdline_req_opt "-n" "<int>" "$description"
}

########
master_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -n option
    define_cmdline_opt "$cmdline" "-n" optlist || return 1

    # Define option for external FIFO
    local fifoname="proc_a_trigger"
    define_fifo_opt "-trigger" "${fifoname}" optlist || return 1

    # Define option for output FIFO
    local fifoname="proc_a_fifo"
    define_fifo_opt "-outf" "${fifoname}" optlist || return 1

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "worker" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
master()
{
    # Initialize variables
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local trigger_fifo=$(read_opt_value_from_func_args "-trigger" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Set initial value
    local initial_value=$(cat "${trigger_fifo}")

    while [ "${initial_value}" != "${SHUTDOWN_TOKEN}" ]; do
        # Send value for transformation until is equal or greater than n
        local value="${initial_value}"
        echo "* Initial value ${value}"
        while [ "${value}" -le "${n}" ]; do
            echo "${value}" > "${outf}"
            echo "Sent value ${value}"
            value=$(cat "${inf}")
            echo "Received value ${value}"
            echo ""
        done

        # Set initial value
        local initial_value=$(cat "${trigger_fifo}")
    done

    # Send shutdown token
    echo "${SHUTDOWN_TOKEN}" > "${outf}"
}

########
worker_document()
{
    process_description "Executes a process reading and writing from fifos."
}

########
worker_explain_cmdline_opts()
{
    # -threshold option
    local description="Threshold value used to influence number transformation"
    explain_cmdline_req_opt "-threshold" "<int>" "$description"
}

########
worker_define_opts()
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
    define_opt_from_proc_out "-inf" "master" "-outf" optlist || return 1

    # Define option for external FIFO
    local fifoname="proc_b_threshold"
    define_fifo_opt "-threshold" "${fifoname}" optlist || return 1

    # Define option for output directory
    define_opt "-outd" "${process_outdir}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
transformation_a()
{
    local value=$1
    local outf=$2

    value=$((value + 1))
    echo ${value} > ${outf}
}

########
transformation_b()
{
    local value=$1
    local outf=$2

    value=$((value + 2))
    echo ${value} > ${outf}
}

########
worker()
{
    local threshold_fifo=$(read_opt_value_from_func_args "-threshold" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    # Execute loop until the shutdown token is received
    local sum=0
    while true; do
        # Read value
        value=$(cat "${inf}")
        echo "Received value ${value}"
        if [ "${value}" = "${SHUTDOWN_TOKEN}" ]; then
            break
        fi

        # Read threshold
        local threshold=$(read_fifo_line "${threshold_fifo}")
        echo "Threshold value ${threshold}"

        # Decide transformation function depending on threshold
        if [ "${sum}" -le "${threshold}" ]; then
            seq_execute_slurm transformation_a "${value}" "${outd}/transformation_result.txt"
            value=$(cat "${outd}/transformation_result.txt")
        else
            seq_execute_slurm transformation_b "${value}" "${outd}/transformation_result.txt"
            value=$(cat "${outd}/transformation_result.txt")
        fi

        # Update sum
        sum=$((sum + value))

        echo "Transformed value ${value}"
        echo "Sum ${sum}"
        echo ""

        # Send current value
        echo "${value}" > "${outf}"
    done

    echo "Final value of sum: ${sum}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_cycle_trigger_interactive_program()
{
    add_debasher_process "master" "cpus=1 mem=32 time=00:10:00"
    add_debasher_process "worker" "cpus=1 mem=32 time=00:10:00"
}
