# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_hello_world_document()
{
    :
}


webui_hello_world_shared_dirs()
{
    :
}


hello_world_document()
{
    debasher::document_process "Prints a greeting."
}


hello_world_explain_opts()
{
    debasher::explain_opt "-s" "<string>" "string to print ('Hello World!' by default)"
}


hello_world_identify_cmdline_opts()
{
    debasher::opt_is_non_mandatory_cmdline "-s"
}


hello_world_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt_if_given "${cmdline}" "-s" optlist || return 1

    save_opt_list optlist
}


hello_world()
{
    local s=$(read_opt_value_from_func_args "-s" "$@")
    if [ "${s}" = "${DEBASHER_OPT_NOT_FOUND}" ]; then
        s="Hello World!"
    fi

    echo "${s}"
}



webui_hello_world_program()
{
    add_debasher_process "hello_world" "cpus=1 mem=256 time=01:00:00" ""
}
