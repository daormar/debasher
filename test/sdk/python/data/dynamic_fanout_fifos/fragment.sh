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

    # Open the output FIFO once, for the whole process
    exec 3> "$outf"

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

        echo "$blockfile" >&3   # announce this block as soon as it's ready
    done

    exec 3>&-
}