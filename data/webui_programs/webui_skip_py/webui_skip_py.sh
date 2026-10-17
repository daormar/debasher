# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_skip_py_document()
{
    debasher::document_module "Example built with the web UI: a process sums two numbers into a value descriptor, and another writes the sum plus one, skipped by a rule in Python when the sum is odd."
}


webui_skip_py_shared_dirs()
{
    :
}


value_writer_document()
{
    debasher::document_process "Takes two numbers and produces their sum as output."
}


value_writer_explain_opts()
{
    debasher::explain_opt "-num-a" "<int>" "First number to be summed"
    debasher::explain_opt "-num-b" "<int>" "Second number to be summed"
    debasher::explain_opt "-outv" "<int>" "output value descriptor"
}


value_writer_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-num-a"
    debasher::opt_is_cmdline "-num-b"
}


value_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-num-a" optlist || return 1
    debasher::define_cmdline_opt "${cmdline}" "-num-b" optlist || return 1
    debasher::define_value_desc_opt "-outv" optlist || return 1

    save_opt_list optlist
}


value_writer()
{
    local num_a=$(read_opt_value_from_func_args "-num-a" "$@")
    local num_b=$(read_opt_value_from_func_args "-num-b" "$@")
    local outv=$(read_opt_value_from_func_args "-outv" "$@")

    write_value_to_desc "$((num_a + num_b))" "${outv}"
}


value_reader_document()
{
    debasher::document_process "Reads the sum, increases it by one and writes it into a file; skipped when the sum is odd."
}


value_reader_explain_opts()
{
    debasher::explain_opt "-val-desc" "<int>" "value descriptor"
    debasher::explain_opt "-outf" "<file>" "output file"
}


value_reader_identify_cmdline_opts()
{
    :
}


value_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt_from_proc_out "-val-desc" "value_writer" "-outv" optlist || return 1
    debasher::define_opt "-outf" "${process_outdir}/value_reader.out" optlist || return 1

    save_opt_list optlist
}


value_reader()
{
    local value=$(read_opt_value_from_func_args "-val-desc" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    echo "$((value + 1))" > "${outf}"
}


value_reader_skip()
{
    debasher::skip_from_file "value_reader" "value_reader_skip.py" "$@"
}


webui_skip_py_program()
{
    add_debasher_process "value_writer" "cpus=1 mem=32 time=00:01:00" ""
    add_debasher_process "value_reader" "cpus=1 mem=32 time=00:01:00" ""
}
