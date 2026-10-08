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

# Load modules
load_debasher_module "debasher_dynamic_fanout"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_dynamic_fanout_stepdone_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
worker_stepdone_document()
{
    document_process "Executes an array of w tasks. Each task takes a list of text files and generates another file for each one, as a step. Each step that succeeds is marked as done, so that a new run does not execute it again."
}

########
worker_stepdone_reset_outfiles()
{
    # The output directory of the worker is not reset, so that the
    # markers of the steps that succeeded survive to the next run
    :
}

########
worker_stepdone_explain_opts()
{
    # -id option
    local description="id of writer"
    explain_opt "-id" "<int>" "$description"

    # -inf option
    local description="input file"
    explain_opt "-inf" "<file>" "$description"

    # -outd option
    local description="output directory"
    explain_opt "-outd" "<file>" "$description"
}

########
worker_stepdone_explain_task_shaping_opts()
{
    # -w option
    local description="Number of workers."
    explain_task_shaping_opt "-w" "<int>" "$description"
}

########
worker_stepdone_identify_cmdline_opts()
{
    :
}

########
worker_stepdone_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # Build one array element per worker task
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    local array=()
    for ((i=0; i<w; i++)); do
        array+=("$i")
    done

    for idx in "${!array[@]}"; do
        local optlist=""
        define_opt "-id" "${idx}" optlist || return 1
        define_opt_from_proc_out "-inf" "dispatch" "-outf${idx}" optlist || return 1
        define_opt "-outd" "${process_outdir}/${idx}" optlist || return 1
        save_opt_list optlist
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
worker_stepdone()
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
    while IFS= read -r filepath; do
        [ -z "$filepath" ] && continue
        [ -e "$filepath" ] || continue

        local base
        base=$(basename "$filepath")

        # The id of the step carries a checksum of its input, so that
        # the marker of an earlier run stops counting when the block
        # changes
        local sum
        sum=$(cksum < "$filepath" | awk '{print $1}')
        local stepid
        stepid="${id}_${base}_${sum}"

        # Execute the step of the worker, only if it is not marked as
        # done. The step reads its standard input from /dev/null, since
        # under Slurm srun would take the rest of the list from the loop
        if is_step_done "${outd}" "${stepid}"; then
            echo "Step ${stepid} was already completed and marked as done" >&2
        else
            # Remove the markers of this block left by an earlier run
            # with another input, since the step overwrites the output
            # they stand for
            rm -f "${outd}/${DEBASHER_STEP_MARKER_PREFIX}${id}_${base}_"*
            if seq_execute worker_task "$filepath" "$outd/$base" < /dev/null; then
                mark_step_done "${outd}" "${stepid}" || return 1
                echo "Step ${stepid} completed and marked as done" >&2
            else
                exit_code=1
                echo "Error: step ${stepid} failed" >&2
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
    local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        define_opt_from_proc_task_out "-ind${i}" "worker_stepdone" "${i}" "-outd" optlist || return 1
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
debasher_dynamic_fanout_stepdone_program()
{
    add_debasher_process "generate"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "count"           "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fragment"        "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:count"
    add_debasher_process "dispatch"        "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "worker_stepdone" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "aggregate"       "cpus=1 mem=32 time=00:01:00"
}
