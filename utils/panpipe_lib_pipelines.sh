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
    local process_dependencies=$3

    # Print process pipeline line
    echo "${processname}" "${process_computational_specs}" "${process_dependencies}"
}

########
apply_suffix_to_pipeline_entry()
{
    local ppl_entry=$1
    local suffix=$2

    echo "${ppl_entry}" | "${AWK}" -v sep="${PROCESSNAME_SUFFIX_SEP}" -v suffix="${suffix}" -v procdeps_spec="${PROCESSDEPS_SPEC}" \
                                       'function is_prefix(string1, string2)
                                        {
                                         return substr(string2, 1, length(string1)) == string1
                                        }
                                        function add_suffix_to_deps(deps)
                                        {
                                         return deps
                                        }
                                        {
                                         if(suffix == "") print $0
                                         else
                                         {
                                          # Add suffix to process name
                                          $1=$1 sep suffix
                                          # Search for dependencies and process them
                                          for(i=2; i<=NF; ++i)
                                           if(is_prefix(procdeps_spec"=", $i))
                                            $i = add_suffix_to_deps($i)
                                          # print result
                                          print $0
                                         }
                                        }'
}

########
apply_sufix_to_pipeline_entries()
{
    local suffix=$1

    while read line; do
        apply_suffix_to_pipeline_entry "${line}" "${suffix}"
    done
}

########
add_panpipe_pipeline()
{
    # Initialize variables
    local modname=$1
    local suffix=$2

    # Load module
    load_pipeline_module "${modname}"

    # Execute pipeline function for module
    exec_pipeline_func_for_module "${modname}" | apply_sufix_to_pipeline_entries "${suffix}" ; pipe_fail || return 1
}
