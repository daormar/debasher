sum()
{
    local nums=$(read_opt_value_from_func_args "-nums" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    awk '{ total += $1 } END { print total }' "${nums}" > "${outf}"
}
