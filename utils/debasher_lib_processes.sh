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
get_proc_document_funcname()
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
        if [ "${PROGRAM_OPT_REQ[${opt}]}" != "" ]; then
            reqflag=" (required) "
        else
            reqflag=" "
        fi

        # Print option
        if [ -z ${PROGRAM_OPT_TYPE[$opt]} ]; then
            echo "\`${opt}\` ${PROGRAM_OPT_DESC[$opt]}${reqflag}"
        else
            echo "\`${opt}\` ${PROGRAM_OPT_TYPE[$opt]} ${PROGRAM_OPT_DESC[$opt]}${reqflag}"
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
    echo "## ${processname}"
    echo ""

    # Print body
    echo "### Description"
    local document_funcname=`get_proc_document_funcname ${processname}`
    ${document_funcname}
    echo ""

    if [ ${doc_options} -eq 1 ]; then
        echo "### Command Line Options"
        DIFFERENTIAL_CMDLINE_OPT_STR=""
        local explain_cmdline_opts_funcname=`get_explain_cmdline_opts_funcname ${processname}`
        ${explain_cmdline_opts_funcname}
        document_process_opts "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    fi
}

########
program_process_spec_is_ok()
{
    local process_spec=$1

    local fieldno=1
    local procdeps_correct=1
    local field
    for field in $process_spec; do
        if [[ ${field} = "${PROCESSDEPS_SPEC}="* ]]; then
            if [ "$fieldno" = 1 ]; then
                procdeps_correct=0
            fi
        fi
        fieldno=$((fieldno + 1))
    done

    if [ "${fieldno}" -gt 0 ] && [ "${procdeps_correct}" = 1 ]; then
        return 0
    else
        return 1
    fi
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
get_pyexec_varname()
{
    local processname=$1

    search_process_var "${processname}" "${PROCESS_METHOD_NAME_PYEXEC}"
}

########
get_rexec_varname()
{
    local processname=$1

    search_process_var "${processname}" "${PROCESS_METHOD_NAME_REXEC}"
}

########
get_perlexec_varname()
{
    local processname=$1

    search_process_var "${processname}" "${PROCESS_METHOD_NAME_PERLEXEC}"
}

########
get_groovyexec_varname()
{
    local processname=$1

    search_process_var "${processname}" "${PROCESS_METHOD_NAME_GROOVYEXEC}"
}

########
get_pyexec_command()
{
    echo "${PYTHON} -c"
}

########
get_rexec_command()
{
    echo "${RSCRIPT} -e"
}

########
get_perlexec_command()
{
    echo "${PERL} -e"
}

########
get_groovyexec_command()
{
    echo "${GROOVY} -e"
}

########
get_exec_commvar()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${pyexec_varname}"
        return 0
    fi

    # Try with R
    local rexec_varname=`get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${rexec_varname}"
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${perlexec_varname}"
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${groovyexec_varname}"
        return 0
    fi
}

########
get_end_of_options_marker()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${PY_END_OF_OPTIONS_MARKER}"
        return 0
    fi

    # Try with R
    local rexec_varname=`get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${R_END_OF_OPTIONS_MARKER}"
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${PL_END_OF_OPTIONS_MARKER}"
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${GROOVY_END_OF_OPTIONS_MARKER}"
        return 0
    fi
}

########
get_end_of_options_marker_given_var()
{
    local varname=$1

    # Extract the part after the last underscore
    local suffix="${varname##*_}"

    case "$suffix" in
        "py")
            echo "${PY_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "R")
            echo "${R_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "pl")
            echo "${PL_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "groovy")
            echo "${GROOVY_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
serialize_exec_commvar()
{
    # Serialize a variable name storing a command for execution
    local exec_commvar=$1

    if [ -n "${exec_commvar}" ]; then
        echo "\"\$${exec_commvar}\""
    fi
}

########
get_exec_command_given_var()
{
    local varname=$1

    # Extract the part after the last underscore
    local suffix="${varname##*_}"

    case "$suffix" in
        "py")
            get_pyexec_command "${pyexec_varname}"
            return 0
            ;;
        "R")
            get_rexec_command "${rexec_varname}"
            return 0
            ;;
        "pl")
            get_perlexec_command "${perlexec_varname}"
            return 0
            ;;
        "groovy")
            get_groovyexec_command "${groovyexec_varname}"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
get_exec_command_or_funcname()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_pyexec_command "${pyexec_varname}"
        return 0
    fi

    # Try with R
    local rexec_varname=`get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_rexec_command "${rexec_varname}"
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_perlexec_command "${perlexec_varname}"
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_groovyexec_command "${groovyexec_varname}"
        return 0
    fi

    # Finally, try with native function
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
get_generate_opts_funcname()
{
    local processname=$1

    search_process_func "${processname}" "${PROCESS_METHOD_NAME_GENERATE_OPTS}"
}

########
get_generate_opts_size_funcname()
{
    local processname=$1
    local -n var_ref=$2

    local get_generate_opts_size_funcname_nr
    search_process_func_nameref "${processname}" "${PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE}" "get_generate_opts_size_funcname_nr"
    var_ref="${get_generate_opts_size_funcname_nr}"
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
uses_option_generator()
{
    local uses_option_generator_nr
    get_generate_opts_size_funcname "${processname}" uses_option_generator_nr

    if func_exists "${uses_option_generator_nr}"; then
        return 0
    else
        return 1
    fi
}

########
write_opt_array()
{
    local varname=$1
    local opt_array_size=$2
    local opts_fname=$3

    if [ "${OPT_FILE_LINES_PER_BLOCK}" -le 0 ] || [ "${opt_array_size}" -le "${OPT_FILE_LINES_PER_BLOCK}" ]; then
        print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
    else
        print_array_elems "${varname}" "${opt_array_size}" > "${opts_fname}"
        split_file_in_blocks "${opts_fname}" "${opts_fname}" "${OPT_FILE_LINES_PER_BLOCK}"
        "${RM}" "${opts_fname}"
    fi
}

########
get_numtasks_for_process()
{
    local processname=$1

    echo ${PROCESS_OPT_LIST_LEN["${processname}"]}
}

########
gen_opts_for_process_and_task()
{
    # WARNING: The resolve_proc_out_descriptor function should be called
    # in a subshell, otherwise it may clash with the caller due to its
    # use of the DESERIALIZE_ARGS variable
    resolve_proc_out_descriptor()
    {
        local cmdline=$1
        local value=$2

        # Extract information of connected process
        local connected_proc_info="${value#$PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        deserialize_args_given_sep "${connected_proc_info}" "${ASSOC_ARRAY_ELEM_SEP}"
        local connected_proc=${DESERIALIZED_ARGS[0]}
        local connected_proc_task_idx=${DESERIALIZED_ARGS[1]}
        local connected_proc_opt=${DESERIALIZED_ARGS[2]}

        # Resolve descriptor
        sargs=`get_opts_for_process_and_task "${cmdline}" "${connected_proc}" "${connected_proc_task_idx}"`
        deserialize_args "${sargs}"
        value=`get_opt_value_from_func_args "${connected_proc_opt}" "${DESERIALIZED_ARGS[@]}"`

        echo "${value}"
    }

    resolve_proc_out_descriptors()
    {
        local cmdline=$1

        # Iterate over DESERIALIZED_ARGS array
        i=0
        while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
            # Resolve process output descriptor if necessary
            local elem=${DESERIALIZED_ARGS[$i]}
            if ! str_is_option "${elem}" && str_is_proc_out_opt_descriptor "${elem}"; then
                value=`resolve_proc_out_descriptor "${cmdline}" "${elem}"`
                DESERIALIZED_ARGS[$i]=${value}
            fi
            i=$((i+1))
        done
    }

    local cmdline=$1
    local processname=$2
    local proc_outdir=$3
    local generate_opts_funcname=$4
    local task_idx=$5

    # Call options generator (output stored into DESERIALIZED_ARGS)
    local proc_spec=${INITIAL_PROCESS_SPEC["${processname}"]}
    ${generate_opts_funcname} "${cmdline}" "${proc_spec}" "${processname}" "${proc_outdir}" "${task_idx}" || return 1

    # Resove descriptors for connected processes
    resolve_proc_out_descriptors "${cmdline}"

    # Obtain serialized args
    serialize_args_nameref "sargs_nr" "${DESERIALIZED_ARGS[@]}"
    echo "${sargs_nr}"
}

########
get_file_opts_for_process_and_task()
{
    local opts_fname=$1
    local task_idx=$2

    if [ -f "${opts_fname}" ]; then
        local line=$((task_idx + 1))
        get_nth_file_line "${opts_fname}" "${line}"
    else
        local block_number=$((task_idx / OPT_FILE_LINES_PER_BLOCK))
        local block_idx=$((task_idx % OPT_FILE_LINES_PER_BLOCK))
        local block_fname="${opts_fname}_${block_number}"

        local line=$((block_idx + 1))
        get_nth_file_line "${block_fname}" "${line}"
    fi
}

########
get_opts_for_process_and_task()
{
    local cmdline=$1
    local processname=$2
    local task_idx=$3

    if uses_option_generator "${processname}"; then
        local generate_opts_funcname=`get_generate_opts_funcname ${processname}`
        local proc_outdir=`get_process_outdir "${processname}"`
        gen_opts_for_process_and_task  "${cmdline}" "${processname}" "${proc_outdir}" "${generate_opts_funcname}" "${task_idx}"
    else
        local opts_fname=`get_sched_opts_fname_for_process "${PROGRAM_OUTDIR}" "${processname}"`
        get_file_opts_for_process_and_task "${opts_fname}" "${task_idx}"
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
#   define_opts_for_process <cmdline> <process_spec>
#
# The function does not return any value
define_opts_for_process()
{
    define_opts_loop()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`get_process_outdir "${processname}"`

        # Copy processname_def_opts function if necessary
        copy_process_defopts_func "${processname}"

        # Obtain define_opts function name and call it
        local define_opts_funcname=`get_define_opts_funcname ${processname}`
        ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1
    }

    define_opts_generator()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=`extract_processname_from_process_spec "${process_spec}"`
        local process_outdir=`get_process_outdir "${processname}"`

        # Check if process dependencies were pre-specified for all processes
        if [ "${ALL_PROCESS_DEPS_PRE_SPECIFIED}" -eq 0 ]; then
            # There are process dependencies to be determined, so it is
            # necessary to update output options information

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local generate_opts_funcname=`get_generate_opts_funcname ${processname}`
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Iterate over array tasks
            local task_idx
            for (( task_idx=0; task_idx<$array_size; task_idx++ )); do
                # Call option generator
                ${generate_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" "${task_idx}" || return 1

                # Update output options information
                get_output_opts_info "${processname}" "${task_idx}" "${DESERIALIZED_ARGS[@]}"
            done

            # Set option list length
            PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        else
            # There are no process dependencies to be determined, so it is
            # only necessary to update option list length

            # Obtain define_opts_array function name and call it
            local define_opts_generator_gen_opts_size_fname
            get_generate_opts_size_funcname "${processname}" define_opts_generator_gen_opts_size_fname
            local array_size=`${define_opts_generator_gen_opts_size_fname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}"`

            # Set option list length
            PROCESS_OPT_LIST_LEN[$processname]=${array_size}
        fi
    }

    # Initialize variables
    local cmdline=$1
    local process_spec=$2

    if uses_option_generator "$processname"; then
        define_opts_generator "${cmdline}" "${process_spec}"
    else
        define_opts_loop "${cmdline}" "${process_spec}"
    fi
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
get_prg_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base exec dir
    execdir=`get_prg_exec_dir_given_basedir "${dirname}"`

    echo "${execdir}/${processname}"
}

########
create_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    local execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`
    if [ ! -d "${execdir}" ]; then
        "${MKDIR}" -p "${execdir}" || return 1
    fi
}

########
get_script_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}"
}

########
get_process_stdout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    if [ "${opt_array_size}" -eq 1 ]; then
        echo "${execdir}/${processname}.${STDOUT_FEXT}"
    else
        echo "${execdir}/${processname}_${task_idx}.${STDOUT_FEXT}"
    fi
}

########
get_process_log_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}.${SCHED_LOG_FEXT}"
}

########
get_task_log_filename()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3

    # Get exec dir
    execdir=`get_prg_exec_dir_for_process "${dirname}" "${processname}"`

    echo "${execdir}/${processname}_${task_idx}.${SCHED_LOG_FEXT}"
}

########
get_process_schedout_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    if [ "${opt_array_size}" -eq 1 ]; then
        get_process_log_filename "${dirname}" "${processname}"
    else
        get_task_log_filename "${dirname}" "${processname}" "${task_idx}"
    fi
}

########
get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd="${PROGRAM_OUTDIR}"

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
            local cmdline=$1
            local processname=$2
            local num_tasks=$3
            local task_idx=$4
            declare -A depdict

            # Iterate over task options
            local opts=`get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
            deserialize_args "${opts}"
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
                            if [[ -v OUT_VALUE_TO_PROCESSES[${value}] ]]; then
                                # The value is generated as output by
                                # another process (or processes)

                                # Check if the value represents a FIFO
                                local augm_fifoname=`get_augm_fifoname_from_absname "${value}"`
                                if [[ -v PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                                    # The value represents a FIFO
                                    local proc_plus_idx=${PROGRAM_FIFOS["${augm_fifoname}"]}
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
                                    local processes="${OUT_VALUE_TO_PROCESSES[${value}]}"
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

        local cmdline=$1
        local processname=$2

        # Determine whether the process has multiple tasks
        local num_tasks=`get_numtasks_for_process "${processname}"`
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
    local processname=`extract_processname_from_process_spec "$process_spec"`

    # Check if process dependencies were already obtained
    if [[ -v PROCESS_DEPENDENCIES["$processname"] ]]; then
        echo "${PROCESS_DEPENDENCIES[$processname]}"
    else
        # Extract dependencies from process specification if given
        local deps=`extract_processdeps_from_process_spec "${process_spec}"`
        if [ "${deps}" = "${ATTR_NOT_FOUND}" ]; then
            # No dependencies are provided in specification
            local deps=`get_procdeps_for_process "${cmdline}" "$processname"`
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
        local cmdline=$1
        local processname=$2
        local num_tasks=$3
        local task_idx=$4

        # Iterate over task options
        local opts=`get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
        deserialize_args "${opts}"
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
                        if [[ -v PROGRAM_FIFOS["${augm_fifoname}"] ]]; then
                            # The value is a FIFO
                            local proc_plus_idx=${PROGRAM_FIFOS["${augm_fifoname}"]}
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
    local num_tasks=`get_numtasks_for_process "${processname}"`
    if [ "${num_tasks}" -eq 1 ]; then
        # The process has only one task
        register_fifos_used_by_process_task "${cmdline}" "${processname}" "${num_tasks}" 0
    else
        # The process is an array of tasks
        register_fifos_used_by_task_array "${cmdline}" "${processname}" "${num_tasks}"
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
            local owner=${PROGRAM_FIFOS["${augm_fifoname}"]}
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
    local outd=${PROGRAM_OUTDIR}

    get_process_outdir_given_dirname "${outd}" "${processname}"
}

########
get_adaptive_processname()
{
    local processname=$1

    # Get caller process name
    local caller_processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_GENERATE_OPTS}"`

    if [ -z "${caller_processname}" ]; then
        caller_processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    fi

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
    local outd=${PROGRAM_OUTDIR}

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
        echo "Warning: ${processname} output directory already exists but program was not finished or will be re-executed, directory content will be removed">&2
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
        "${RM}" -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
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
