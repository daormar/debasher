python_version()
{
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # conda_activate loads the shell functions of conda first, if the
    # shell that runs the process does not have them
    conda_activate py27 || return 1
    python --version > "${outf}" 2>&1 || return 1
    conda deactivate
}
