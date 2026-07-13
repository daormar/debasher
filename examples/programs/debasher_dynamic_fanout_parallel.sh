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
load_debasher_module "debasher_dynamic_fanout"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_dynamic_fanout_parallel_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
worker_parallel_document()
{
    process_description "Executes an array of w tasks. Each task takes a list of text files and generates another file for each one. All the files are generated in parallel."
}

########
worker_parallel_explain_cmdline_opts()
{
    # -w option
    local description="Number of workers."
    explain_cmdline_req_opt "-w" "<int>" "$description"
}

########
worker_parallel_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define worker parameters
    local w
    w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        local specific_optlist=${optlist}
        define_opt "-id" $i specific_optlist || return 1
        define_opt_from_proc_out "-inf" "dispatch" "-outf$i" specific_optlist || return 1
        define_opt "-outd" "${process_outdir}/${i}" specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
worker_task()
{
    local filepath=$1
    local outf=$2

    rev "$filepath" > "$outf"
}

########
worker_parallel()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    # Create output directory
    if [ ! -d "${outd}" ]; then
        mkdir -p "${outd}"
    fi

    # Read the input file line by line (each line is a file path) and
    # launch the worker task in parallel
    pids=()
    while IFS= read -r filepath; do
        [ -z "$filepath" ] && continue
        [ -e "$filepath" ] || continue

        local base
        base=$(basename "$filepath")

        # Reverse the characters of each line in the file and save it to outd
        worker_task "$filepath" "$outd/$base" &
        pids+=($!)
        echo "Worker ${id} launched task with PID $!" >&2
    done < "$inf"

    # Wait for the processes to finish and check exit code
    local exit_code
    exit_code=0
    for i in "${!pids[@]}"; do
        wait "${pids[$i]}"
        task_exit_code=$?
        if [ ${task_exit_code} -ne 0 ]; then
            echo "Error: Worker task with PID $i failed with exit code ${task_exit_code}" >&2
            exit_code=1
        fi
    done

    return ${exit_code}
}

########
aggregate_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -w option
    define_cmdline_opt "$cmdline" "-w" optlist || return 1

    # Define parameters so as to collect workers output
    local w
    w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        define_opt_from_proc_task_out "-ind$i" "worker_parallel" "${i}" "-outd" optlist || return 1
    done

    # Define name of output file
    local outf="${process_outdir}/result.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_dynamic_fanout_parallel_program()
{
    add_debasher_process "generate"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fragment"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "dispatch"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "worker_parallel" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "aggregate"       "cpus=1 mem=32 time=00:01:00"
}
