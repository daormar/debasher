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
worker_task()
{
    local inf=$1
    local outf=$2

    count_chars "${inf}" > "${outf}"
}

########
worker()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

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