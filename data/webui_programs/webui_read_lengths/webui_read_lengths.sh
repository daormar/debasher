# AUTOMATICALLY GENERATED DEBASHER SCRIPT


webui_read_lengths_document()
{
    debasher::document_module "Example built with the web UI: a general program that summarizes the lengths of the reads of one file of a sequencing run (POD5, FAST5, or a text file with one length per line); webui_readfish runs it once for each file that the sequencer writes."
}


webui_read_lengths_shared_dirs()
{
    :
}


read_lengths_document()
{
    debasher::document_process "Writes a JSON summary of the lengths of the reads of -infile: count, median, N50 and the fraction of reads shorter than -short-bases, which says whether adaptive sampling was at work when the file was written."
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


webui_read_lengths_program()
{
    add_debasher_process "read_lengths" "cpus=1 mem=512 time=01:00:00" "ext_alias=read_lengths.py"
}
