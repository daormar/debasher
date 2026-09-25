# *- bash -*
# General program that the launcher reference program launches once for each
# request (see debasher_launcher_ref.sh): step waits -secs seconds and writes
# -text to a file of its output directory.

debasher_launcher_batch_shared_dirs()
{
    :
}

########
step_document()
{
    document_process "Waits a while and writes a text to a file."
}

step_explain_opts()
{
    explain_opt "-text" "<string>" "text to write"
    explain_opt "-secs" "<int>" "seconds to wait before writing it"
    explain_opt "-outf" "<file>" "file the text is written to"
}

step_identify_cmdline_opts()
{
    opt_is_cmdline "-text"
    opt_is_cmdline "-secs"
}

step_define_opts()
{
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""
    define_cmdline_opt "$cmdline" "-text" optlist || return 1
    define_cmdline_opt "$cmdline" "-secs" optlist || return 1
    define_opt "-outf" "${process_outdir}/result.txt" optlist || return 1
    save_opt_list optlist
}

step()
{
    local text=$(read_opt_value_from_func_args "-text" "$@")
    local secs=$(read_opt_value_from_func_args "-secs" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    sleep "${secs}"
    echo "${text}" > "${outf}"
}

########
debasher_launcher_batch_program()
{
    add_debasher_process "step" "cpus=1 mem=32 time=00:10:00"
}
