hello_world()
{
    local s=$(read_opt_value_from_func_args "-s" "$@")
    if [ "${s}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
        s="Hello World!"
    fi

    echo "${s}"
}
