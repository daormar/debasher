# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_batch_greet_document()
{
    debasher::document_module "Example built with the web UI: a general program that waits for some seconds and writes a greeting; webui_batch_launcher runs it once for each request."
}


webui_batch_greet_shared_dirs()
{
    :
}


greet_document()
{
    debasher::document_process "Waits for some seconds and writes a greeting into a file."
}


greet_explain_opts()
{
    debasher::explain_opt "-text" "<string>" "whom to greet; the text fail makes the program fail"
    debasher::explain_opt "-secs" "<int>" "how many seconds to wait before greeting"
    debasher::explain_opt "-outf" "<file>" "file with the greeting"
}


greet_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-text"
    debasher::opt_is_cmdline "-secs"
}


greet_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-text" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-secs" optlist || return 1
    debasher::define_opt "-outf" "${process_outdir}/greeting.txt" optlist || return 1

    save_opt_list optlist
}


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


webui_batch_greet_program()
{
    add_debasher_process "greet" "cpus=1 mem=256 time=01:00:00" ""
}
