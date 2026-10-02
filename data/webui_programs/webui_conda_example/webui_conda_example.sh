# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_conda_example_document()
{
    debasher::document_module "Example built with the web UI: a general program whose process activates the conda environment py27, which a run with conda support creates from py27.yml, and writes the version of its Python into a file."
}


webui_conda_example_shared_dirs()
{
    :
}


python_version_document()
{
    debasher::document_process "Activates the conda environment py27 and writes the version of its Python into a file."
}


python_version_explain_opts()
{
    debasher::explain_opt "-outf" "<file>" "file with the version of the Python of py27"
}


python_version_identify_cmdline_opts()
{
    :
}


python_version_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_opt "-outf" "${process_outdir}/python_version.txt" optlist || return 1

    save_opt_list optlist
}


python_version()
{
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # conda_activate loads the shell functions of conda first, if the
    # shell that runs the process does not have them
    conda_activate py27 || return 1
    python --version > "${outf}" 2>&1 || return 1
    conda deactivate
}


python_version_conda_envs()
{
    define_conda_env py27 py27.yml
}


webui_conda_example_program()
{
    add_debasher_process "python_version" "cpus=1 mem=256 time=01:00:00" ""
}
