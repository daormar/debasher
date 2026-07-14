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
debasher_dynamic_fanout_fifos_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
generate_document()
{
    process_description "Generates a text file of a given size and random content."
}

########
generate_explain_cmdline_opts()
{
    # -l option
    local description="Length of file in lines"
    explain_cmdline_req_opt "-n" "<int>" "$description"

    # -c option
    local description="Length of each line in characters"
    explain_cmdline_req_opt "-c" "<int>" "$description"
}

########
generate_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -l option
    define_cmdline_opt "$cmdline" "-l" optlist || return 1

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Define name of output file
    local outf="${process_outdir}/file.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
generate()
{
    # Initialize variables
    local numlines=$(read_opt_value_from_func_args "-l" "$@")
    local numchars=$(read_opt_value_from_func_args "-c" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Clear/create the output file
    > "$outf"

    for ((i = 1; i <= numlines; i++)); do
        # Generate a line of numchars random alphanumeric characters
        tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$numchars" >> "$outf"
        echo >> "$outf"
    done
}

########
fragment_document()
{
    process_description "Fragments an input file into a given number of equally sized blocks, inverting the file lines."
}

########
fragment_explain_cmdline_opts()
{
    # -b option
    local description="Number of blocks"
    explain_cmdline_req_opt "-b" "<int>" "$description"
}

########
fragment_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-b" optlist || return 1

    # -inf option
    define_opt_from_proc_out "-inf" "generate" "-outf" optlist || return 1

    # Define name of output directory
    define_opt "-outd" "${process_outdir}" optlist || return 1

    # Define option for output FIFO
    local fifoname="fragment_fifo"
    define_fifo_opt "-outf" "${fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
fragment_task()
{
    local inf=$1
    local outf=$2

    rev "${inf}" > "${outf}"
}

########
fragment()
{
    # Initialize variables
    local numblocks=$(read_opt_value_from_func_args "-b" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Count the total number of lines in the input file
    local total_lines
    total_lines=$(wc -l < "$inf")

    # Calculate how many lines correspond to each block (rounded up)
    local lines_per_block=$(( (total_lines + numblocks - 1) / numblocks ))

    # Split the file into temporary blocks
    local tmpd
    tmpd=$(mktemp -d)
    split -l "$lines_per_block" -d -a 4 "$inf" "$tmpd/part_" || return 1

    # Process each block: reverse the characters of each line
    exec 3> "${outf}"
    local i=0
    for part in "$tmpd"/part_*; do
        [ -e "$part" ] || continue
        fragment_task "$part" "$outd/blk${i}.txt" || return 1
        echo "$outd/blk${i}.txt" > "${outf}" || return 1
        ((i++))
    done
    exec 3>&-

    # Clean up the temporary directory
    rm -rf "$tmpd"
}

########
dispatch_document()
{
    process_description "Dispatches file blocks to workers."
}

########
dispatch_explain_cmdline_opts()
{
    # -w option
    local description="Number of workers."
    explain_cmdline_req_opt "-w" "<int>" "$description"

    # --log-level option
    local description="Logging verbosity. Choices: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)."
    explain_cmdline_opt "--log-level" "<string>" "$description"
}

########
dispatch_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -w option
    define_cmdline_opt "$cmdline" "-w" optlist || return 1

    # --log-level option
    define_cmdline_nonmandatory_opt "$cmdline" "--log-level" "INFO" optlist || return 1

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "fragment" "-outf" optlist || return 1

    # Add output option for w files
    local w
    w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        local fifoname="dispatch_fifo_${i}"
        define_fifo_opt "-outf$i" "${fifoname}" optlist || return 1
    done

    # Save option list
    save_opt_list optlist
}

########
worker_document()
{
    process_description "Executes an array of w tasks. Each task takes a list of text files and generates another file for each one."
}

########
worker_explain_cmdline_opts()
{
    # -w option
    local description="Number of workers."
    explain_cmdline_req_opt "-w" "<int>" "$description"
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
    local inf=$1
    local outf=$2

    rev "${inf}" > "${outf}"
}

########
worker()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

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

        # Reverse the characters of each line in the file and save it to outd
        worker_task "$filepath" "$outd/$base" || return 1
    done < "$inf"
}

########
aggregate_document()
{
    process_description "Aggregates worker results."
}

########
aggregate_explain_cmdline_opts()
{
    # -w option
    local description="Number of workers."
    explain_cmdline_req_opt "-w" "<int>" "$description"
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
        define_opt_from_proc_task_out "-ind$i" "worker" "${i}" "-outd" optlist || return 1
    done

    # Define name of output file
    local outf="${process_outdir}/result.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
aggregate()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    local w=$(read_opt_value_from_func_args "-w" "$@")
    local dirs=()
    for ((i=0; i<w; i++)); do
        dirs+=($(read_opt_value_from_func_args "-ind$i" "$@"))
    done

    # Clear/create the output file
    > "$outf"

    # Collect all available indices i from all directories
    local indices=()
    local d f base i
    for d in "${dirs[@]}"; do
        for f in "$d"/blk*.txt; do
            [ -e "$f" ] || continue
            base=$(basename "$f")
            i="${base#blk}"
            i="${i%.txt}"
            indices+=("$i")
        done
    done

    # Sort indices numerically
    local sorted_indices
    sorted_indices=$(printf '%s\n' "${indices[@]}" | sort -n -u)

    # For each index, search through the directories to find the block
    for i in $sorted_indices; do
        local found=0
        for d in "${dirs[@]}"; do
            local blockfile="$d/blk${i}.txt"
            if [ -e "$blockfile" ]; then
                cat "$blockfile" >> "$outf" || return 1
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            echo "Warning: block $i not found in any directory" >&2
        fi
    done
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_dynamic_fanout_fifos_program()
{
    add_debasher_process "generate"  "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fragment"  "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "dispatch"  "cpus=1 mem=32 time=00:01:00" "ext_alias=./dynamic_fanout_dispatcher.py"
    add_debasher_process "worker"    "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "aggregate" "cpus=1 mem=32 time=00:01:00"
}
