# *- bash -*
# Module with the process that the watcher reference program launches, alone,
# for each file that arrives (see debasher_watch_ref.sh): count_lines writes
# how many lines a file has.

debasher_watch_batch_shared_dirs()
{
    :
}

########
count_lines_document()
{
    document_process "Writes how many lines a file has."
}

count_lines_explain_opts()
{
    explain_opt "-infile" "<file>" "file whose lines are counted"
    explain_opt "-outf" "<file>" "file the count is written to"
}

count_lines_identify_cmdline_opts()
{
    opt_is_cmdline "-infile"
    opt_is_cmdline "-outf"
}

count_lines_define_opts()
{
    local cmdline=$1
    local optlist=""
    define_cmdline_opt "$cmdline" "-infile" optlist || return 1
    define_cmdline_opt "$cmdline" "-outf" optlist || return 1
    save_opt_list optlist
}

count_lines()
{
    local infile=$(read_opt_value_from_func_args "-infile" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    wc -l < "${infile}" > "${outf}"
}

########
debasher_watch_batch_program()
{
    add_debasher_process "count_lines" "cpus=1 mem=32 time=00:10:00"
}
