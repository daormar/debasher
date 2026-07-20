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
debasher_dynamic_fanout_taskdone_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
worker_taskdone_document()
{
    process_description "Executes an array of w tasks. Each task takes a list of text files and generates another file for each one. When each subtask is completed, it is marked as done, so that they it is not reexecuted."
}

########
worker_taskdone_reset_outdir()
{
    # Output directory for worker is not reset, so as to enable marking
    # tasks as done
    :
}

########
worker_taskdone_explain_cmdline_opts()
{
    # -w option
    local description="Number of workers."
    explain_cmdline_req_opt "-w" "<int>" "$description"
}

########
worker_taskdone_define_opts()
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
bernoulli_trial()
{
    local prob=$1
    local value=$((RANDOM % 100))

    if (( value < prob )); then
        echo 0
    else
        echo 1
    fi
}

########
worker_task()
{
    local filepath=$1
    local outf=$2
    local retcode

    # Randomly generate return code so as to simulate failing tasks
    retcode=$(bernoulli_trial 75)

    if [ "${retcode}" -eq 0 ]; then
        count_chars "$filepath" > "$outf"
    else
        return "${retcode}"
    fi
}

########
worker_taskdone()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    local exit_code=0

    # Create output directory
    if [ ! -d "${outd}" ]; then
        mkdir -p "${outd}"
    fi

    # Read the input file line by line (each line is a file path)
    local retval=$?
    while IFS= read -r filepath; do
        [ -z "$filepath" ] && continue
        [ -e "$filepath" ] || continue

        local base
        base=$(basename "$filepath")

        local taskid
        taskid="${id}_${base}"

        # Execute worker task. The task is only carried out if it is not
        # marked as done
        if debasher::is_task_done "${outd}" "${taskid}"; then
            echo "Task ${taskid} was already completed and marked as done" >&2
        else
            worker_task "$filepath" "$outd/$base"
            retval=$?
            if [ "${retval}" -eq 0 ]; then
                debasher::mark_task_done "${outd}" "${taskid}" || return 1
                echo "Task ${taskid} completed and marked as done" >&2
            else
                exit_code=1
                echo "Error: task ${taskid} failed with exit code ${retval}" >&2
            fi
        fi
    done < "$inf"

    return "${exit_code}"
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
        define_opt_from_proc_task_out "-ind$i" "worker_taskdone" "${i}" "-outd" optlist || return 1
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
debasher_dynamic_fanout_taskdone_program()
{
    add_debasher_process "generate"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "count"           "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fragment"        "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:count"
    add_debasher_process "dispatch"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "worker_taskdone" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "aggregate"       "cpus=1 mem=32 time=00:01:00"
}
