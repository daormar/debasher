# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_fifo_sum_document()
{
    debasher::document_module "Example built with the web UI: a process writes the numbers from 1 to n into a fifo, and another adds them up."
}


webui_fifo_sum_shared_dirs()
{
    :
}


numbers_document()
{
    debasher::document_process "Writes the numbers from 1 to n into a fifo, one per line."
}


numbers_explain_opts()
{
    debasher::explain_opt "-n" "<int>" "how many numbers to write"
    debasher::explain_opt "-outnums" "<string>" "fifo with one number per line"
}


numbers_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-n"
}


numbers_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-n" optlist || return 1
    debasher::define_fifo_opt "-outnums" "numbers" optlist || return 1

    save_opt_list optlist
}


numbers()
{
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local outnums=$(read_opt_value_from_func_args "-outnums" "$@")

    seq 1 "${n}" > "${outnums}"
}


sum_document()
{
    debasher::document_process "Adds the numbers it reads from a fifo and writes the result into a file."
}


sum_explain_opts()
{
    debasher::explain_opt "-nums" "<string>" "fifo with the numbers to add"
    debasher::explain_opt "-outf" "<file>" "file with the sum"
}


sum_identify_cmdline_opts()
{
    :
}


sum_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-nums" "numbers" "-outnums" optlist || return 1
    debasher::define_opt "-outf" "${process_outdir}/sum.txt" optlist || return 1

    save_opt_list optlist
}


sum()
{
    local nums=$(read_opt_value_from_func_args "-nums" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    awk '{ total += $1 } END { print total }' "${nums}" > "${outf}"
}


webui_fifo_sum_program()
{
    add_debasher_process "numbers" "cpus=1 mem=256 time=01:00:00" ""
    add_debasher_process "sum" "cpus=1 mem=256 time=01:00:00" ""
}
