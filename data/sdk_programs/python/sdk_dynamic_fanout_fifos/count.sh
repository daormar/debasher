########
count_chars() {
    local inf="$1"

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
    ' "$inf"
}

########
count()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Extract counts
    count_chars "${inf}" | sort > "${outf}"
}
