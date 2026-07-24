# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
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
debasher::_get_proc_document_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DOCUMENT}"
}

########
debasher::_process_description()
{
    local desc=$1
    echo $desc
}

########
debasher::_document_process_opts()
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
debasher::_document_process()
{
    local processname=$1
    local doc_options=$2

    # Print header
    echo "## ${processname}"
    echo ""

    # Print body
    echo "### Description"
    local document_funcname=`debasher::_get_proc_document_funcname "${processname}"`
    ${document_funcname}
    echo ""

    if [ ${doc_options} -eq 1 ]; then
        echo "### Command Line Options"
        local DIFFERENTIAL_CMDLINE_OPT_STR=""
        local explain_cmdline_opts_funcname=`debasher::_get_explain_cmdline_opts_funcname "${processname}"`
        ${explain_cmdline_opts_funcname}
        debasher::_document_process_opts "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    fi
}

########
debasher::_get_reset_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_RESET_OUTFILES}"
}

########
debasher::_get_exec_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXEC}"
}

########
debasher::_get_pyexec_varname()
{
    local processname=$1

    debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_PYEXEC}"
}

########
debasher::_get_rexec_varname()
{
    local processname=$1

    debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_REXEC}"
}

########
debasher::_get_perlexec_varname()
{
    local processname=$1

    debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_PERLEXEC}"
}

########
debasher::_get_groovyexec_varname()
{
    local processname=$1

    debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAME_GROOVYEXEC}"
}

########
debasher::_get_post_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_POST}"
}

########
debasher::_get_outdir_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_OUTDIR}"
}

########
debasher::_get_explain_cmdline_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"
}

########
debasher::_get_define_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"
}

########
debasher::_get_define_opt_deps_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPT_DEPS}"
}

########
debasher::_get_generate_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"
}

########
debasher::_get_generate_opts_size_funcname()
{
    local processname=$1
    local -n var_ref=$2

    local get_generate_opts_size_funcname_nr
    debasher::_search_process_func_nameref "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE}" "get_generate_opts_size_funcname_nr"
    var_ref="${get_generate_opts_size_funcname_nr}"
}

########
debasher::_get_skip_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_SKIP}"
}

########
debasher::_get_conda_envs_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_CONDA_ENVS}"
}

########
debasher::_get_docker_imgs_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_DOCKER_IMGS}"
}

########
debasher::_process_is_defined()
{
    local processname=$1
    local funcname=`debasher::_get_define_opts_funcname "${processname}"`

    if debasher::_func_exists "${funcname}"; then
        return 0
    else
        return 1
    fi
}

########
debasher::_uses_option_generator()
{
    local uses_option_generator_nr
    debasher::_get_generate_opts_size_funcname "${processname}" uses_option_generator_nr

    if debasher::_func_exists "${uses_option_generator_nr}"; then
        return 0
    else
        return 1
    fi
}

########
debasher::_write_opt_array()
{
    local varname=$1
    local opt_array_size=$2
    local opts_fname=$3

    if [ "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}" -le 0 ] || [ "${opt_array_size}" -le "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}" ]; then
        debasher::_print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
    else
        debasher::_print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
        debasher::_split_file_in_blocks "${opts_fname}" "${opts_fname}" "${DEBASHER_OPT_FILE_LINES_PER_BLOCK}"
        "${RM}" "${opts_fname}"
    fi
}

########
debasher::_get_numtasks_for_process()
{
    local processname=$1

    echo ${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}
}

########
debasher::_gen_opts_for_process_and_task()
{
    # WARNING: The resolve_proc_out_descriptor function should be called
    # in a subshell, otherwise it may clash with the caller due to its
    # use of the DESERIALIZE_ARGS variable
    debasher::_resolve_proc_out_descriptor()
    {
        local cmdline=$1
        local value=$2

        # Extract information of connected process
        local connected_proc_info="${value#$DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        debasher::_deserialize_args_given_sep "${connected_proc_info}" "${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
        local connected_proc=${DEBASHER_DESERIALIZED_ARGS[0]}
        local connected_proc_task_idx=${DEBASHER_DESERIALIZED_ARGS[1]}
        local connected_proc_opt=${DEBASHER_DESERIALIZED_ARGS[2]}

        # Resolve descriptor
        sargs=`debasher::_get_opts_for_process_and_task "${cmdline}" "${connected_proc}" "${connected_proc_task_idx}"`
        debasher::_deserialize_args "${sargs}"
        value=`debasher::_get_opt_value_from_func_args "${connected_proc_opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}"`

        echo "${value}"
    }

    debasher::_resolve_proc_out_descriptors()
    {
        local cmdline=$1

        # Iterate over DEBASHER_DESERIALIZED_ARGS array
        i=0
        while [ $i -lt ${#DEBASHER_DESERIALIZED_ARGS[@]} ]; do
            # Resolve process output descriptor if necessary
            local elem=${DEBASHER_DESERIALIZED_ARGS[$i]}
            if ! debasher::_str_is_option "${elem}" && debasher::_str_is_proc_out_opt_descriptor "${elem}"; then
                value=`debasher::_resolve_proc_out_descriptor "${cmdline}" "${elem}"`
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
    debasher::_resolve_proc_out_descriptors "${cmdline}"

    # Obtain serialized args
    debasher::_serialize_args_nameref "sargs_nr" "${DEBASHER_DESERIALIZED_ARGS[@]}"
    echo "${sargs_nr}"
}

########
debasher::_get_file_opts_for_process_and_task()
{
    local opts_fname=$1
    local task_idx=$2

    if [ -f "${opts_fname}" ]; then
        local line=$((task_idx + 1))
        debasher::_get_nth_file_line "${opts_fname}" "${line}"
    else
        local block_number=$((task_idx / DEBASHER_OPT_FILE_LINES_PER_BLOCK))
        local block_idx=$((task_idx % DEBASHER_OPT_FILE_LINES_PER_BLOCK))
        local block_fname="${opts_fname}_${block_number}"

        local line=$((block_idx + 1))
        debasher::_get_nth_file_line "${block_fname}" "${line}"
    fi
}

########
debasher::_get_opts_for_process_and_task()
{
    local cmdline=$1
    local processname=$2
    local task_idx=$3

    if debasher::_uses_option_generator "${processname}"; then
        local generate_opts_funcname=`debasher::_get_generate_opts_funcname "${processname}"`
        local proc_outdir=`debasher::_get_process_outdir "${processname}"`
        debasher::_gen_opts_for_process_and_task  "${cmdline}" "${processname}" "${proc_outdir}" "${generate_opts_funcname}" "${task_idx}"
    else
        local opts_fname=`debasher::_get_sched_opts_fname_for_process "${DEBASHER_PROGRAM_OUTDIR}" "${processname}"`
        debasher::_get_file_opts_for_process_and_task "${opts_fname}" "${task_idx}"
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
#   debasher::_define_opts_for_process <cmdline> <process_spec>
#
# The function does not return any value
debasher::_define_opts_for_process()
{
    debasher::_define_opts_loop()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`debasher::_extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`debasher::_get_process_outdir "${processname}"`

        # Obtain define_opts function name and call it
        local define_opts_funcname=`debasher::_get_define_opts_funcname "${processname}"`
        ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1
    }

    debasher::_define_opts_generator()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`debasher::_extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`debasher::_get_process_outdir "${processname}"`

        # Check if process dependencies were pre-specified for all processes
        if [ "${DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED}" -eq 0 ]; then
            # There are process dependencies to be determined, so it is
            # necessary to update output options information

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            debasher::_get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local generate_opts_funcname=`debasher::_get_generate_opts_funcname "${processname}"`
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Iterate over array tasks
            local task_idx
            for (( task_idx=0; task_idx<$array_size; task_idx++ )); do
                # Call option generator
                ${generate_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" "${task_idx}" || return 1

                # Update output options information
                debasher::_get_output_opts_info "${processname}" "${task_idx}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
            done

            # Set option list length
            DEBASHER_PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        else
            # There are no process dependencies to be determined, so it is
            # only necessary to update option list length

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            debasher::_get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Set option list length
            DEBASHER_PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        fi
    }

    # Initialize variables
    local cmdline=$1
    local process_spec=$2

    if debasher::_uses_option_generator "$processname"; then
        debasher::_define_opts_generator "${cmdline}" "${process_spec}"
    else
        debasher::_define_opts_loop "${cmdline}" "${process_spec}"
    fi
}

########
debasher::_get_processdeps_separator()
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
debasher::_find_dependency_for_process()
{
    local process_spec=$1
    local processname_part=$2

    # Obtain process dependencies separated by blanks
    local processdeps=`debasher::_extract_processdeps_from_process_spec "$process_spec"`
    local separator=`debasher::_get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    # Process dependencies
    local dep
    for dep in ${processdeps_blanks}; do
        local processname_part_in_dep=`debasher::_get_processname_part_in_dep ${dep}`
        if [ "${processname_part_in_dep}" = "${processname_part}" ]; then
            echo ${dep}
            return 0
        fi
    done
    echo ${DEBASHER_DEP_NOT_FOUND}
    return 1
}

########
debasher::_get_prg_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base exec dir
    execdir=`debasher::get_prg_exec_dir_given_basedir "${dirname}"`

    echo "${execdir}/${processname}"
}

########
debasher::_create_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    local execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`
    if [ ! -d "${execdir}" ]; then
        "${MKDIR}" -p "${execdir}" || return 1
    fi
}

########
debasher::_get_script_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}"
}

########
debasher::_get_process_stdout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    if [ "${opt_array_size}" -eq 1 ]; then
        echo "${execdir}/${processname}.${DEBASHER_STDOUT_FEXT}"
    else
        echo "${execdir}/${processname}_${task_idx}.${DEBASHER_STDOUT_FEXT}"
    fi
}

########
debasher::_get_process_log_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}.${DEBASHER_SCHED_LOG_FEXT}"
}

########
debasher::_get_task_log_filename()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3

    # Get exec dir
    execdir=`debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}_${task_idx}.${DEBASHER_SCHED_LOG_FEXT}"
}

########
debasher::_get_process_schedout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    if [ "${opt_array_size}" -eq 1 ]; then
        debasher::_get_process_log_filename "${dirname}" "${processname}"
    else
        debasher::_get_task_log_filename "${dirname}" "${processname}" "${task_idx}"
    fi
}

########
debasher::_get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd="${DEBASHER_PROGRAM_OUTDIR}"

        # Get processname
        local processname_part="${dep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"
        debasher::_get_process_outdir_given_dirname "${outd}" "${processname_part}"
    fi
}

########
debasher::_get_outd_for_dep_given_process_spec()
{
    local process_spec=$1
    local depname=$2

    local dep=`debasher::_find_dependency_for_process "${process_spec}" $depname`
    if [ ${dep} = ${DEBASHER_DEP_NOT_FOUND} ]; then
        return 1
    else
        local outd=`debasher::_get_outd_for_dep "${dep}"`
        echo "${outd}"
        return 0
    fi
}

########
debasher::_get_deptype_part_in_dep()
{
    local dep=$1
    local str_array
    IFS="${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
debasher::_get_processname_part_in_dep()
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
debasher::_task_array_elem_is_range()
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
debasher::_get_start_idx_in_range()
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
debasher::_get_end_idx_in_range()
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
# Check whether the argument at position $1 is a candidate to generate
# a process dependency. Returns 0 and writes the associated option index
# into the caller-provided variable if it is a candidate; returns 1
# otherwise.
debasher::_deserialized_args_idx_is_dep_candidate()
{
    local i=$1
    local -n idx_ref=$2

    local value="${DEBASHER_DESERIALIZED_ARGS[i]}"
    if ! debasher::_is_absolute_path "${value}"; then
        return 1
    fi

    local j=$((i-1))
    if [ $j -lt 0 ]; then
        return 1
    fi

    local opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
    if ! debasher::_str_is_option "${opt}" || debasher::_str_is_output_option "${opt}"; then
        return 1
    fi

    if [[ ! -v DEBASHER_OUT_VALUE_TO_PROCESSES[${value}] ]]; then
        return 1
    fi

    idx_ref=$j
    return 0
}

########
debasher::_get_procdeps_for_process()
{
    # Writes the result into the caller-provided variable name (no subshell,
    # no fork: this avoids the cost of command substitution at the call site).
    # Still forks internally when invoking the user-defined callback, since
    # that callback's contract is to echo its result.
    debasher::_get_deptype_using_func()
    {
        local define_opt_deps_funcname=$1
        local opt=$2
        local producer_process=$3
        local -n result_ref=$4

        if [ "${define_opt_deps_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            result_ref=""
        else
            result_ref=`"${define_opt_deps_funcname}" "${opt}" "${producer_process}"`
        fi
    }

    # Writes the result into the caller-provided variable name (no subshell,
    # no fork: this avoids the cost of command substitution entirely).
    debasher::_get_highest_priority_deptype()
    {
        local deptype_a=$1
        local deptype_b=$2
        local -n result_ref=$3

        if [ -z "${deptype_a}" ]; then
            deptype_a=${DEBASHER_NONE_PROCESSDEP_TYPE}
        fi
        if [ -z "${deptype_b}" ]; then
            deptype_b=${DEBASHER_NONE_PROCESSDEP_TYPE}
        fi

        if [ "${DEBASHER_PROCESSDEP_PRIORITY[$deptype_a]}" -gt "${DEBASHER_PROCESSDEP_PRIORITY[$deptype_b]}" ]; then
            result_ref=${deptype_a}
        else
            result_ref=${deptype_b}
        fi
    }

    debasher::_get_procdeps_for_process_task()
    {
        local cmdline=$1
        local processname=$2
        local define_opt_deps_funcname=$3
        local num_tasks=$4
        local task_idx=$5
        declare -A depdict

        local opts
        opts=`debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
        debasher::_deserialize_args "${opts}"

        local i
        for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
            # Skip early: is this argument even a dependency candidate?
            local j
            if ! debasher::_deserialized_args_idx_is_dep_candidate "$i" j; then
                continue
            fi

            local opt="${DEBASHER_DESERIALIZED_ARGS[j]}"
            local value="${DEBASHER_DESERIALIZED_ARGS[i]}"
            local processes="${DEBASHER_OUT_VALUE_TO_PROCESSES[${value}]}"

            # Case 1: value is a FIFO
            local augm_fifoname
            augm_fifoname=`debasher::_get_augm_fifoname_from_absname "${value}"`
            if [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                local proc_plus_idx="${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}"
                local processowner="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

                [ "${processowner}" = "${processname}" ] && continue

                local deptype
                debasher::_get_deptype_using_func "${define_opt_deps_funcname}" "${opt}" "${processowner}" deptype
                [ -z "${deptype}" ] && deptype="${DEBASHER_NONE_PROCESSDEP_TYPE}"
                [ "${deptype}" = "${DEBASHER_NONE_PROCESSDEP_TYPE}" ] && continue

                local highest_pri_deptype
                debasher::_get_highest_priority_deptype "${depdict[$processowner]}" "${deptype}" highest_pri_deptype
                depdict["${processowner}"]=${highest_pri_deptype}
                continue
            fi

            # Case 2: value is a file, possibly owned by several processes
            while [ -n "${processes}" ]; do
                local proc_plus_idx="${processes%%${DEBASHER_ASSOC_ARRAY_PROC_SEP}*}"
                local proc="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
                local idx="${proc_plus_idx#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"

                # Advance to the next process in the list up-front, so any
                # "continue" below doesn't risk an infinite loop
                local processes_aux="${processes#"${proc_plus_idx}${DEBASHER_ASSOC_ARRAY_PROC_SEP}"}"
                if [ "${processes}" = "${processes_aux}" ]; then
                    processes=""
                else
                    processes=${processes_aux}
                fi

                [ "${processname}" = "${proc}" ] && continue

                local deptype
                debasher::_get_deptype_using_func "${define_opt_deps_funcname}" "${opt}" "${proc}" deptype
                if [ -z "${deptype}" ]; then
                    if [ "$num_tasks" -gt 1 ] && [ "$task_idx" = "$idx" ]; then
                        deptype=${DEBASHER_AFTERCORR_PROCESSDEP_TYPE}
                    else
                        deptype=${DEBASHER_AFTEROK_PROCESSDEP_TYPE}
                    fi
                fi

                local highest_pri_deptype
                debasher::_get_highest_priority_deptype "${depdict[$proc]}" "${deptype}" highest_pri_deptype
                depdict["${proc}"]=${highest_pri_deptype}
            done
        done

        # Serialize depdict into the final "dep,dep,..." format
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

        echo "${processdeps}"
    }

    debasher::_get_procdeps_for_task_array()
    {
        # Initialize variables
        local cmdline=$1
        local processname=$2
        local define_opt_deps_funcname=$3
        local num_tasks=$4
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Obtain dependencies for task
            local prdeps_idx=`debasher::_get_procdeps_for_process_task "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}" "${task_idx}"`

            # Iterate over dependencies
            if [ -n "${prdeps_idx}" ]; then
                while IFS=${DEBASHER_PROCESSDEPS_SEP_COMMA} read -r processdep; do
                    # Extract dependency information
                    local deptype="${processdep%%${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}*}"
                    local proc="${processdep#*${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}}"

                    # Update associative array of dependencies
                    local highest_pri_deptype
                    debasher::_get_highest_priority_deptype "${depdict[$proc]}" "${deptype}" highest_pri_deptype
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

    # Get name of function to define option dependencies for process
    # (if defined)
    local define_opt_deps_funcname
    define_opt_deps_funcname=`debasher::_get_define_opt_deps_funcname "${processname}"`

    # Determine whether the process has multiple tasks
    local num_tasks=`debasher::_get_numtasks_for_process "${processname}"`
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        debasher::_get_procdeps_for_process_task "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        debasher::_get_procdeps_for_task_array "${cmdline}" "${processname}" "${define_opt_deps_funcname}" "${num_tasks}"
    fi
}

########
debasher::_get_procdeps_for_process_cached()
{
    local cmdline=$1
    local process_spec=$2

    # Extract process information
    local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

    # Check if process dependencies were already obtained
    if [[ -v DEBASHER_PROCESS_DEPENDENCIES["$processname"] ]]; then
        echo "${DEBASHER_PROCESS_DEPENDENCIES[$processname]}"
    else
        # Extract dependencies from process specification if given
        local deps=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`
        if [ "${deps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # No dependencies are provided in specification
            local deps=`debasher::_get_procdeps_for_process "${cmdline}" "$processname"`
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
debasher::_register_fifos_used_by_process()
{
    debasher::_register_fifos_used_by_process_task()
    {
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        local task_idx=$4

        local opts
        opts=`debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
        debasher::_deserialize_args "${opts}"

        local i
        for i in "${!DEBASHER_DESERIALIZED_ARGS[@]}"; do
            # Skip early: is this argument even a dependency candidate?
            local j
            if ! debasher::_deserialized_args_idx_is_dep_candidate "$i" j; then
                continue
            fi

            local value="${DEBASHER_DESERIALIZED_ARGS[i]}"

            local augm_fifoname
            augm_fifoname=`debasher::_get_augm_fifoname_from_absname "${value}"`
            [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]] || continue

            local proc_plus_idx="${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}"
            local processowner="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"

            [ "${processowner}" = "${processname}" ] && continue

            # The current process is not the owner of the FIFO: register it as a user
            DEBASHER_FIFO_USERS["${augm_fifoname}"]=${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}
        done
    }

    debasher::_register_fifos_used_by_task_array()
    {
        # Initialize variables
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        declare -A depdict

        # Iterate over tasks indices
        for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
            # Register fifos for task
            debasher::_register_fifos_used_by_process_task "${cmdline}" "${processname}" "${num_tasks}" "${task_idx}"
        done
    }

    local cmdline=$1
    local processname=$2

    # Determine whether the process has multiple tasks
    local num_tasks=`debasher::_get_numtasks_for_process "${processname}"`
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        debasher::_register_fifos_used_by_process_task "${cmdline}" "${processname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        debasher::_register_fifos_used_by_task_array "${cmdline}" "${processname}" "${num_tasks}"
    fi
}

########
debasher::_get_fifo_owners_for_process()
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
debasher::_get_default_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2
    echo "${dirname}/${processname}"
}

########
debasher::_get_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2

    # Get name of process function to set output directory
    process_function_outdir=`debasher::_get_outdir_funcname "${processname}"`

    if [ "${process_function_outdir}" = "${DEBASHER_FUNCT_NOT_FOUND}" ]; then
        debasher::_get_default_process_outdir_given_dirname "$dirname" "$processname"
    else
        local outdir_basename=${process_function_outdir}
        echo "${dirname}/${outdir_basename}"
    fi
}

########
debasher::_get_process_outdir()
{
    local processname=$1

    # Get full path of output directory
    local outd=${DEBASHER_PROGRAM_OUTDIR}

    debasher::_get_process_outdir_given_dirname "${outd}" "${processname}"
}

########
debasher::_get_process_outdir_given_process_spec()
{
    local process_spec=$1

    # Get full path of output directory
    local outd=${DEBASHER_PROGRAM_OUTDIR}

    # Obtain output directory for process
    local processname=`debasher::_extract_processname_from_process_spec ${process_spec}`
    local process_outd=`debasher::_get_process_outdir_given_dirname ${outd} "${processname}"`

    echo ${process_outd}
}

########
debasher::_create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d ${outd} ]; then
        echo "Warning: ${processname} output directory already exists but program was not finished or will be re-executed, directory content will be removed">&2
    else
        "${MKDIR}" "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
debasher::_default_reset_outfiles_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}"`

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        "${RM}" -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
    fi
}

########
debasher::_default_reset_outfiles_for_process_array()
{
    :
}

########
debasher::_display_begin_process_message()
{
    echo "Process started at `date '+%Y-%m-%d %H:%M:%S.%3N'`" >&2
}

########
debasher::_display_end_process_message()
{
    echo "Process finished at `date '+%Y-%m-%d %H:%M:%S.%3N'`" >&2
}

########
debasher::_get_process_start_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process started at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}

########
debasher::_get_process_finish_date()
{
    log_filename=$1
    if [ -f "${log_filename}" ]; then
        "${GREP}" "^Process finished at " "${log_filename}" | "${AWK}" '{for(i=4;i<=NF;++i) {printf"%s",$i; if(i<NF) printf" "}}'
    fi
}
