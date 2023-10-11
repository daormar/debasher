##############################
# PIPELINE-RELATED FUNCTIONS #
##############################

########
get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 ${command_line_file} | "$AWK" '{print $2}'` ; pipe_fail || return 1
    echo $workdir
}

########
get_orig_outdir_from_command_line_file()
{
    # initialize variables
    local command_line_file=$1

    # Extract information from command line file
    local workdir
    workdir=`get_orig_workdir "${command_line_file}"` || return 1
    local cmdline
    cmdline=`get_cmdline_from_command_line_file "${command_line_file}"` || return 1
    local outdir=`read_opt_value_from_line "$cmdline" "--outdir"`

    # Retrieve original output directory
    if is_absolute_path "$outdir"; then
        echo "$outdir"
    else
        echo "${workdir}/${outdir}"
    fi
}

########
get_cmdline_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`"$TAIL" -1 "${command_line_file}"`
    sargsquotes_to_sargs "$cmdline"
}

########
get_pfile_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`get_cmdline_from_command_line_file "${command_line_file}"`
    local pfile=`read_opt_value_from_line "$cmdline" "--pfile"` || return 1
    echo "${pfile}"
}

########
get_currdir_from_command_line_file()
{
    local command_line_file=$1
    local currdir=`"${HEAD}" -1 "${command_line_file}" | "${AWK}" '{print $2}'`
    echo "${currdir}"
}

########
get_sched_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`get_cmdline_from_command_line_file "${command_line_file}"`
    local sched=`read_opt_value_from_line "${cmdline}" "--sched"` || return 1
    echo "${sched}"
}

########
replace_outdir_in_cmdline()
{
    local cmdline=$1
    local newdir=$2

    echo "$cmdline" | "$AWK" -v newdir="$newdir" 'BEGIN{
                                replace=0
                               }
                               {
                                for(i=1;i<=NF;++i)
                                {
                                 if(replace==0)
                                 {
                                  printf"%s",$i
                                 }
                                 else
                                 {
                                  printf"%s",newdir
                                  replace=0
                                 }
                                 if($i=="--outdir") replace=1
                                 if(i!=NF) printf" "
                                }
                               }'
}

########
get_abspfile_from_command_line_file()
{
    # Initialize variables
    local command_line_file=$1

    # Obtain pipeline file and current dir
    local cmdline_pfile
    cmdline_pfile=`get_pfile_from_command_line_file "${command_line_file}"` || return 1
    local cmdline_currdir
    cmdline_currdir=`get_currdir_from_command_line_file "${command_line_file}"` || return 1

    # Obtain absolute pipeline file name
    local abspfile
    pushd "${cmdline_currdir}" > /dev/null
    abspfile=`get_absolute_path "${cmdline_pfile}"`
    popd > /dev/null

    # Check if resulting pipeline file exists
    if [ -f "${abspfile}" ]; then
        echo "${abspfile}"
        return 0
    else
        echo "Error: unable to find pipeline file (${abspfile})" >&2
        return 1
    fi
}

########
exec_pipeline_func_for_module()
{
    local pfile=$1

    local pipeline_funcname
    pipeline_funcname=`get_pipeline_funcname "${pfile}"`

    ${pipeline_funcname}
}

########
get_ppl_scripts_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${PANPIPE_SCRIPTS_DIRNAME}"
}

########
get_ppl_scripts_dir()
{
    get_ppl_scripts_dir_given_basedir "${PIPELINE_OUTDIR}"
}

########
add_panpipe_process()
{
    # Initialize variables
    local processname=$1
    local process_computational_specs=$2
    local process_additional_specs=$3

    # Print process pipeline line
    echo "${processname}" "${process_computational_specs}" "${process_additional_specs}"
}

########
apply_suffix_to_processdeps()
{
    local processdeps=$1
    local suffix=$2

    # Obtain process dependencies separated by blanks
    local separator=`get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    # Process dependencies
    local dep
    local result=""
    for dep in ${processdeps_blanks}; do
        # Extract dependency components
        local processname=`get_processname_part_in_dep ${dep}`
        local deptype=`get_deptype_part_in_dep ${dep}`
        # Obtain modified dependency
        if [ "${deptype}" = "${NONE_PROCESSDEP_TYPE}" ]; then
            local modified_dep="${deptype}"
        else
            local processname_with_suff=`get_processname_given_suffix "${processname}" "${suffix}"`
            local modified_dep="${deptype}${PROCESS_PLUS_DEPTYPE_SEP}${processname_with_suff}"
        fi
        # Add modified dependency to result
        if [ -z "${result}" ]; then
            result="${modified_dep}"
        else
            result="${result}${separator}${modified_dep}"
        fi
    done

    echo "${result}"
}

########
apply_suffix_to_pipeline_entry()
{
    local ppl_entry=$1
    local suffix=$2

    # Read the string into an array using the IFS
    local elements
    IFS=" " read -ra elements <<< "$ppl_entry"

    # Initialize a variable to store the concatenated elements
    local result=""

    # Iterate over the indices of the elements array
    for i in "${!elements[@]}"; do
        # The first word is the process name
        if [ "${i}" -eq 0 ]; then
            # Add process with suffix to result
            local processname="${elements[$i]}"
            local processname_with_suff=`get_processname_given_suffix "${processname}" "${suffix}"`
            result="${processname_with_suff}"
        else
            if [[ "${elements[$i]}" == "${PROCESSDEPS_SPEC}"* ]]; then
                processdeps=`extract_processdeps_from_process_spec "${elements[$i]}"`
                processdeps_with_suffix=`apply_suffix_to_processdeps "${processdeps}" "${suffix}"`
                result="${result} ${PROCESSDEPS_SPEC}=${processdeps_with_suffix}"
            else
                result="${result} ${elements[$i]}"
            fi
        fi
    done

    # Print the concatenated result
    echo "$result"
}

########
exec_additional_actions_for_ppl_entry()
{
    local ppl_entry=$1
    local suffix=$2

    # Read the string into an array using the IFS
    local elements
    IFS=" " read -ra elements <<< "$ppl_entry"

    # Get process name from entry
    local processname="${elements[0]}"

    # Copy processname_def_opts function if necessary
    copy_process_defopts_func "${processname}" "${suffix}"
}

########
add_panpipe_pipeline()
{
    # Initialize variables
    local modname=$1
    local suffix=$2

    # Create temporary file
    local tmpfile=`${MKTEMP}`

    # Load module
    load_panpipe_module "${modname}"

    # Execute pipeline function for module and store output entries in a
    # temporary file (the purpose is to enable function execution
    # without using any sub-shell)
    exec_pipeline_func_for_module "${modname}" > "${tmpfile}"

    # Process resulting pipeline entries
    while read ppl_entry; do
        apply_suffix_to_pipeline_entry "${ppl_entry}" "${suffix}" || return 1
        exec_additional_actions_for_ppl_entry "${ppl_entry}" "${suffix}" || return 1
    done < "${tmpfile}"

    # Remove temporary file
    rm "${tmpfile}"
}
