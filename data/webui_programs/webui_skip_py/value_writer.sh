value_writer()
{
    local num_a=$(read_opt_value_from_func_args "-num-a" "$@")
    local num_b=$(read_opt_value_from_func_args "-num-b" "$@")
    local outv=$(read_opt_value_from_func_args "-outv" "$@")

    write_value_to_desc "$((num_a + num_b))" "${outv}"
}
