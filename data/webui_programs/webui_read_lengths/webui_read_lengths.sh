# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_read_lengths_document()
{
    debasher::document_module "Example built with the web UI: a general program that summarizes the lengths of the reads of one file of a sequencing run (POD5, FAST5, or a text file with one length per line), in the conda environment read_lengths, which a run with conda support creates; webui_readfish runs it once for each file that the sequencer writes."
}


webui_read_lengths_shared_dirs()
{
    :
}


read_lengths_document()
{
    debasher::document_process "Activates the conda environment read_lengths and runs read_lengths.py, which writes a JSON summary of the lengths of the reads of -infile: count, median, N50 and the fraction of reads shorter than -short-bases, which says whether adaptive sampling was at work when the file was written."
}


read_lengths_explain_opts()
{
    debasher::explain_opt "-infile" "<string>" "the file of reads, given by the request of the launcher"
    debasher::explain_opt "-samples-per-base" "<string>" "signal samples per base for POD5 and FAST5 (10 by default)"
    debasher::explain_opt "-short-bases" "<string>" "a read under this many bases is short (1000 by default)"
    debasher::explain_opt "-outsummary" "<file>" "the JSON summary"
}


read_lengths_identify_cmdline_opts()
{
    debasher::opt_is_cmdline "-infile"
    debasher::opt_is_non_mandatory_cmdline "-samples-per-base"
    debasher::opt_is_non_mandatory_cmdline "-short-bases"
}


read_lengths_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    debasher::define_cmdline_opt "${cmdline}" "-infile" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-samples-per-base" optlist || return 1
    debasher::define_cmdline_opt_if_given "${cmdline}" "-short-bases" optlist || return 1
    debasher::define_opt "-outsummary" "${process_outdir}/summary.json" optlist || return 1

    save_opt_list optlist
}


read_lengths()
{
    local infile=$(read_opt_value_from_func_args "-infile" "$@")
    local samples_per_base=$(read_opt_value_from_func_args "-samples-per-base" "$@")
    local short_bases=$(read_opt_value_from_func_args "-short-bases" "$@")
    local outsummary=$(read_opt_value_from_func_args "-outsummary" "$@")

    # The readers of POD5 and FAST5 files live in the conda environment
    # read_lengths, which a run with conda support creates; conda_activate
    # loads the shell functions of conda first, if the shell that runs the
    # process does not have them
    conda_activate read_lengths || return 1
    # The script next to the module does the work, with the options that
    # were given; one left out reads as DEBASHER_OPT_NOT_FOUND
    local args=(-infile "${infile}" -outsummary "${outsummary}")
    if [ "${samples_per_base}" != "${DEBASHER_OPT_NOT_FOUND}" ]; then
        args+=(-samples-per-base "${samples_per_base}")
    fi
    if [ "${short_bases}" != "${DEBASHER_OPT_NOT_FOUND}" ]; then
        args+=(-short-bases "${short_bases}")
    fi
    python "${DEBASHER_PROCESS_MODULE_DIR}/read_lengths.py" "${args[@]}" || return 1
    conda deactivate
}


read_lengths_conda_envs()
{
    define_conda_env read_lengths read_lengths.yml
}


webui_read_lengths_program()
{
    add_debasher_process "read_lengths" "cpus=1 mem=512 time=01:00:00" ""
}
