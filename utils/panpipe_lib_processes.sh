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
pipeline_process_spec_is_ok()
{
    local process_spec=$1

    local fieldno=1
    local field
    for field in $process_spec; do
        if [[ ${field} = "${PROCESSDEPS_SPEC}="* ]]; then
            if [ $fieldno -ge 2 ]; then
                return 0
            fi
        fi
        fieldno=$((fieldno + 1))
    done

    return 1
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
get_reset_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_RESET_OUTFILES}"
}

########
get_exec_funcname()
{
    local processname=$1

    search_process_mandatory_func "${processname}" "${PROCESS_METHOD_NAME_EXEC}"
}

########
get_post_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_POST}"
}

########
get_outdir_funcname()
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
get_define_opt_deps_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_DEFINE_OPT_DEPS}"
}

########
get_skip_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_SKIP}"
}

########
get_conda_envs_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_CONDA_ENVS}"
}

########
get_docker_imgs_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_DOCKER_IMGS}"
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
get_numtasks_for_process()
{
    local processname=$1

    echo "${PROCESS_OPT_LIST[${processname}${ASSOC_ARRAY_ELEM_SEP}${ASSOC_ARRAY_KEY_LEN}]}"
}

########
get_optlist_for_process_and_task()
{
    local processname=$1
    local task_idx=$2
    echo "${PROCESS_OPT_LIST[${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}]}"
}

########
define_opts_for_process()
{
    clear_def_opts_vars()
    {
        clear_curr_opt_list_array
    }

    store_opt_list_in_assoc_array()
    {
        local processname=$1
        local array_length=${#CURRENT_PROCESS_OPT_LIST[@]}
        PROCESS_OPT_LIST["${processname}${ASSOC_ARRAY_ELEM_SEP}${ASSOC_ARRAY_KEY_LEN}"]=${array_length}
        for task_idx in "${!CURRENT_PROCESS_OPT_LIST[@]}"; do
            PROCESS_OPT_LIST["${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}"]=${CURRENT_PROCESS_OPT_LIST[$task_idx]}
        done
    }

    get_output_params_info()
    {
        local processname=$1
        for task_idx in "${!CURRENT_PROCESS_OPT_LIST[@]}"; do
            deserialize_args "${CURRENT_PROCESS_OPT_LIST[$task_idx]}"
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
                                local process_info="${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}"
                                if [[ -v PROCESS_OUT_VALUES["${value}"] ]]; then
                                    PROCESS_OUT_VALUES["$value"]=${PROCESS_OUT_VALUES["$value"]}${ASSOC_ARRAY_PROC_SEP}${process_info}
                                else
                                    PROCESS_OUT_VALUES["$value"]=${process_info}
                                fi
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

    # Copy processname_def_opts function if necessary
    copy_process_defopts_func "${processname}"

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
create_scripts_dir_for_process()
{
    local dirname=$1
    local processname=$2

    local scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`
    if [ ! -d "${scriptsdir}" ]; then
        "${MKDIR}" -p "${scriptsdir}" || return 1
    fi
}

########
get_ppl_scripts_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base scripts dir
    scriptsdir=`get_ppl_scripts_dir_given_basedir "${dirname}"`

    echo "${scriptsdir}/${processname}"
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
        local processname_part="${dep#*${PROCESS_PLUS_DEPTYPE_SEP}}"
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
    echo ${#CURRENT_PROCESS_OPT_LIST[@]}
}

########
get_deptype_part_in_dep()
{
    local dep=$1
    local str_array
    IFS="${PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
get_processname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "${NONE_PROCESSDEP_TYPE}" ]; then
        echo ${dep}
    else
        local str_array
        IFS="${PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"
        echo ${str_array[1]}
    fi
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
get_highest_priority_deptype()
{
    local deptype_a=$1
    local deptype_b=$2

    if [ -z "${deptype_a}" ]; then
        deptype_a=${NONE_PROCESSDEP_TYPE}
    fi

    if [ -z "${deptype_b}" ]; then
        deptype_b=${NONE_PROCESSDEP_TYPE}
    fi

    if [ "${PROCESSDEP_PRIORITY[$deptype_a]}" -gt "${PROCESSDEP_PRIORITY[$deptype_b]}" ]; then
        echo "${deptype_a}"
    else
        echo "${deptype_b}"
    fi
}

########
get_procdeps_for_process_cached()
{
    get_procdeps_for_process()
    {
        get_deptype_using_func()
        {
            local processname=$1
            local opt=$2
            local producer_process=$3
            local funcname=`get_define_opt_deps_funcname "${processname}"`
            if [ "${funcname}" = ${FUNCT_NOT_FOUND} ]; then
                :
            else
                "${funcname}" "${opt}" "${producer_process}"
            fi
        }

        get_procdeps_for_process_task()
        {
            # Initialize variables
            local processname=$1
            local num_tasks=$2
            local task_idx=$3
            declare -A depdict

            # Iterate over task options
            local optlist=`get_optlist_for_process_and_task "${processname}" "${task_idx}"`
            deserialize_args "${optlist}"
            local i
            for i in "${!DESERIALIZED_ARGS[@]}"; do
                # Check if a value represents an absolute path
                local value="${DESERIALIZED_ARGS[i]}"
                if is_absolute_path "${value}"; then
                    local j=$((i-1))
                    if [ $j -ge 0 ]; then
                        opt="${DESERIALIZED_ARGS[j]}"
                        # Check if the option associated to the value is
                        # not an output option
                        if str_is_option "${opt}" && ! str_is_output_option "${opt}"; then
                            if [[ -v PROCESS_OUT_VALUES[${value}] ]]; then
                                # The value is generated as output by
                                # another process (or processes)

                                # Check if the value represents a FIFO
                                local augm_fifoname=`get_augm_fifoname_from_absname "${value}"`
                                if [[ -v PIPELINE_FIFOS["${augm_fifoname}"] ]]; then
                                    # The value represents a FIFO
                                    local proc_plus_idx=${PIPELINE_FIFOS["${augm_fifoname}"]}
                                    local processowner="${proc_plus_idx%%${ASSOC_ARRAY_ELEM_SEP}*}"
                                    local idx="${proc_plus_idx#*${ASSOC_ARRAY_ELEM_SEP}}"
                                    if [ "${processowner}" != "${processname}" ]; then
                                        # The current process is not the owner of the FIFO
                                        local deptype=`get_deptype_using_func ${processname} ${opt} ${processowner}`
                                        if [ -z "${deptype}" ]; then
                                            deptype="${NONE_PROCESSDEP_TYPE}"
                                        fi
                                        if [ "${deptype}" != "${NONE_PROCESSDEP_TYPE}" ]; then
                                            local highest_pri_deptype=`get_highest_priority_deptype "${depdict[$processowner]}" "${deptype}"`
                                            depdict["${processowner}"]=${highest_pri_deptype}
                                        fi
                                    fi
                                else
                                    # The value represents a file
                                    local processes="${PROCESS_OUT_VALUES[${value}]}"
                                    while [ -n "${processes}" ]; do
                                        # Extract process information
                                        local proc_plus_idx="${processes%%${ASSOC_ARRAY_PROC_SEP}*}"
                                        local proc="${proc_plus_idx%%${ASSOC_ARRAY_ELEM_SEP}*}"
                                        local idx="${proc_plus_idx#*${ASSOC_ARRAY_ELEM_SEP}}"
                                        if [ "${processname}" != "${proc}" ]; then
                                            # Determine dependency type
                                            local deptype=`get_deptype_using_func ${processname} ${opt} ${proc}`
                                            if [ -z "${deptype}" ]; then
                                                if [ "$num_tasks" -gt 1 ] && [ "$task_idx" = "$idx" ]; then
                                                    deptype=${AFTERCORR_PROCESSDEP_TYPE}
                                                else
                                                    deptype=${AFTEROK_PROCESSDEP_TYPE}
                                                fi
                                            fi
                                            local highest_pri_deptype=`get_highest_priority_deptype "${depdict[$proc]}" "${deptype}"`
                                            # Update dependency dictionary
                                            depdict["${proc}"]=${highest_pri_deptype}
                                        fi
                                        # Update processes variable
                                        local processes_aux="${processes#"${proc_plus_idx}${ASSOC_ARRAY_PROC_SEP}"}"
                                        if [ "${processes}" = "${processes_aux}" ]; then
                                            processes=""
                                        else
                                            processes=${processes_aux}
                                        fi
                                    done
                                fi
                            fi
                        fi
                    fi
                fi
            done

            # Instantiate processdeps variable
            local processdeps=""
            local proc
            for proc in "${!depdict[@]}"; do
                local dep="${depdict[$proc]}${PROCESS_PLUS_DEPTYPE_SEP}${proc}"
                if [ -z "$processdeps" ]; then
                    processdeps=${dep}
                else
                    processdeps="${processdeps}${PROCESSDEPS_SEP_COMMA}${dep}"
                fi
            done

            # Return dependencies
            echo "${processdeps}"
        }

        get_procdeps_for_task_array()
        {
            # Initialize variables
            local processname=$1
            local num_tasks=$2
            declare -A depdict

            # Iterate over tasks indices
            for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
                # Obtain dependencies for task
                local prdeps_idx=`get_procdeps_for_process_task "${processname}" "${num_tasks}" "${task_idx}"`

                # Iterate over dependencies
                if [ -n "${prdeps_idx}" ]; then
                    while IFS=${PROCESSDEPS_SEP_COMMA} read -r processdep; do
                        # Extract dependency information
                        local deptype="${processdep%%${PROCESS_PLUS_DEPTYPE_SEP}*}"
                        local proc="${processdep#*${PROCESS_PLUS_DEPTYPE_SEP}}"

                        # Update associative array of dependencies
                        local highest_pri_deptype=`get_highest_priority_deptype "${depdict[$proc]}" "${deptype}"`
                        depdict["${proc}"]=${highest_pri_deptype}
                    done <<< "${prdeps_idx}"
                fi
            done

            # Instantiate processdeps variable
            local processdeps=""
            local proc
            for proc in "${!depdict[@]}"; do
                local dep="${depdict[$proc]}${PROCESS_PLUS_DEPTYPE_SEP}${proc}"
                if [ -z "$processdeps" ]; then
                    processdeps=${dep}
                else
                    processdeps="${processdeps}${PROCESSDEPS_SEP_COMMA}${dep}"
                fi
            done

            # Return dependencies
            echo "${processdeps}"
        }

        local processname=$1
        # Determine whether the process has multiple tasks
        local num_tasks=`get_numtasks_for_process "${processname}"`
        if [ "${num_tasks}" -eq 1 ]; then
            # The process has only one task
            get_procdeps_for_process_task "${processname}" "${num_tasks}" 0
        else
            # The process is an array of tasks
            get_procdeps_for_task_array "${processname}" "${num_tasks}"
        fi
    }
    local process_spec=$1

    # Extract process information
    local processname=`extract_processname_from_process_spec "$process_spec"`

    # Check if process dependencies were already obtained
    if [[ -v PROCESS_DEPENDENCIES["$processname"] ]]; then
        echo "${PROCESS_DEPENDENCIES[$processname]}"
    else
        # Extract dependencies from process specification if given
        local deps=`extract_processdeps_from_process_spec "${process_spec}"`
        if [ "${deps}" = "${ATTR_NOT_FOUND}" ]; then
            # No dependencies are provided in specification
            local deps=`get_procdeps_for_process "$processname"`
            if [ -z "${deps}" ]; then
                deps="${NONE_PROCESSDEP_TYPE}"
            fi
            # Add prefix to result
            deps="${PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            PROCESS_DEPENDENCIES[$processname]=${deps}
            echo "$deps"
        else
            # Add prefix to result
            deps="${PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            PROCESS_DEPENDENCIES[$processname]=${deps}
            echo "$deps"
        fi
    fi
}

########
register_fifos_used_by_process()
{
    register_fifos_used_by_process_task()
    {
        # Initialize variables
        local processname=$1
        local num_tasks=$2
        local task_idx=$3

        # Iterate over task options
        local optlist=`get_optlist_for_process_and_task "${processname}" "${task_idx}"`
        deserialize_args "${optlist}"
        for i in "${!DESERIALIZED_ARGS[@]}"; do
            # Check if a value represents an absolute path
            local value="${DESERIALIZED_ARGS[i]}"
            if is_absolute_path "${value}"; then
                j=$((i-1))
                if [ $j -ge 0 ]; then
                    opt="${DESERIALIZED_ARGS[j]}"
                    # Check if the option associated to the value is
                    # not an output option
                    if str_is_option "${opt}" && ! str_is_output_option "${opt}"; then
                        augm_fifoname=`get_augm_fifoname_from_absname "${value}"`
                        if [[ -v PIPELINE_FIFOS["${augm_fifoname}"] ]]; then
                            # The value is a FIFO
                            local proc_plus_idx=${PIPELINE_FIFOS["${augm_fifoname}"]}
                            local processowner="${proc_plus_idx%%${ASSOC_ARRAY_ELEM_SEP}*}"
                            local idx="${proc_plus_idx#*${ASSOC_ARRAY_ELEM_SEP}}"
                            if [ "${processowner}" != "${processname}" ]; then
                                # The current process is not the owner of the FIFO
                                FIFO_USERS["${augm_fifoname}"]=${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}
                            fi
                        fi
                    fi
                fi
            fi
        done
    }

    register_fifos_used_by_task_array()
    {
        # Initialize variables
        local processname=$1
        local num_tasks=$2
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Register fifos for task
            register_fifos_used_by_process_task "${processname}" "${num_tasks}" "${task_idx}"
        done
    }

    local processname=$1

    # Determine whether the process has multiple tasks
    local num_tasks=`get_numtasks_for_process "${processname}"`
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        register_fifos_used_by_process_task "${processname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        register_fifos_used_by_task_array "${processname}" "${num_tasks}"
    fi
}

########
get_fifo_owners_for_process()
{
    local processname=$1
    declare -A owners

    # Iterate over fifo users
    for augm_fifoname in "${!FIFO_USERS[@]}"; do
        local user=${FIFO_USERS["${augm_fifoname}"]}
        local user_proc="${user%%${ASSOC_ARRAY_ELEM_SEP}*}"
        if [ "${user_proc}" = "${processname}" ]; then
            local owner=${PIPELINE_FIFOS["${augm_fifoname}"]}
            local owner_proc="${owner%%${ASSOC_ARRAY_ELEM_SEP}*}"
            owners["${owner_proc}"]=1
        fi
    done

    # Obtain result
    local result=""
    for owner in "${!owners[@]}"; do
        if [ -z "${result}" ]; then
            result=${owner}
        else
            result="${result} ${owner}"
        fi
    done

    echo "${result}"
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
    process_function_outdir=`get_outdir_funcname ${processname}`

    if [ "${process_function_outdir}" = "${FUNCT_NOT_FOUND}" ]; then
        get_default_process_outdir_given_dirname "$dirname" "$processname"
    else
        local outdir_basename=${process_function_outdir}
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
    local caller_processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`

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
copy_process_func()
{
    local methodname=$1
    local processname=$2
    local processname_wo_suffix=`remove_suffix_from_processname "${processname}"`
    local suffix=`get_suffix_from_processname "${processname}"`

    if [ -n "${suffix}" ]; then
        local process_function_wo_suffix=`get_process_funcname "${processname_wo_suffix}" "${methodname}"`
        local process_function=`get_process_funcname "${processname}" "${methodname}"`
        if func_exists "${process_function_wo_suffix}" && ! func_exists "${process_function}"; then
            copy_func "${process_function_wo_suffix}" "${process_function}"
        fi
    fi
}

########
copy_process_defopts_func()
{
    local processname=$1

    copy_process_func "${PROCESS_METHOD_NAME_DEFINE_OPTS}" "${processname}"
}

########
create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d ${outd} ]; then
        echo "Warning: ${processname} output directory already exists but pipeline was not finished or will be re-executed, directory content will be removed">&2
    else
        "${MKDIR}" "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
default_reset_outfiles_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        rm -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
    fi
}

########
default_reset_outfiles_for_process_array()
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
