greet()
{
    local text=$(read_opt_value_from_func_args "-text" "$@")
    local secs=$(read_opt_value_from_func_args "-secs" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # The text "fail" makes the program fail, to show a batch run that
    # failed.
    if [ "${text}" = "fail" ]; then
        echo "Error: asked to fail" >&2
        return 1
    fi

    sleep "${secs}"
    echo "Hello, ${text}!" > "${outf}"
}
