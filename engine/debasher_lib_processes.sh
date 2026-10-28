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
debasher::_get_explain_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}"
}

########
debasher::_get_explain_task_shaping_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_TASK_SHAPING_OPTS}"
}

########
debasher::_get_identify_cmdline_opts_funcname()
{
    local processname=$1

    debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}"
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
# Calls the skip method of a process with the options of a task, and
# tells what the task does: a method that returns 0 skips the task, one
# that returns 1 lets it run, and any other status is a failure of the
# method, which fails the task rather than letting it run as if the
# method had decided so.
#
# $1 - Process name.
# $2 - Name of the skip method.
# $3,$4,...,$n - Options of the task.
#
# Returns 0 if the task is skipped, 1 if it runs, and 2, with an error,
# if the method failed.
debasher::_call_skip_method()
{
    local processname=$1
    local skip_funct=$2
    shift 2

    local skip_status=0
    "${skip_funct}" "$@" || skip_status=$?
    case ${skip_status} in
        0|1)
            return ${skip_status}
            ;;
        *)
            echo "Error: the skip method of process ${processname} failed with exit code ${skip_status}" >&2
            return 2
            ;;
    esac
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
    local funcname=$(debasher::_get_define_opts_funcname "${processname}")

    if debasher::_func_exists "${funcname}"; then
        return 0
    else
        return 1
    fi
}

########
debasher::_uses_option_generator()
{
    local processname=$1
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

        # Resolve descriptor; a process that does not exist has neither
        # an option generator nor a line of options
        local sargs
        sargs=$(debasher::_get_opts_for_process_and_task "${cmdline}" "${connected_proc}" "${connected_proc_task_idx}") || return 1
        debasher::_deserialize_args "${sargs}"
        value=$(debasher::_get_opt_value_from_func_args "${connected_proc_opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}")

        printf '%s\n' "${value}"
    }

    debasher::_resolve_proc_out_descriptors()
    {
        local cmdline=$1
        local processname=$2

        # Iterate over DEBASHER_DESERIALIZED_ARGS array
        local i=0
        while [ $i -lt ${#DEBASHER_DESERIALIZED_ARGS[@]} ]; do
            # Resolve process output descriptor if necessary, refusing a
            # connection that does not resolve
            local elem=${DEBASHER_DESERIALIZED_ARGS[$i]}
            if ! debasher::_str_is_option "${elem}" && debasher::_str_is_proc_out_opt_descriptor "${elem}"; then
                local opt=${DEBASHER_DESERIALIZED_ARGS[$((i-1))]}
                local value
                value=$(debasher::_resolve_proc_out_descriptor "${cmdline}" "${elem}") || return 1
                debasher::_check_connection_resolved "${processname}" "${opt}" "${elem}" "${value}" || return 1
                DEBASHER_DESERIALIZED_ARGS[$i]=${value}
            fi
            i=$((i+1))
        done
    }

    # Verifies that no option was given conflicting values once every
    # process-output descriptor has been resolved to a literal; options
    # repeated with an identical resolved value are silently collapsed.
    # WARNING: must run after DEBASHER_DESERIALIZED_ARGS no longer holds
    # any unresolved descriptor, and must not call any helper that
    # clobbers DEBASHER_DESERIALIZED_ARGS while still reading from it.
    debasher::_dedup_resolved_opts()
    {
        local processname=$1

        local -a tokens=("${DEBASHER_DESERIALIZED_ARGS[@]}")
        local -A opt_list
        local -a opt_order=()

        local i=0
        while [ $i -lt ${#tokens[@]} ]; do
            local elem=${tokens[$i]}

            if ! debasher::_str_is_option "${elem}"; then
                i=$((i+1))
                continue
            fi

            local opt=${elem}
            local value=${DEBASHER_VOID_VALUE}
            local next_idx=$((i+1))
            if [ $next_idx -lt ${#tokens[@]} ] && ! debasher::_str_is_option "${tokens[$next_idx]}"; then
                value=${tokens[$next_idx]}
                i=$((i+2))
            else
                i=$((i+1))
            fi

            [[ -v opt_list[${opt}] ]] || opt_order+=("${opt}")
            debasher::_merge_opt_value opt_list "${opt}" "${value}"
        done

        # Rebuild the deduplicated token list, failing if any option
        # ended up with more than one distinct resolved value
        local -a result=()
        local opt
        for opt in "${opt_order[@]}"; do
            debasher::_split_opt_multival "${opt_list[${opt}]}"
            local value
            value=$(debasher::_get_single_opt_value "${processname}" "${opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}") || return 1

            result+=("${opt}")
            [ "${value}" != "${DEBASHER_VOID_VALUE}" ] && result+=("${value}")
        done

        unset DEBASHER_DESERIALIZED_ARGS
        declare -ga DEBASHER_DESERIALIZED_ARGS
        DEBASHER_DESERIALIZED_ARGS=("${result[@]}")
    }

    local cmdline=$1
    local processname=$2
    local proc_outdir=$3
    local generate_opts_funcname=$4
    local task_idx=$5

    # Call options generator (output stored into DEBASHER_DESERIALIZED_ARGS)
    local proc_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]}
    debasher::_call_generate_opts "${generate_opts_funcname}" "${cmdline}" "${proc_spec}" "${processname}" "${proc_outdir}" "${task_idx}" || return 1

    # Resolve descriptors for connected processes
    debasher::_resolve_proc_out_descriptors "${cmdline}" "${processname}" || return 1

    # Ensure no option received conflicting values
    debasher::_dedup_resolved_opts "${processname}" || return 1

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
        local generate_opts_funcname=$(debasher::_get_generate_opts_funcname "${processname}")
        local proc_outdir=$(debasher::_get_process_outdir "${processname}")
        debasher::_gen_opts_for_process_and_task  "${cmdline}" "${processname}" "${proc_outdir}" "${generate_opts_funcname}" "${task_idx}"
    else
        local opts_fname=$(debasher::_get_sched_opts_fname_for_process "${processname}")
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
        local processname=$(debasher::_extract_processname_from_process_spec "${process_spec}")
        local process_outdir=$(debasher::_get_process_outdir "${processname}")

        # The number of tasks of the process is the number of option lists
        # that its _define_opts method registers, so it is being computed
        # while the method runs (see debasher::_check_num_tasks_chain)
        local DEBASHER_COMPUTING_NUM_TASKS="${DEBASHER_COMPUTING_NUM_TASKS:-} ${processname}"

        # Obtain define_opts function name and call it; a process without
        # an option generator needs the method
        local define_opts_funcname=$(debasher::_get_define_opts_funcname "${processname}")
        if [ "${define_opts_funcname}" = "${DEBASHER_FUNCT_NOT_FOUND}" ]; then
            echo "Error: process ${processname} has neither a ${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS} method nor an option generator (${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE} and ${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS})" >&2
            return 1
        fi
        ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1

        # A method that registered no task leaves zero tasks, so that a
        # process whose options are defined always has its number of tasks
        DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]=${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]:-0}
    }

    debasher::_define_opts_generator()
    {
        # Initialize variables
        local cmdline=$1
        local process_spec=$2
        local processname=$(debasher::_extract_processname_from_process_spec "${process_spec}")
        local process_outdir=$(debasher::_get_process_outdir "${processname}")

        # Obtain the generator function and the number of tasks
        local generate_opts_funcname=$(debasher::_get_generate_opts_funcname "${processname}")
        local array_size
        array_size=$(debasher::_compute_generator_num_tasks "${cmdline}" "${process_spec}" "${processname}") || return 1

        # Known from here on: a process that asks, through the generator,
        # for the number of tasks of this one finds it without computing
        # it again
        DEBASHER_PROCESS_OPT_LIST_LEN[$processname]=${array_size}

        # Iterate over array tasks. This is done even when all process
        # dependencies were given, as save_opt_list does for a process
        # without a generator: a fifo the generator defines with
        # define_fifo_opt_generator is registered as a side effect of
        # calling it in this shell, and the readers of that fifo are then
        # found through the output options information of its owner task
        local task_idx
        for (( task_idx=0; task_idx<$array_size; task_idx++ )); do
            # Call option generator
            debasher::_call_generate_opts "${generate_opts_funcname}" "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" "${task_idx}" || return 1

            # Update output options information
            debasher::_get_output_opts_info "${processname}" "${task_idx}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
        done
    }

    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local processname=$(debasher::_extract_processname_from_process_spec "${process_spec}")

    # The methods that define the options read the task shaping options
    # without defining them, so nothing else would stop a run that lacks
    # one
    debasher::_check_task_shaping_opts_given "${cmdline}" "${processname}" || return 1

    if debasher::_uses_option_generator "${processname}"; then
        debasher::_define_opts_generator "${cmdline}" "${process_spec}"
    else
        debasher::_define_opts_loop "${cmdline}" "${process_spec}"
    fi
}

########
# Defines the options of the given processes, in the given order. Keeps
# the command line while it runs, for get_process_num_tasks, which needs
# it to compute the number of tasks of a process not defined yet.
#
# $1 - Command line.
# $2... - Process names.
#
# Returns 1 if the options of some process cannot be defined.
debasher::_define_opts_for_processes()
{
    local cmdline=$1
    shift
    local DEBASHER_DEFINING_OPTS_CMDLINE=${cmdline}

    local processname
    for processname in "$@"; do
        local process_spec="${DEBASHER_INITIAL_PROCESS_SPEC[${processname}]}"
        debasher::_define_opts_for_process "${cmdline}" "${process_spec}" || { echo "Error: option not found for process ${processname}" >&2 ; return 1; }
    done
}

########
# Defines the options of every process of the program: first those of the
# processes without an option generator, then those of the processes with
# one. Any process can ask for the number of tasks of any other while its
# options are defined (see debasher::get_process_num_tasks), whatever the
# order; the order only spares computing again the number of tasks of the
# processes without an option generator, which the option generators
# usually ask for and which cost a whole _define_opts method each time.
#
# $1 - Command line.
#
# Returns 1 if the options of some process cannot be defined.
debasher::_define_opts_for_program_processes()
{
    local cmdline=$1

    local -a without_generator=() with_generator=()
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        if debasher::_uses_option_generator "${processname}"; then
            with_generator+=("${processname}")
        else
            without_generator+=("${processname}")
        fi
    done
    debasher::_define_opts_for_processes "${cmdline}" "${without_generator[@]}" || return 1
    debasher::_define_opts_for_processes "${cmdline}" "${with_generator[@]}"
}

########
# Fails if the number of tasks of process $1 is already being computed in
# the current call stack: DEBASHER_COMPUTING_NUM_TASKS holds the processes
# whose _define_opts or _generate_opts_size method is running, each added
# while its method runs. Asking for one of them again would recurse for
# ever, or, for a process whose method has registered some task already,
# give the number of tasks registered so far, so get_process_num_tasks
# checks it before anything else and stops the preparation instead.
#
# $1 - Process name.
#
# Returns 1 if the number of tasks of the process depends on itself.
debasher::_check_num_tasks_chain()
{
    local processname=$1

    case " ${DEBASHER_COMPUTING_NUM_TASKS:-} " in
        *" ${processname} "*)
            local chain="${DEBASHER_COMPUTING_NUM_TASKS# } ${processname}"
            echo "Error: the number of tasks of process ${processname} depends on itself (${chain// / -> })" >&2
            return 1
            ;;
    esac
}

########
# Prints the number of tasks of a process whose options are not defined
# yet, while the run is prepared: what the _generate_opts_size method of
# an option generator gives, or the number of option lists that the
# _define_opts method of a process without one registers. That method
# runs in a subshell, so that nothing it registers survives, and the
# process is defined once, for real, in its turn; the method thus runs
# again for every process that asks before that turn, and has to give the
# same number of tasks every time.
#
# $1 - Command line.
# $2 - Process name.
#
# Returns 1, printing nothing, if the number of tasks cannot be computed.
debasher::_compute_num_tasks()
{
    local cmdline=$1
    local processname=$2
    local process_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]}

    if debasher::_uses_option_generator "${processname}"; then
        debasher::_check_task_shaping_opts_given "${cmdline}" "${processname}" || return 1
        debasher::_compute_generator_num_tasks "${cmdline}" "${process_spec}" "${processname}"
    else
        (
            debasher::_define_opts_for_process "${cmdline}" "${process_spec}" || exit 1
            echo "${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}"
        ) || {
            echo "Error: get_process_num_tasks: the options of process ${processname} could not be defined" >&2
            return 1
        }
    fi
}

########
# Prints the number of tasks that the _generate_opts_size method of the
# option generator $3 gives, after checking that it succeeded and printed
# a number. The number of tasks of the process is being computed while
# the method runs (see debasher::_check_num_tasks_chain).
#
# $1 - Command line.
# $2 - Process specification of the process.
# $3 - Process name.
#
# Returns 1, printing nothing, if the number of tasks cannot be computed.
debasher::_compute_generator_num_tasks()
{
    local cmdline=$1
    local process_spec=$2
    local processname=$3

    local DEBASHER_COMPUTING_NUM_TASKS="${DEBASHER_COMPUTING_NUM_TASKS:-} ${processname}"

    local size_funcname
    debasher::_get_generate_opts_size_funcname "${processname}" size_funcname
    local process_outdir=$(debasher::_get_process_outdir "${processname}")
    local num_tasks
    num_tasks=$("${size_funcname}" "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}") || {
        echo "Error: the _generate_opts_size method of process ${processname} failed" >&2
        return 1
    }
    if [[ ! "${num_tasks}" =~ ^[0-9]+$ ]]; then
        echo "Error: the _generate_opts_size method of process ${processname} printed \"${num_tasks}\" instead of a number of tasks" >&2
        return 1
    fi
    echo "${num_tasks}"
}

########
# Populates the given associative array (passed by name) with the set
# of option names a process declares via explain_opts (or the legacy
# explain_cmdline_opts), leaving out its task shaping options. Mirrors
# the function resolution used to print command-line options (see
# debasher::_show_program_cmdline_opts).
#
# $1 - Process name.
# $2 - Name of an existing associative array to populate (opt name -> 1).
#
# Returns 1, leaving the array untouched, if the process defines
# neither method.
debasher::_get_explained_opt_names()
{
    local processname=$1
    local -n explained_opt_names_ref=$2

    local opts_funcname=$(debasher::_get_explain_cmdline_opts_funcname "${processname}")
    if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        opts_funcname=$(debasher::_get_explain_opts_funcname "${processname}")
    fi
    if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        return 1
    fi

    ${opts_funcname} || return 1

    local prefix="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    local key
    for key in "${!DEBASHER_PROGRAM_OPT_IS_TASK_OPT[@]}"; do
        case "${key}" in
            "${prefix}"*)
                explained_opt_names_ref["${key#${prefix}}"]=1
                ;;
        esac
    done
}

########
# Populates the given associative array (passed by name) with the set
# of task shaping option names a process declares via its
# explain_task_shaping_opts method, which it may not have.
#
# $1 - Process name.
# $2 - Name of an existing associative array to populate (opt name -> 1).
#
# Returns 1 if the method of the process fails.
debasher::_get_task_shaping_opt_names()
{
    local processname=$1
    local -n task_shaping_opt_names_ref=$2

    local funcname=$(debasher::_get_explain_task_shaping_opts_funcname "${processname}")
    if [ "${funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        return 0
    fi

    ${funcname} || return 1

    local prefix="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    local key
    for key in "${!DEBASHER_PROGRAM_OPT_IS_TASK_SHAPING[@]}"; do
        case "${key}" in
            "${prefix}"*)
                task_shaping_opt_names_ref["${key#${prefix}}"]=1
                ;;
        esac
    done
}

########
# Verifies that every task shaping option of a process is given on the
# command line. A task shaping option is always mandatory: its value
# fixes the tasks of the process, and through connections by task index
# how they meet the tasks of other processes, so two processes that
# read the same option with different defaults of their own would
# disagree on that structure.
#
# $1 - Command line.
# $2 - Process name.
#
# Returns 1 if some task shaping option is missing.
debasher::_check_task_shaping_opts_given()
{
    local cmdline=$1
    local processname=$2

    local -A task_shaping_opt_names=()
    debasher::_get_task_shaping_opt_names "${processname}" task_shaping_opt_names || return 1

    local missing=0
    local opt
    for opt in "${!task_shaping_opt_names[@]}"; do
        if ! debasher::_read_opt_value_from_line_memoiz "${cmdline}" "${opt}"; then
            echo "Error: process ${processname} needs the task shaping option ${opt}, which was not given on the command line" >&2
            missing=1
        fi
    done

    [ "${missing}" -eq 0 ]
}

########
# Populates the given associative array (passed by name) with the
# options actually produced for a process's first task (task_idx 0),
# each name mapped to its value (empty for a flag).
#
# For a process without an option generator, this reads the
# DEBASHER_OPT_LIST_<proc>_0 array that debasher::_define_opts_for_process
# already populated for real (save_opt_list only fills that array when
# it detects it is being called, transitively, from a *_define_opts
# function).
#
# For a process with an option generator, save_opt_list instead just
# leaves the raw, still-serialized option tokens in
# DEBASHER_DESERIALIZED_ARGS (it never populates DEBASHER_OPT_LIST_*
# for a *_generate_opts caller), so its generate_opts method is
# invoked once here, for task_idx 0 only (not at all for a process with
# no task, which has no options to compare), and the resulting tokens are
# walked the same way debasher::_generate_opt_list does (odd tokens
# are option names, the following token is their value unless it is
# itself an option, in which case the first is treated as a flag) to
# recover the options. This extra call is made inside a subshell so it
# is side-effect free (no stray FIFO registration, etc.) on the
# program's real scheduling state: only the resulting options are
# read back, as NUL-separated name/value pairs, so that a value may
# hold any character.
#
# $1 - Command line.
# $2 - Process name.
# $3 - Name of an existing associative array to populate (opt name ->
#      value).
debasher::_get_actual_opt_names_for_first_task()
{
    local cmdline=$1
    local processname=$2
    local -n actual_opt_names_ref=$3

    # A process with no task has no options to compare
    if [ "$(debasher::_get_numtasks_for_process "${processname}")" = 0 ]; then
        return 0
    fi

    if debasher::_uses_option_generator "${processname}"; then
        local generate_opts_funcname=$(debasher::_get_generate_opts_funcname "${processname}")
        local process_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]}
        local process_outdir=$(debasher::_get_process_outdir "${processname}")

        # The subshell ends with an end marker only when generate_opts
        # succeeded, so a failure is told apart from a task with no
        # options (a process substitution's own exit status is lost)
        local end_marker="__DEBASHER_END_OF_OPTS__"
        local -a fields=()
        mapfile -d '' -t fields < <(
            debasher::_call_generate_opts "${generate_opts_funcname}" "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" 0 >/dev/null || exit 1
            set -- "${DEBASHER_DESERIALIZED_ARGS[@]}"
            while [ $# -gt 0 ]; do
                local token="$1"
                if ! debasher::_str_is_option "${token}"; then
                    shift
                    continue
                fi
                shift
                local value=""
                if [ $# -gt 0 ] && ! debasher::_str_is_option "$1"; then
                    value="$1"
                    shift
                fi
                printf '%s\0%s\0' "${token}" "${value}"
            done
            printf '%s\0' "${end_marker}"
        )
        if [ "${#fields[@]}" -eq 0 ] || [ "${fields[-1]}" != "${end_marker}" ]; then
            return 1
        fi
        unset 'fields[-1]'

        local i
        for ((i = 0; i + 1 < ${#fields[@]}; i += 2)); do
            actual_opt_names_ref["${fields[i]}"]="${fields[i + 1]}"
        done
    else
        local opt_list_name=$(debasher::_get_opt_list_name "${processname}" 0)
        if declare -p "${opt_list_name}" >/dev/null 2>&1; then
            declare -n first_task_opt_list_ref="${opt_list_name}"
            local o
            for o in "${!first_task_opt_list_ref[@]}"; do
                actual_opt_names_ref["${o}"]="${first_task_opt_list_ref[${o}]}"
            done
        fi
    fi
}

########
# Fails when a task shaping option of the process is also declared in
# explain_opts, marked in identify_cmdline_opts or defined for its first
# task: a task shaping option is declared in explain_task_shaping_opts
# alone (it is always a mandatory command-line option already), and no
# task receives it.
#
# $1 - Process name.
# $2 - Name of the associative array of the options it declares.
# $3 - Name of the associative array of its task shaping options.
# $4 - Name of the associative array of the options of its first task.
debasher::_check_task_shaping_opts_declared_alone()
{
    local processname=$1
    local -n tsa_explained=$2
    local -n tsa_shaping=$3
    local -n tsa_actual=$4

    local status=0
    local opt
    for opt in "${!tsa_shaping[@]}"; do
        if [ -n "${tsa_explained[${opt}]+x}" ]; then
            echo "Error: process ${processname} declares option ${opt} both in its explain_opts and in its explain_task_shaping_opts; an option that its tasks receive is declared only in explain_opts" >&2
            status=1
        elif debasher::_opt_is_cmdline_for_process "${processname}" "${opt}"; then
            echo "Error: process ${processname} marks its task shaping option ${opt} in its identify_cmdline_opts; a task shaping option is always a mandatory command-line option, and is not marked" >&2
            status=1
        elif [ -n "${tsa_actual[${opt}]+x}" ]; then
            echo "Error: process ${processname} defines its task shaping option ${opt} for its first task; a task shaping option is only read by the methods that define the options, and no task receives it" >&2
            status=1
        fi
    done
    return "${status}"
}

########
# Fails when identify_cmdline_opts marks an option that explain_opts does
# not declare: it only classifies declared options, so the mark is a
# typo, which leaves the intended option unmarked, or a leftover. A
# marked task shaping option is reported by
# debasher::_check_task_shaping_opts_declared_alone.
#
# $1 - Process name.
# $2 - Name of the associative array of the options it declares.
# $3 - Name of the associative array of its task shaping options.
debasher::_check_marked_cmdline_opts_declared()
{
    local processname=$1
    local -n mcd_explained=$2
    local -n mcd_shaping=$3

    local status=0
    local prefix="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    local key opt
    for key in "${!DEBASHER_PROGRAM_OPT_IS_CMDLINE[@]}"; do
        case "${key}" in
            "${prefix}"*) ;;
            *) continue ;;
        esac
        opt="${key#"${prefix}"}"
        [ -n "${mcd_shaping[${opt}]+x}" ] && continue
        if [ -z "${mcd_explained[${opt}]+x}" ]; then
            echo "Error: process ${processname} marks option ${opt} in its identify_cmdline_opts, but does not declare it in its explain_opts" >&2
            status=1
        fi
    done
    return "${status}"
}

########
# Fails when the first task of the process defines an option that
# explain_opts does not declare, typically a typo or a name that drifted
# out of sync with explain_opts, or a command-line option with a value
# that does not come from the command line (see
# debasher::_cmdline_opt_value_is_from_cmdline): a command-line option
# can only be defined from it. A process whose number of "-foo0",
# "-foo1", ... options depends on a run-time value declares the whole
# family once, as "-foo-ith" (see debasher::_actual_opt_is_ith_instance
# and dispatch_define_opts in debasher_dynamic_fanout.sh). A defined
# task shaping option is reported by
# debasher::_check_task_shaping_opts_declared_alone.
#
# $1 - Command line.
# $2 - Process name.
# $3 - Name of the associative array of the options it declares.
# $4 - Name of the associative array of its task shaping options.
# $5 - Name of the associative array of the options of its first task.
debasher::_check_defined_opts_declared()
{
    local cmdline=$1
    local processname=$2
    local -n dod_explained=$3
    local -n dod_shaping=$4
    local -n dod_actual=$5

    local status=0
    local opt
    for opt in "${!dod_actual[@]}"; do
        [ -n "${dod_shaping[${opt}]+x}" ] && continue
        if [ -z "${dod_explained[${opt}]+x}" ]; then
            debasher::_actual_opt_is_ith_instance "${opt}" "$3" && continue
            echo "Error: process ${processname} defines option ${opt}, which is not declared in its explain_opts" >&2
            status=1
            continue
        fi
        if debasher::_opt_is_cmdline_for_process "${processname}" "${opt}" \
                && ! debasher::_cmdline_opt_value_is_from_cmdline "${cmdline}" "${opt}" "${dod_actual[${opt}]}"; then
            echo "Error: process ${processname} defines command-line option ${opt} with a value that does not come from the command line; a command-line option can only be defined from it (define_cmdline_opt and similar)" >&2
            status=1
        fi
    done
    return "${status}"
}

########
# Warns about the options that the process declares but its first task
# does not define: some are legitimately conditional, defined only when
# given on the command line, so their absence from one task is not an
# error. No warning is given for a command-line option that is optional
# or a flag; the one for a mandatory command-line option suggests a task
# shaping option, the only legitimate reason for that absence.
#
# $1 - Process name.
# $2 - Name of the associative array of the options it declares.
# $3 - Name of the associative array of the options of its first task.
debasher::_warn_declared_opts_not_defined()
{
    local processname=$1
    local -n don_explained=$2
    local -n don_actual=$3

    local opt
    for opt in "${!don_explained[@]}"; do
        [ -n "${don_actual[${opt}]+x}" ] && continue
        debasher::_ith_family_has_instance "${opt}" "$3" && continue
        if debasher::_opt_is_cmdline_for_process "${processname}" "${opt}"; then
            debasher::_opt_is_mandatory_valued_for_process "${processname}" "${opt}" || continue
            echo "Warning: process ${processname} declares mandatory command-line option ${opt} in explain_opts, but it was not found among the options generated for its first task; an option that only the methods that define the options read is declared in ${processname}${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_TASK_SHAPING_OPTS} instead" >&2
            continue
        fi
        echo "Warning: process ${processname} declares option ${opt} in explain_opts, but it was not found among the options generated for its first task" >&2
    done
}

########
# Sanity check: verifies, for every process, that the option names that
# its first task defines agree with those it declares, one rule each:
# its task shaping options are declared alone
# (debasher::_check_task_shaping_opts_declared_alone), what
# identify_cmdline_opts marks is declared
# (debasher::_check_marked_cmdline_opts_declared), what the task defines
# is declared and a command-line option comes from the command line
# (debasher::_check_defined_opts_declared), and a declared option that
# the task lacks gives a warning (debasher::_warn_declared_opts_not_defined).
#
# $1 - Command line.
#
# Returns 1 if some process breaks one of the rules.
debasher::_check_opt_names_vs_explain()
{
    local cmdline=$1

    local had_undeclared_opt=0
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local -A explained_opt_names=()
        debasher::_get_explained_opt_names "${processname}" explained_opt_names || continue
        local -A task_shaping_opt_names=()
        debasher::_get_task_shaping_opt_names "${processname}" task_shaping_opt_names || return 1
        debasher::_mark_identified_cmdline_opts "${processname}" || return 1

        local -A actual_opt_names=()
        debasher::_get_actual_opt_names_for_first_task "${cmdline}" "${processname}" actual_opt_names || return 1

        debasher::_check_task_shaping_opts_declared_alone "${processname}" explained_opt_names task_shaping_opt_names actual_opt_names || had_undeclared_opt=1
        debasher::_check_marked_cmdline_opts_declared "${processname}" explained_opt_names task_shaping_opt_names || had_undeclared_opt=1
        debasher::_check_defined_opts_declared "${cmdline}" "${processname}" explained_opt_names task_shaping_opt_names actual_opt_names || had_undeclared_opt=1
        debasher::_warn_declared_opts_not_defined "${processname}" explained_opt_names actual_opt_names
    done

    [ "${had_undeclared_opt}" -eq 0 ]
}

########
# Runs the process's identify_cmdline_opts method, if it has one, so
# that the options it marks as command-line options are known
# (DEBASHER_PROGRAM_OPT_IS_CMDLINE): an ordinary run never calls that
# method otherwise.
#
# $1 - Process name.
debasher::_mark_identified_cmdline_opts()
{
    local processname=$1

    local funcname=$(debasher::_get_identify_cmdline_opts_funcname "${processname}")
    if [ "${funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        return 0
    fi
    ${funcname}
}

########
# True if the process marks the option as a command-line option in its
# identify_cmdline_opts.
#
# $1 - Process name.
# $2 - Option name.
debasher::_opt_is_cmdline_for_process()
{
    local processname=$1
    local opt=$2

    local proc_opt=${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    [ "${DEBASHER_PROGRAM_OPT_IS_CMDLINE[${proc_opt}]}" = 1 ]
}

########
# True if the process declares the option as a mandatory one with a
# value, as opposed to an optional option or a flag, which a task may
# legitimately lack.
#
# $1 - Process name.
# $2 - Option name.
debasher::_opt_is_mandatory_valued_for_process()
{
    local processname=$1
    local opt=$2

    local proc_opt=${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    [ "${DEBASHER_PROGRAM_OPT_IS_MANDATORY[${proc_opt}]}" = 1 ] && [ -n "${DEBASHER_PROGRAM_OPT_TYPE[${proc_opt}]}" ]
}

########
# True if a command-line option defined for a task holds the value that
# the define_cmdline_* functions give it: the value given on the command
# line, or its absolute path (define_cmdline_infile_opt[_if_given] and
# define_cmdline_indir_opt[_if_given]), or no value at all for a flag
# given on the command line. False when the option was not given on the
# command line (so its value must have come from somewhere else) or
# holds a different value.
#
# $1 - Command line.
# $2 - Option name.
# $3 - Value the option holds in the task (empty for a flag).
debasher::_cmdline_opt_value_is_from_cmdline()
{
    local cmdline=$1
    local opt=$2
    local actual_value=$3

    debasher::_check_opt_given_memoiz "${cmdline}" "${opt}" || return 1

    # Given with no value: a flag
    if ! debasher::_read_opt_value_from_line_memoiz "${cmdline}" "${opt}"; then
        [ -z "${actual_value}" ] || [ "${actual_value}" = "${DEBASHER_VOID_VALUE}" ]
        return
    fi
    local given_value="${_OPT_VALUE_}"

    [ "${actual_value}" = "${given_value}" ] && return 0
    [ "${actual_value}" = "$(debasher::_get_absolute_path "${given_value}")" ]
}

########
# Prints the name of the fanout family of which actual_opt_name (e.g.
# "-outf3") would be an instance, as the process declares it once:
# "<prefix>-ith" (e.g. "-outf-ith"). See
# debasher::_check_opt_names_vs_explain's own comment for why this
# convention exists.
#
# $1 - Actual option name.
#
# Returns 1 if the option name does not end in a number.
debasher::_ith_family_name_for()
{
    local actual_opt_name=$1

    [[ "${actual_opt_name}" =~ ^(.+[^0-9])[0-9]+$ ]] || return 1
    echo "${BASH_REMATCH[1]}-ith"
}

########
# True if actual_opt_name (e.g. "-outf3") is an instance of a fanout family
# that the process declares in explained_opt_names.
#
# $1 - Actual option name.
# $2 - Name of an associative array of explained option names.
debasher::_actual_opt_is_ith_instance()
{
    local actual_opt_name=$1
    local -n ith_explained_ref=$2

    local family
    family=$(debasher::_ith_family_name_for "${actual_opt_name}") || return 1
    [ -n "${ith_explained_ref[${family}]+x}" ]
}

########
# True if some name in actual_opt_names (e.g. "-outf3") is an instance of
# the fanout family that explained_opt_name declares (e.g.
# explained_opt_name "-outf-ith" matches actual "-outf3", "-outf0", ...).
#
# $1 - Explained option name.
# $2 - Name of an associative array of actual option names.
debasher::_ith_family_has_instance()
{
    local explained_opt_name=$1
    local -n ith_actual_ref=$2

    [[ "${explained_opt_name}" == *-ith ]] || return 1

    local a a_family
    for a in "${!ith_actual_ref[@]}"; do
        a_family=$(debasher::_ith_family_name_for "${a}") || continue
        [ "${a_family}" = "${explained_opt_name}" ] && return 0
    done
    return 1
}

########
debasher::_get_prg_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base exec dir
    execdir=$(debasher::get_prg_exec_dir_given_basedir "${dirname}")

    echo "${execdir}/${processname}"
}

########
debasher::_create_exec_dir_for_process()
{
    local dirname=$1
    local processname=$2

    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")
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
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

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
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    if [ "${opt_array_size}" -eq 1 ]; then
        echo "${execdir}/${processname}.${DEBASHER_STDOUT_FEXT}"
    else
        echo "${execdir}/${processname}_${task_idx}.${DEBASHER_STDOUT_FEXT}"
    fi
}

########
debasher::_get_process_opts_filename()
{
    local dirname=$1
    local processname=$2
    local opt_array_size=$3
    local task_idx=$4

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    if [ "${opt_array_size}" -eq 1 ]; then
        echo "${execdir}/${processname}.${DEBASHER_OPTS_FEXT}"
    else
        echo "${execdir}/${processname}_${task_idx}.${DEBASHER_OPTS_FEXT}"
    fi
}

########
debasher::_get_process_log_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    echo "${execdir}/${processname}.${DEBASHER_SCHED_LOG_FEXT}"
}

########
debasher::_get_task_log_filename()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

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
    process_function_outdir=$(debasher::_get_outdir_funcname "${processname}")

    if [ "${process_function_outdir}" = "${DEBASHER_FUNCT_NOT_FOUND}" ]; then
        debasher::_get_default_process_outdir_given_dirname "$dirname" "$processname"
    else
        local outdir_basename=$("${process_function_outdir}")
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
    local processname=$(debasher::_extract_processname_from_process_spec "${process_spec}")
    local process_outd=$(debasher::_get_process_outdir_given_dirname ${outd} "${processname}")

    echo ${process_outd}
}

########
# Creates the output directory of a process if it does not exist. What an
# earlier run left in it is not removed here: a task that is not skipped
# resets it before it runs, with the _reset_outfiles method of its process
# or the default reset (see debasher::_default_reset_outfiles_for_process)
debasher::_create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=$(debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}")

    "${MKDIR}" -p "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
}

########
debasher::_default_reset_outfiles_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=$(debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}")

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        # Everything goes, including the entries whose name starts with a
        # dot, such as value descriptors
        "${FIND}" "${outd}" -mindepth 1 -maxdepth 1 -exec "${RM}" -rf -- {} + || { echo "Error! could not clear output directory" >&2; return 1; }
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
    echo "Process started at $(debasher::_now_datetime_ms)" >&2
}

########
debasher::_display_end_process_message()
{
    echo "Process finished at $(debasher::_now_datetime_ms)" >&2
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

########
debasher::list_proc_names()
{
    while IFS= read -r func; do
        case "$func" in
            *"$DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS")
                echo "${func%"$DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS"}"
                ;;
            *"$DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS")
                echo "${func%"$DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS"}"
                ;;
        esac
    done < <(declare -F | "${AWK}" '{print $3}')
}
