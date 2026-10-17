numbers()
{
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local outnums=$(read_opt_value_from_func_args "-outnums" "$@")

    seq 1 "${n}" > "${outnums}"
}
