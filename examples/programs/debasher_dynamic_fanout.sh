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
debasher_dynamic_fanout_shared_dirs()
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
count_chars() {
    local inf="$1"
    local outf="$2"

    awk '
        {
            n = length($0)
            for (i = 1; i <= n; i++) {
                c = substr($0, i, 1)
                count[c]++
            }
        }
        END {
            for (c in count) print c","count[c]
        }
    ' "$inf" > "$outf"
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

    local bytes_needed=$(( (numchars * numlines * 3 / 4) + numlines * 4 + 64 ))

    # Generate file
    head -c "$bytes_needed" /dev/urandom | base64 | tr -d '\n' | \
        fold -w "$numchars" | head -n "$numlines" > "$outf"

    # Extract counts for program testing
    count_chars "${outf}" "${outf}.counts"
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

    # Save option list
    save_opt_list optlist
}

########
fragment()
{
    # Initialize variables
    local numblocks=$(read_opt_value_from_func_args "-b" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    # Count the total number of lines in the input file
    local total_lines
    total_lines=$(wc -l < "$inf")

    # Calculate how many lines correspond to each block (rounded up)
    local lines_per_block=$(( (total_lines + numblocks - 1) / numblocks ))

    # Fragment file
    local i start_line end_line count blockfile
    for ((i = 0; i < numblocks; i++)); do
        start_line=$(( i * lines_per_block + 1 ))
        [ "$start_line" -gt "$total_lines" ] && break   # no more lines left

        end_line=$(( start_line + lines_per_block - 1 ))
        [ "$end_line" -gt "$total_lines" ] && end_line="$total_lines"
        count=$(( end_line - start_line + 1 ))

        blockfile="$outd/blk${i}.txt"

        # Extract lines [start_line, end_line] using tail + head,
        # instead of reading and writing line by line in bash.
        tail -n "+$start_line" "$inf" | head -n "$count" > "$blockfile"
    done
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

    # -ind option
    define_opt_from_proc_out "-ind" "fragment" "-outd" optlist || return 1

    # Add output option for w files
    local w
    w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
    for ((i=0; i<w; i++)); do
        define_opt "-outf$i" "${process_outdir}/block_list_${i}.txt" optlist || return 1
    done

    # Save option list
    save_opt_list optlist
}

########
dispatch()
{
    # Initialize variables
    local ind=$(read_opt_value_from_func_args "-ind" "$@")
    local w=$(read_opt_value_from_func_args "-w" "$@")
    local files=()
    for ((i=0; i<w; i++)); do
        files+=($(read_opt_value_from_func_args "-outf$i" "$@"))
    done

    # Clear the destination files before starting
    for f in "${files[@]}"; do
        > "$f"
    done

    # Iterate over the blk*.txt files in the input directory
    for blockfile in "$ind"/blk*.txt; do
        [ -e "$blockfile" ] || continue

        local base
        base=$(basename "$blockfile")

        # Extract the number i from "blk${i}.txt"
        local i="${base#blk}"
        i="${i%.txt}"

        # Calculate i mod w
        local idx=$(( i % w ))

        # Write the block file name to the corresponding output file
        echo "$blockfile" >> "${files[$idx]}" || return 1
    done
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

    count_chars "${inf}" "${outf}"
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

        # Execute worker task
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
merge_counts() {
    local outf="$1"
    shift
    local count_files=("$@")

    awk -F',' '
        {
            total[$1] += $2
        }
        END {
            for (c in total) print c","total[c]
        }
    ' "${count_files[@]}" > "$outf"
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

    # Collect all count files (blk${i}.txt.counts, or whatever naming
    # convention the workers used) across all directories. Order doesn't
    # matter here since aggregation is a sum, not a concatenation.
    local count_files=()
    local d f
    for d in "${dirs[@]}"; do
        for f in "$d"/blk*.txt; do
            [ -e "$f" ] || continue
            count_files+=("$f")
        done
    done

    if [ "${#count_files[@]}" -eq 0 ]; then
        echo "Warning: no count files found in any directory" >&2
        return 1
    fi

    merge_counts "$outf" "${count_files[@]}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_dynamic_fanout_program()
{
    add_debasher_process "generate"  "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fragment"  "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "dispatch"  "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "worker"    "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "aggregate" "cpus=1 mem=32 time=00:01:00"
}
