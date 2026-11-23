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
