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

    head -c "$bytes_needed" /dev/urandom | base64 | tr -d '\n' | \
        fold -w "$numchars" | head -n "$numlines" > "$outf"
}