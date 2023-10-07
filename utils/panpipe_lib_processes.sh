#############################
# PROCESS-RELATED FUNCTIONS #
#############################

########
get_document_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_DOCUMENT}"
}

########
process_description()
{
    local desc=$1
    echo $desc
}

########
document_process_opts()
{
    local opts=$1
    for opt in ${opts}; do
        if [ "${PIPELINE_OPT_REQ[${opt}]}" != "" ]; then
            reqflag=" (required) "
        else
            reqflag=" "
        fi

        # Print option
        if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
            echo "\`${opt}\` ${PIPELINE_OPT_DESC[$opt]}${reqflag}"
        else
            echo "\`${opt}\` ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}${reqflag}"
        fi
        echo ""
    done
}

########
document_process()
{
    local processname=$1
    local doc_options=$2

    # Print header
    echo "# ${processname}"
    echo ""

    # Print body
    echo "## Description"
    local document_funcname=`get_document_funcname ${processname}`
    ${document_funcname}
    echo ""

    if [ ${doc_options} -eq 1 ]; then
        echo "## Options"
        DIFFERENTIAL_CMDLINE_OPT_STR=""
        local explain_cmdline_opts_funcname=`get_explain_cmdline_opts_funcname ${processname}`
        ${explain_cmdline_opts_funcname}
        document_process_opts "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    fi
}

########
pipeline_process_spec_is_comment()
{
    local process_spec=$1

    local fields=( $process_spec )
    if [[ "${fields[0]}" = \#* ]]; then
        echo "yes"
    else
        echo "no"
    fi
}

########
pipeline_process_spec_is_ok()
{
    local process_spec=$1

    local fieldno=1
    local field
    for field in $process_spec; do
        if [[ ${field} = "${PROCESSDEPS_SPEC}="* ]]; then
            if [ $fieldno -ge 2 ]; then
                echo "yes"
                return 0
            fi
        fi
        fieldno=$((fieldno + 1))
    done

    echo "no"
}

########
extract_attr_from_process_spec()
{
    local process_spec=$1
    local attrname=$2

    local field
    for field in $process_spec; do
        if [[ "${field}" = "${attrname}="* ]]; then
            local attrname_len=${#attrname}
            local start=$((attrname_len + 1))
            local attr_val=${field:${start}}
            echo ${attr_val}
            return 0
        fi
    done

    echo ${ATTR_NOT_FOUND}
}

########
extract_processname_from_process_spec()
{
    local process_spec=$1
    local fields=( $process_spec )
    echo ${fields[0]}
}

########
extract_processdeps_from_process_spec()
{
    local process_spec=$1
    extract_attr_from_process_spec "${process_spec}" "${PROCESSDEPS_SPEC}"
}

########
extract_cpus_from_process_spec()
{
    local process_spec=$1
    extract_attr_from_process_spec "${process_spec}" "cpus"
}

########
extract_mem_from_process_spec()
{
    local process_spec=$1
    extract_attr_from_process_spec "${process_spec}" "mem"
}

########
get_task_template_log_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_%a.${SLURM_SCHED_LOG_FEXT}"
}

########
get_name_of_process_function_reset()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_RESET_OUTDIR}"
}

########
get_name_of_process_function()
{
    local processname=$1

    search_process_mandatory_func "${processname}" "${PROCESS_METHOD_NAME_EXEC}"
}

########
get_name_of_process_function_post()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_POST}"
}

########
get_name_of_process_function_outdir()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_OUTDIR}"
}

########
get_explain_cmdline_opts_funcname()
{
    local processname=$1

    search_process_mandatory_func "${processname}" "${PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"
}

########
get_define_opts_funcname()
{
    local processname=$1

    search_process_mandatory_func "${processname}" "${PROCESS_METHOD_NAME_DEFINE_OPTS}"
}

########
get_should_execute_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_SHOULD_EXECUTE}"
}

########
get_conda_envs_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_CONDA_ENVS}"
}

########
process_is_defined()
{
    local processname=$1
    local funcname=`get_define_opts_funcname "${processname}"`

    if func_exists "${funcname}"; then
        return 0
    else
        return 1
    fi
}

########
define_opts_for_process()
{
    clear_def_opts_vars()
    {
        clear_curr_opt_list_array
        clear_pipeline_shdirs_def_opts_array
        clear_pipeline_fifos_def_opts_array
    }

    store_opt_list_in_assoc_array()
    {
        local processname=$1
        local array_length=${#CURRENT_PROCESS_OPT_LIST[@]}
        PROCESS_OPT_LIST["${processname}${ASSOC_ARRAY_KEY_SEP}${ASSOC_ARRAY_KEY_LEN}"]=${array_length}
        for task_idx in "${!CURRENT_PROCESS_OPT_LIST[@]}"; do
            PROCESS_OPT_LIST["${processname}${ASSOC_ARRAY_KEY_SEP}${task_idx}"]=${CURRENT_PROCESS_OPT_LIST[task_idx]}
        done
    }

    get_output_params_info()
    {
        local processname=$1
        for task_idx in "${!CURRENT_PROCESS_OPT_LIST[@]}"; do
            deserialize_args ${CURRENT_PROCESS_OPT_LIST[task_idx]}
            local i=0
            while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
                # Check if option was found
                if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
                    local opt="${DESERIALIZED_ARGS[$i]}"
                    i=$((i+1))
                    # Obtain value if it exists
                    local value=""
                    # Check if next token is an option
                    if [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; then
                        if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
                            :
                        else
                            value="${DESERIALIZED_ARGS[$i]}"
                            if is_absolute_path "${value}" && str_is_output_option "${opt}"; then
                                PROCESS_OUT_VALUES["$value"]="${processname}${ASSOC_ARRAY_KEY_SEP}${task_idx}" >&2
                            fi
                            i=$((i+1))
                        fi
                    fi
                else
                    echo "Warning: unexpected value (${DESERIALIZED_ARGS[$i]}), skipping..." >&2
                    i=$((i+1))
                fi
            done
        done
    }

    local cmdline=$1
    local process_spec=$2
    local processname=`extract_processname_from_process_spec "${process_spec}"`
    local process_outdir=`get_process_outdir "${processname}"`

    # Clear variables
    clear_def_opts_vars

    # Obtain define_opts function name and call it
    local define_opts_funcname=`get_define_opts_funcname ${processname}`
    ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1

    # Update variables storing option information
    store_opt_list_in_assoc_array "${processname}"
    get_output_params_info "${processname}"
}

########
get_processdeps_separator()
{
    local processdeps=$1
    if [[ "${processdeps}" == *"${PROCESSDEPS_SEP_COMMA}"* ]]; then
        echo "${PROCESSDEPS_SEP_COMMA}"
    else
        if [[ "${processdeps}" == *"${PROCESSDEPS_SEP_INTERR}"* ]]; then
            echo "${PROCESSDEPS_SEP_INTERR}"
        else
            echo ""
        fi
    fi
}

########
find_dependency_for_process()
{
    local process_spec=$1
    local processname_part=$2

    # Obtain process dependencies separated by blanks
    local processdeps=`extract_processdeps_from_process_spec "$process_spec"`
    local separator=`get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    # Process dependencies
    local dep
    for dep in ${processdeps_blanks}; do
        local processname_part_in_dep=`get_processname_part_in_dep ${dep}`
        if [ "${processname_part_in_dep}" = ${processname_part} ]; then
            echo ${dep}
            return 0
        fi
    done
    echo ${DEP_NOT_FOUND}
    return 1
}

########
get_ppl_scripts_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base scripts dir
    scriptsdir=`get_ppl_scripts_dir_given_basedir "${dirname}"`

    echo "${scriptsdir}"
}

########
get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd="${PIPELINE_OUTDIR}"

        # Get processname
        local processname_part=`echo ${dep} | "$AWK" -F ":" '{print $2}'`

        get_process_outdir_given_dirname "${outd}" ${processname_part}
    fi
}

########
get_outd_for_dep_given_process_spec()
{
    local process_spec=$1
    local depname=$2

    local dep=`find_dependency_for_process "${process_spec}" $depname`
    if [ ${dep} = ${DEP_NOT_FOUND} ]; then
        return 1
    else
        local outd=`get_outd_for_dep "${dep}"`
        echo "${outd}"
        return 0
    fi
}

########
get_task_array_size_for_process()
{
    local cmdline=$1
    local process_spec=$2

    define_opts_for_process "${cmdline}" "${process_spec}" || return 1
    echo ${#SCRIPT_OPT_LIST_ARRAY[@]}
}

########
get_deptype_part_in_dep()
{
    local dep=$1
    local sep=":"
    local str_array
    IFS="$sep" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
get_processname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "${NONE_PROCESSDEP_TYPE}" ]; then
        echo ${dep}
    else
        local sep=":"
        local str_array
        IFS="$sep" read -r -a str_array <<< "${dep}"
        echo ${str_array[1]}
    fi
}

########
get_id_part_in_dep()
{
    local dep=$1
    local sep=":"
    local str_array
    IFS="$sep" read -r -a str_array <<< "${dep}"
    echo ${str_array[1]}
}

########
task_array_elem_is_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        return 0
    else
        return 1
    fi
}

########
get_start_idx_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[0]}
    else
        echo "-1"
    fi
}

########
get_end_idx_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[1]}
    else
        echo "-1"
    fi
}

########
get_default_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2
    echo "${dirname}/${processname}"
}

########
get_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2

    # Get name of process function to set output directory
    process_function_outdir=`get_name_of_process_function_outdir ${processname}`

    if [ "${process_function_outdir}" = "${FUNCT_NOT_FOUND}" ]; then
        get_default_process_outdir_given_dirname "$dirname" "$processname"
    else
        outdir_basename=`process_function_outdir`
        echo "${dirname}/${outdir_basename}"
    fi
}

########
get_process_outdir()
{
    local processname=$1

    # Get full path of output directory
    local outd=${PIPELINE_OUTDIR}

    get_process_outdir_given_dirname "${outd}" "${processname}"
}

########
get_adaptive_processname()
{
    local processname=$1

    # Get caller process name
    local caller_processname=`$(get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}")`

    # Get suffix of caller process name
    local caller_suffix=`get_suffix_from_processname "${caller_processname}"`

    # Get adaptive process name
    local adaptive_processname=`get_processname_given_suffix "${processname}" "${caller_suffix}"`

    if process_is_defined "${adaptive_processname}"; then
        echo "${adaptive_processname}"
    else
        echo "${processname}"
    fi
}

########
get_process_outdir_adaptive()
{
    local processname=$1

    # Get adaptive process name
    local adaptive_processname=`get_adaptive_processname "${processname}"`

    # Return result
    get_process_outdir "${adaptive_processname}"
}

########
get_process_outdir_given_process_spec()
{
    local process_spec=$1

    # Get full path of output directory
    local outd=${PIPELINE_OUTDIR}

    # Obtain output directory for process
    local processname=`extract_processname_from_process_spec ${process_spec}`
    local process_outd=`get_process_outdir_given_dirname ${outd} ${processname}`

    echo ${process_outd}
}

########
create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" ${processname}`

    if [ -d ${outd} ]; then
        echo "Warning: ${processname} output directory already exists but pipeline was not finished or will be re-executed, directory content will be removed">&2
    else
        mkdir "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
default_reset_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" ${processname}`

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        rm -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
    fi
}

########
default_reset_outdir_for_process_array()
{
    :
}

########
display_begin_process_message()
{
    echo "Process started at `date +"%D %T"`" >&2
}

########
display_end_process_message()
{
    echo "Process finished at `date +"%D %T"`" >&2
}

########
get_process_start_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process started at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}

########
get_process_finish_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process finished at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}
