value_reader()
{
    local value=$(read_opt_value_from_func_args "-val-desc" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    echo "$((value + 1))" > "${outf}"
}
