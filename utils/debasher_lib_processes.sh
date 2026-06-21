# DeBasher package
# Copyright (C) 2019-2024 Daniel Ortiz-Mart\'inez
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

#############################
# PROCESS-RELATED FUNCTIONS #
#############################

########
debasher::get_proc_document_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DOCUMENT}"
}

########
debasher::process_description()
{
    local desc=$1
    echo $desc
}

########
debasher::document_process_opts()
{
    local opts=$1
    for opt in ${opts}; do
        if [ "${DEBASHER_PROGRAM_OPT_REQ[${opt}]}" != "" ]; then
            reqflag=" (required) "
        else
            reqflag=" "
        fi

        # Print option
        if [ -z ${DEBASHER_PROGRAM_OPT_TYPE[$opt]} ]; then
            echo "\`${opt}\` ${DEBASHER_PROGRAM_OPT_DESC[$opt]}${reqflag}"
        else
            echo "\`${opt}\` ${DEBASHER_PROGRAM_OPT_TYPE[$opt]} ${DEBASHER_PROGRAM_OPT_DESC[$opt]}${reqflag}"
        fi
        echo ""
    done
}

########
debasher::document_process()
{
    local processname=$1
    local doc_options=$2

    # Print header
    echo "## ${processname}"
    echo ""

    # Print body
    echo "### Description"
    local document_funcname=`debasher::get_proc_document_funcname "${processname}"`
    ${document_funcname}
    echo ""

    if [ ${doc_options} -eq 1 ]; then
        echo "### Command Line Options"
        local DIFFERENTIAL_CMDLINE_OPT_STR=""
        local explain_cmdline_opts_funcname=`debasher::get_explain_cmdline_opts_funcname "${processname}"`
        ${explain_cmdline_opts_funcname}
        debasher::document_process_opts "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    fi
}

########
debasher::get_reset_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_RESET_OUTFILES}"
}

########
debasher::get_exec_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXEC}"
}

########
debasher::get_pyexec_varname()
{
    local processname=$1

    debasher::search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_PYEXEC}"
}

########
debasher::get_rexec_varname()
{
    local processname=$1

    debasher::search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_REXEC}"
}

########
debasher::get_perlexec_varname()
{
    local processname=$1

    debasher::search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_PERLEXEC}"
}

########
debasher::get_groovyexec_varname()
{
    local processname=$1

    debasher::search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_GROOVYEXEC}"
}

########
debasher::get_post_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_POST}"
}

########
debasher::get_outdir_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_OUTDIR}"
}

########
debasher::get_explain_cmdline_opts_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"
}

########
debasher::get_define_opts_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"
}

########
debasher::get_define_opt_deps_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPT_DEPS}"
}

########
debasher::get_generate_opts_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"
}

########
debasher::get_generate_opts_size_funcname()
{
    local processname=$1
    local -n var_ref=$2

    local get_generate_opts_size_funcname_nr
    debasher::search_process_func_nameref "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE}" "get_generate_opts_size_funcname_nr"
    var_ref="${get_generate_opts_size_funcname_nr}"
}

########
debasher::get_skip_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_SKIP}"
}

########
debasher::get_conda_envs_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_CONDA_ENVS}"
}

########
debasher::get_docker_imgs_funcname()
{
    local processname=$1

    debasher::search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DOCKER_IMGS}"
}

########
debasher::process_is_defined()
{
    local processname=$1
    local funcname=`debasher::get_define_opts_funcname "${processname}"`

    if debasher::func_exists "${funcname}"; then
        return 0
    else
        return 1
    fi
}

########
debasher::uses_option_generator()
{
    local uses_option_generator_nr
    debasher::get_generate_opts_size_funcname "${processname}" uses_option_generator_nr

    if debasher::func_exists "${uses_option_generator_nr}"; then
        return 0
    else
        return 1
    fi
}

########
debasher::write_opt_array()
{
    local varname=$1
    local opt_array_size=$2
    local opts_fname=$3

    if [ "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}" -le 0 ] || [ "${opt_array_size}" -le "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}" ]; then
        debasher::print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
    else
        debasher::print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
        debasher::split_file_in_blocks "${opts_fname}" "${opts_fname}" "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}"
        "${RM}" "${opts_fname}"
    fi
}

########
debasher::get_numtasks_for_process()
{
    local processname=$1

    echo ${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}
}

########
debasher::gen_opts_for_process_and_task()
{
    # WARNING: The resolve_proc_out_descriptor function should be called
    # in a subshell, otherwise it may clash with the caller due to its
    # use of the DESERIALIZE_ARGS variable
    resolve_proc_out_descriptor()
    {
        local cmdline=$1
        local value=$2

        # Extract information of connected process
        local connected_proc_info="${value#$DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        debasher::deserialize_args_given_sep "${connected_proc_info}" "${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
        local connected_proc=${DEBASHER_DESERIALIZED_ARGS[0]}
        local connected_proc_task_idx=${DEBASHER_DESERIALIZED_ARGS[1]}
        local connected_proc_opt=${DEBASHER_DESERIALIZED_ARGS[2]}

        # Resolve descriptor
        sargs=`debasher::get_opts_for_process_and_task "${cmdline}" "${connected_proc}" "${connected_proc_task_idx}"`
        debasher::deserialize_args "${sargs}"
        value=`debasher::get_opt_value_from_func_args "${connected_proc_opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}"`

        echo "${value}"
    }

    resolve_proc_out_descriptors()
    {
        local cmdline=$1

        # Iterate over DEBASHER_DESERIALIZED_ARGS array
        i=0
        while [ $i -lt ${#DEBASHER_DESERIALIZED_ARGS[@]} ]; do
            # Resolve process output descriptor if necessary
            local elem=${DEBASHER_DESERIALIZED_ARGS[$i]}
            if ! debasher::str_is_option "${elem}" && debasher::str_is_proc_out_opt_descriptor "${elem}"; then
                value=`resolve_proc_out_descriptor "${cmdline}" "${elem}"`
                DEBASHER_DESERIALIZED_ARGS[$i]=${value}
            fi
            i=$((i+1))
        done
    }

    local cmdline=$1
    local processname=$2
    local proc_outdir=$3
    local generate_opts_funcname=$4
    local task_idx=$5

    # Call options generator (output stored into DEBASHER_DESERIALIZED_ARGS)
    local proc_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]}
    ${generate_opts_funcname} "${cmdline}" "${proc_spec}" "${processname}" "${proc_outdir}" "${task_idx}" || return 1

    # Resove descriptors for connected processes
    resolve_proc_out_descriptors "${cmdline}"

    # Obtain serialized args
    debasher::serialize_args_nameref "sargs_nr" "${DEBASHER_DESERIALIZED_ARGS[@]}"
    echo "${sargs_nr}"
}

########
debasher::get_file_opts_for_process_and_task()
{
    local opts_fname=$1
    local task_idx=$2

    if [ -f "${opts_fname}" ]; then
        local line=$((task_idx + 1))
        debasher::get_nth_file_line "${opts_fname}" "${line}"
    else
        local block_number=$((task_idx / DEBASHER_OPT_FILE_LINES_PER_BLOCK))
        local block_idx=$((task_idx % DEBASHER_OPT_FILE_LINES_PER_BLOCK))
        local block_fname="${opts_fname}_${block_number}"

        local line=$((block_idx + 1))
        debasher::get_nth_file_line "${block_fname}" "${line}"
    fi
}

########
debasher::get_opts_for_process_and_task()
{
    local cmdline=$1
    local processname=$2
    local task_idx=$3

    if debasher::uses_option_generator "${processname}"; then
        local generate_opts_funcname=`debasher::get_generate_opts_funcname "${processname}"`
        local proc_outdir=`debasher::get_process_outdir "${processname}"`
        debasher::gen_opts_for_process_and_task  "${cmdline}" "${processname}" "${proc_outdir}" "${generate_opts_funcname}" "${task_idx}"
    else
        local opts_fname=`debasher::get_sched_opts_fname_for_process "${DEBASHER_PROGRAM_OUTDIR}" "${processname}"`
        debasher::get_file_opts_for_process_and_task "${opts_fname}" "${task_idx}"
    fi
}

########
# Public: Defines options for process.
#
# $1 - Command line
# $2 - Process specification
#
# Examples
#
#   debasher::define_opts_for_process <cmdline> <process_spec>
#
# The function does not return any value
debasher::define_opts_for_process()
{
    define_opts_loop()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`debasher::extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`debasher::get_process_outdir "${processname}"`

        # Obtain define_opts function name and call it
        local define_opts_funcname=`debasher::get_define_opts_funcname "${processname}"`
        ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1
    }

    define_opts_generator()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`debasher::extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`debasher::get_process_outdir "${processname}"`

        # Check if process dependencies were pre-specified for all processes
        if [ "${DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED}" -eq 0 ]; then
            # There are process dependencies to be determined, so it is
            # necessary to update output options information

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            debasher::get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local generate_opts_funcname=`debasher::get_generate_opts_funcname "${processname}"`
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Iterate over array tasks
            local task_idx
            for (( task_idx=0; task_idx<$array_size; task_idx++ )); do
                # Call option generator
                ${generate_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" "${task_idx}" || return 1

                # Update output options information
                get_output_opts_info "${processname}" "${task_idx}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
            done

            # Set option list length
            DEBASHER_PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        else
            # There are no process dependencies to be determined, so it is
            # only necessary to update option list length

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            debasher::get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Set option list length
            DEBASHER_PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        fi
    }

    # Initialize variables
    local cmdline=$1
    local process_spec=$2

    if debasher::uses_option_generator "$processname"; then
        define_opts_generator "${cmdline}" "${process_spec}"
    else
        define_opts_loop "${cmdline}" "${process_spec}"
    fi
}

########
debasher::get_processdeps_separator()
{
    local processdeps=$1
    if [[ "${processdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_COMMA}"* ]]; then
        echo "${DEBASHER_PROCESSDEPS_SEP_COMMA}"
    else
        if [[ "${processdeps}" == *"${DEBASHER_PROCESSDEPS_SEP_INTERR}"* ]]; then
            echo "${DEBASHER_PROCESSDEPS_SEP_INTERR}"
        else
            echo ""
        fi
    fi
}

########
debasher::find_dependency_for_process()
{
    local process_spec=$1
    local processname_part=$2

    # Obtain process dependencies separated by blanks
    local processdeps=`debasher::extract_processdeps_from_process_spec "$process_spec"`
    local separator=`debasher::get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`debasher::replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    # Process dependencies
    local dep
    for dep in ${processdeps_blanks}; do
        local processname_part_in_dep=`debasher::get_processname_part_in_dep ${dep}`
        if [ "${processname_part_in_dep}" = "${processname_part}" ]; then
            echo ${dep}
            return 0
        fi
    done
    echo ${DEBASHER_DEP_NOT_FOUND}
    return 1
}

########
debasher::get_prg_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base exec dir
    execdir=`debasher::get_prg_exec_dir_given_basedir "${dirname}"`

    echo "${execdir}/${processname}"
}

########
debasher::create_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    local execdir=`debasher::get_prg_exec_dir_for_process "${dirname}" "${processname}"`
    if [ ! -d "${execdir}" ]; then
        "${MKDIR}" -p "${execdir}" || return 1
    fi
}

########
debasher::get_script_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}"
}

########
debasher::get_process_stdout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    # Get exec dir
    execdir=`debasher::get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    if [ "${opt_array_size}" -eq 1 ]; then
        echo "${execdir}/${processname}.${DEBASHER_STDOUT_FEXT}"
    else
        echo "${execdir}/${processname}_${task_idx}.${DEBASHER_STDOUT_FEXT}"
    fi
}

########
debasher::get_process_log_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}.${DEBASHER_SCHED_LOG_FEXT}"
}

########
debasher::get_task_log_filename()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3

    # Get exec dir
    execdir=`debasher::get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}_${task_idx}.${DEBASHER_SCHED_LOG_FEXT}"
}

########
debasher::get_process_schedout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    if [ "${opt_array_size}" -eq 1 ]; then
        debasher::get_process_log_filename "${dirname}" "${processname}"
    else
        debasher::get_task_log_filename "${dirname}" "${processname}" "${task_idx}"
    fi
}

########
debasher::get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd="${DEBASHER_PROGRAM_OUTDIR}"

        # Get processname
        local processname_part="${dep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"
        debasher::get_process_outdir_given_dirname "${outd}" "${processname_part}"
    fi
}

########
debasher::get_outd_for_dep_given_process_spec()
{
    local process_spec=$1
    local depname=$2

    local dep=`debasher::find_dependency_for_process "${process_spec}" $depname`
    if [ ${dep} = ${DEBASHER_DEP_NOT_FOUND} ]; then
        return 1
    else
        local outd=`debasher::get_outd_for_dep "${dep}"`
        echo "${outd}"
        return 0
    fi
}

########
debasher::get_deptype_part_in_dep()
{
    local dep=$1
    local str_array
    IFS="${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
debasher::get_processname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ]; then
        echo ${dep}
    else
        local str_array
        IFS="${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"
        echo ${str_array[1]}
    fi
}

########
debasher::task_array_elem_is_range()
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
debasher::get_start_idx_in_range()
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
debasher::get_end_idx_in_range()
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
debasher::get_highest_priority_deptype()
{
    local deptype_a=$1
    local deptype_b=$2

    if [ -z "${deptype_a}" ]; then
        deptype_a=${DEBASHER_NONE_PROCESSDEP_TYPE}
    fi

    if [ -z "${deptype_b}" ]; then
        deptype_b=${DEBASHER_NONE_PROCESSDEP_TYPE}
    fi

    if [ "${DEBASHER_PROCESSDEP_PRIORITY[$deptype_a]}" -gt "${DEBASHER_PROCESSDEP_PRIORITY[$deptype_b]}" ]; then
        echo "${deptype_a}"
    else
        echo "${deptype_b}"
    fi
}

########
debasher::get_procdeps_for_process_cached()
{
    get_procdeps_for_process()
    {
        get_deptype_using_func()
        {
            local processname=$1
            local opt=$2
            local producer_process=$3
            local funcname=`debasher::get_define_opt_deps_funcname "${processname}"`
            if [ "${funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                :
            else
                "${funcname}" "${opt}" "${producer_process}"
            fi
        }

        get_procdeps_for_process_task()
        {
            # Initialize variables
            local cmdline=$1
            local processname=$2
            local num_tasks=$3
            local task_idx=$4
            declare -A depdict

            # Iterate over task options
            local opts=`debasher::get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
            debasher::deserialize_args "${opts}"
            local i
            for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
                # Check if a value represents an absolute path
                local value="${DEBASHER_DESERIALIZED_ARGS[i]}"
                if debasher::is_absolute_path "${value}"; then
                    local j=$((i-1))
                    if [ $j -ge 0 ]; then
                        opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
                        # Check if the option associated to the value is
                        # not an output option
                        if debasher::str_is_option "${opt}" && ! debasher::str_is_output_option "${opt}"; then
                            if [[ -v DEBASHER_OUT_VALUE_TO_PROCESSES[${value}] ]]; then
                                # The value is generated as output by
                                # another process (or processes)

                                # Check if the value represents a FIFO
                                local augm_fifoname=`debasher::get_augm_fifoname_from_absname "${value}"`
                                if [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                                    # The value represents a FIFO
                                    local proc_plus_idx=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
                                    local processowner="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
                                    local idx="${proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
                                    if [ "${processowner}" != "${processname}" ]; then
                                        # The current process is not the owner of the FIFO
                                        local deptype=`get_deptype_using_func "${processname}" ${opt} ${processowner}`
                                        if [ -z "${deptype}" ]; then
                                            deptype="${DEBASHER_NONE_PROCESSDEP_TYPE}"
                                        fi
                                        if [ "${deptype}" != "${DEBASHER_NONE_PROCESSDEP_TYPE}" ]; then
                                            local highest_pri_deptype=`debasher::get_highest_priority_deptype "${depdict[$processowner]}" "${deptype}"`
                                            depdict["${processowner}"]=${highest_pri_deptype}
                                        fi
                                    fi
                                else
                                    # The value represents a file
                                    local processes="${DEBASHER_OUT_VALUE_TO_PROCESSES[${value}]}"
                                    while [ -n "${processes}" ]; do
                                        # Extract process information
                                        local proc_plus_idx="${processes%%${DEBASHER_ASSOC_ARRAY_PROC_SEP}*}"
                                        local proc="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
                                        local idx="${proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
                                        if [ "${processname}" != "${proc}" ]; then
                                            # Determine dependency type
                                            local deptype=`get_deptype_using_func "${processname}" ${opt} ${proc}`
                                            if [ -z "${deptype}" ]; then
                                                if [ "$num_tasks" -gt 1 ] && [ "$task_idx" = "$idx" ]; then
                                                    deptype=${DEBASHER_AFTERCORR_PROCESSDEP_TYPE}
                                                else
                                                    deptype=${DEBASHER_AFTEROK_PROCESSDEP_TYPE}
                                                fi
                                            fi
                                            local highest_pri_deptype=`debasher::get_highest_priority_deptype "${depdict[$proc]}" "${deptype}"`
                                            # Update dependency dictionary
                                            depdict["${proc}"]=${highest_pri_deptype}
                                        fi
                                        # Update processes variable
                                        local processes_aux="${processes#"${proc_plus_idx}${DEBASHER_ASSOC_ARRAY_PROC_SEP}"}"
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
                local dep="${depdict[$proc]}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${proc}"
                if [ -z "$processdeps" ]; then
                    processdeps=${dep}
                else
                    processdeps="${processdeps}${DEBASHER_PROCESSDEPS_SEP_COMMA}${dep}"
                fi
            done

            # Return dependencies
            echo "${processdeps}"
        }

        get_procdeps_for_task_array()
        {
            # Initialize variables
            local cmdline=$1
            local processname=$2
            local num_tasks=$3
            declare -A depdict

            # Iterate over tasks indices
            for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
                # Obtain dependencies for task
                local prdeps_idx=`get_procdeps_for_process_task "${cmdline}" "${processname}" "${num_tasks}" "${task_idx}"`

                # Iterate over dependencies
                if [ -n "${prdeps_idx}" ]; then
                    while IFS=${DEBASHER_PROCESSDEPS_SEP_COMMA} read -r processdep; do
                        # Extract dependency information
                        local deptype="${processdep%%${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}*}"
                        local proc="${processdep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"

                        # Update associative array of dependencies
                        local highest_pri_deptype=`debasher::get_highest_priority_deptype "${depdict[$proc]}" "${deptype}"`
                        depdict["${proc}"]=${highest_pri_deptype}
                    done <<< "${prdeps_idx}"
                fi
            done

            # Instantiate processdeps variable
            local processdeps=""
            local proc
            for proc in "${!depdict[@]}"; do
                local dep="${depdict[$proc]}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${proc}"
                if [ -z "$processdeps" ]; then
                    processdeps=${dep}
                else
                    processdeps="${processdeps}${DEBASHER_PROCESSDEPS_SEP_COMMA}${dep}"
                fi
            done

            # Return dependencies
            echo "${processdeps}"
        }

        local cmdline=$1
        local processname=$2

        # Determine whether the process has multiple tasks
        local num_tasks=`debasher::get_numtasks_for_process "${processname}"`
        if [ "${num_tasks}" -eq 1 ]; then
            # The process has only one task
            get_procdeps_for_process_task "${cmdline}" "${processname}" "${num_tasks}" 0
        else
            # The process is an array of tasks
            get_procdeps_for_task_array "${cmdline}" "${processname}" "${num_tasks}"
        fi
    }

    local cmdline=$1
    local process_spec=$2

    # Extract process information
    local processname=`debasher::extract_processname_from_process_spec "$process_spec"`

    # Check if process dependencies were already obtained
    if [[ -v DEBASHER_PROCESS_DEPENDENCIES["$processname"] ]]; then
        echo "${DEBASHER_PROCESS_DEPENDENCIES[$processname]}"
    else
        # Extract dependencies from process specification if given
        local deps=`debasher::extract_processdeps_from_process_spec "${process_spec}"`
        if [ "${deps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # No dependencies are provided in specification
            local deps=`get_procdeps_for_process "${cmdline}" "$processname"`
            if [ -z "${deps}" ]; then
                deps="${DEBASHER_NONE_PROCESSDEP_TYPE}"
            fi
            # Add prefix to result
            deps="${DEBASHER_PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            DEBASHER_PROCESS_DEPENDENCIES["$processname"]=${deps}
            echo "$deps"
        else
            # Add prefix to result
            deps="${DEBASHER_PROCESSDEPS_SPEC}=${deps}"
            # Cache dependencies
            DEBASHER_PROCESS_DEPENDENCIES["$processname"]=${deps}
            echo "$deps"
        fi
    fi
}

########
debasher::register_fifos_used_by_process()
{
    register_fifos_used_by_process_task()
    {
        # Initialize variables
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        local task_idx=$4

        # Iterate over task options
        local opts=`debasher::get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
        debasher::deserialize_args "${opts}"
        for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
            # Check if a value represents an absolute path
            local value="${DEBASHER_DESERIALIZED_ARGS[i]}"
            if debasher::is_absolute_path "${value}"; then
                j=$((i-1))
                if [ $j -ge 0 ]; then
                    opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
                    # Check if the option associated to the value is
                    # not an output option
                    if debasher::str_is_option "${opt}" && ! debasher::str_is_output_option "${opt}"; then
                        augm_fifoname=`debasher::get_augm_fifoname_from_absname "${value}"`
                        if [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                            # The value is a FIFO
                            local proc_plus_idx=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
                            local processowner="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
                            local idx="${proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
                            if [ "${processowner}" != "${processname}" ]; then
                                # The current process is not the owner of the FIFO
                                DEBASHER_FIFO_USERS["${augm_fifoname}"]=${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}
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
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Register fifos for task
            register_fifos_used_by_process_task "${cmdline}" "${processname}" "${num_tasks}" "${task_idx}"
        done
    }

    local cmdline=$1
    local processname=$2

    # Determine whether the process has multiple tasks
    local num_tasks=`debasher::get_numtasks_for_process "${processname}"`
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        register_fifos_used_by_process_task "${cmdline}" "${processname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        register_fifos_used_by_task_array "${cmdline}" "${processname}" "${num_tasks}"
    fi
}

########
debasher::get_fifo_owners_for_process()
{
    local processname=$1
    declare -A owners

    # Iterate over fifo users
    for augm_fifoname in "${!DEBASHER_FIFO_USERS[@]}"; do
        local user=${DEBASHER_FIFO_USERS["${augm_fifoname}"]}
        local user_proc="${user%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
        if [ "${user_proc}" = "${processname}" ]; then
            local owner=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
            local owner_proc="${owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
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
debasher::get_default_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2
    echo "${dirname}/${processname}"
}

########
debasher::get_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2

    # Get name of process function to set output directory
    process_function_outdir=`debasher::get_outdir_funcname "${processname}"`

    if [ "${process_function_outdir}" = "${DEBASHER_FUNCT_NOT_FOUND}" ]; then
        debasher::get_default_process_outdir_given_dirname "$dirname" "$processname"
    else
        local outdir_basename=${process_function_outdir}
        echo "${dirname}/${outdir_basename}"
    fi
}

########
debasher::get_process_outdir()
{
    local processname=$1

    # Get full path of output directory
    local outd=${DEBASHER_PROGRAM_OUTDIR}

    debasher::get_process_outdir_given_dirname "${outd}" "${processname}"
}

########
debasher::get_process_outdir_given_process_spec()
{
    local process_spec=$1

    # Get full path of output directory
    local outd=${DEBASHER_PROGRAM_OUTDIR}

    # Obtain output directory for process
    local processname=`debasher::extract_processname_from_process_spec ${process_spec}`
    local process_outd=`debasher::get_process_outdir_given_dirname ${outd} "${processname}"`

    echo ${process_outd}
}

########
debasher::create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`debasher::get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d ${outd} ]; then
        echo "Warning: ${processname} output directory already exists but program was not finished or will be re-executed, directory content will be removed">&2
    else
        "${MKDIR}" "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
debasher::default_reset_outfiles_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`debasher::get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        "${RM}" -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
    fi
}

########
debasher::default_reset_outfiles_for_process_array()
{
    :
}

########
debasher::display_begin_process_message()
{
    echo "Process started at `date +"%D %T"`" >&2
}

########
debasher::display_end_process_message()
{
    echo "Process finished at `date +"%D %T"`" >&2
}

########
debasher::get_process_start_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process started at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}

########
debasher::get_process_finish_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process finished at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}
