########
merge_counts() {
    local count_files=("$@")

    awk -F',' '
        {
            total[$1] += $2
        }
        END {
            for (c in total) print c","total[c]
        }
    ' "${count_files[@]}"
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

    merge_counts "${count_files[@]}" | sort > "$outf"
}