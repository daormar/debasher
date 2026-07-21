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

# *- bash -*

# INCLUDE BASH LIBRARIES
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_builtin_sched_lib || exit 1

#############
# CONSTANTS #
#############

MAX_NUM_PROCESS_OPTS_TO_DISPLAY=10
REEXEC_PROCESSES_LIST_FNAME=".reexec_processes_due_to_deps.txt"
WAIT_FOR_PROCESSES_SLEEP_TIME_SHORT=5
WAIT_FOR_PROCESSES_SLEEP_TIME_LONG=10

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store process ids
declare -A PIPE_EXEC_PROCESS_IDS

#############################
# OPTION HANDLING FUNCTIONS #
#############################

########
print_desc()
{
    echo "debasher_exec executes general purpose programs"
    echo "type \"debasher_exec --help\" to get usage information"
}

########
usage()
{
    echo "debasher_exec             --pfile <string> --outdir <string> [--sched <string>]"
    echo "                          [--builtinsched-cpus <int>] [--builtinsched-mem <int>]"
    echo "                          [--dflt-nodes <string>] [--dflt-throttle <string>]"
    echo "                          [--reexec-outdated-procs] [--conda-support]"
    echo "                          [--docker-support] [--gen-proc-graph]"
    echo "                          [--show-cmdline-opts|--check-proc-opts|--debug]"
    echo "                          [--wait] [--builtinsched-debug] [--version] [--help]"
    echo ""
    echo "--pfile <string>          File with program processes to be executed (see"
    echo "                          manual for additional information)"
    echo "--outdir <string>         Output directory"
    echo "--sched <string>          Scheduler used to execute the program (if not given,"
    echo "                          it is determined using information gathered during"
    echo "                          package configuration)"
    echo "--builtinsched-cpus <int> Available CPUs for built-in scheduler (${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} by default)."
    echo "                          A value of ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} means unlimited CPUs"
    echo "--builtinsched-mem <int>  Available memory in MB for built-in scheduler"
    echo "                          (${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} by default). A value of ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} means unlimited memory"
    echo "--dflt-nodes <string>     Default set of nodes used to execute the program"
    echo "--dflt-throttle <string>  Default task throttle used when executing job arrays"
    echo "--reexec-outdated-procs   Reexecute those processes with outdated code"
    echo "--conda-support           Enable conda support"
    echo "--docker-support          Enable docker support"
    echo "--gen-proc-graph          Generate process graph"
    echo "--show-cmdline-opts       Show command line options for the program"
    echo "--check-proc-opts         Check process options"
    echo "--debug                   Do everything except launching program processes"
    echo "--wait                    Wait until all processes finish. This option has"
    echo "                          no effect when using the BUILTIN scheduler since it"
    echo "                          waits by its own design"
    echo "--builtinsched-debug      Show debug information for built-in scheduler"
    echo "--version                 Display version information and exit"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    pfile_given=0
    outdir_given=0
    sched_given=0
    builtin_sched_cpus_given=0
    builtin_sched_cpus=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    builtin_sched_mem_given=0
    builtin_sched_mem=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    dflt_nodes_given=0
    dflt_throttle_given=0
    reexec_outdated_processes_given=0
    conda_support_given=0
    docker_support_given=0
    gen_proc_graph_given=0
    show_cmdline_opts_given=0
    check_proc_opts_given=0
    debug=0
    wait=0
    builtin_sched_debug=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--version") debasher::debasher_version
                         exit 1
                         ;;
            "--pfile") shift
                  if [ $# -ne 0 ]; then
                      pfile=$1
                      pfile_given=1
                  fi
                  ;;
            "--outdir") shift
                  if [ $# -ne 0 ]; then
                      outd=$1
                      outdir_given=1
                  fi
                  ;;
            "--sched") shift
                  if [ $# -ne 0 ]; then
                      sched_opt=$1
                      sched_given=1
                  fi
                  ;;
            "--builtinsched-cpus") shift
                  if [ $# -ne 0 ]; then
                      builtin_sched_cpus=$1
                      if ! debasher::_str_is_natural_number ${builtin_sched_cpus}; then
                          echo "Value for --builtinsched_cpus option should be a natural number" >&2
                          return 1
                      fi
                      builtin_sched_cpus_given=1
                  fi
                  ;;
            "--builtinsched-mem") shift
                  if [ $# -ne 0 ]; then
                      builtin_sched_mem=$1
                      builtin_sched_mem=`debasher::_convert_mem_value_to_mb ${builtin_sched_mem}` || { echo "Invalid memory specification for --builtinsched_mem option}" >&2; return 1; }
                      if ! debasher::_str_is_natural_number ${builtin_sched_mem}; then
                          echo "Value for --builtinsched_mem option should be a natural number" >&2
                          return 1
                      fi
                      builtin_sched_mem_given=1
                  fi
                  ;;
            "--dflt-nodes") shift
                  if [ $# -ne 0 ]; then
                      dflt_nodes=$1
                      dflt_nodes_given=1
                  fi
                  ;;
            "--dflt-throttle") shift
                  if [ $# -ne 0 ]; then
                      dflt_throttle=$1
                      dflt_throttle_given=1
                  fi
                  ;;
            "--reexec-outdated-procs")
                  if [ $# -ne 0 ]; then
                      reexec_outdated_processes_given=1
                  fi
                  ;;
            "--conda-support")
                  if [ $# -ne 0 ]; then
                      conda_support_given=1
                  fi
                  ;;
            "--docker-support")
                  if [ $# -ne 0 ]; then
                      docker_support_given=1
                  fi
                  ;;
            "--gen-proc-graph")
                  if [ $# -ne 0 ]; then
                      gen_proc_graph_given=1
                  fi
                  ;;
            "--show-cmdline-opts") show_cmdline_opts_given=1
                          ;;
            "--check-proc-opts") check_proc_opts_given=1
                           ;;
            "--debug") debug=1
                       ;;
            "--wait") wait=1
                       ;;
            "--builtinsched-debug") builtin_sched_debug=1
                                    ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${pfile_given} -eq 0 ]; then
        echo "Error! --pfile parameter not given!" >&2
        exit 1
    else
        if [ ! -f "${pfile}" ]; then
            echo "Error! file ${pfile} does not exist" >&2
            exit 1
        else
            # Absolutize file path
            pfile=`debasher::_get_absolute_path "${pfile}"`
        fi
    fi

    if [ ${outdir_given} -eq 0 ]; then
        echo "Error! --outdir parameter not given!" >&2
        exit 1
    else
        if [ -d "${outd}" ]; then
            echo "Warning! output directory does exist" >&2
        fi
    fi

    if [ ${show_cmdline_opts_given} -eq 1 -a ${check_proc_opts_given} -eq 1 ]; then
        echo "Error! --show-cmdline-opts and --check-proc-opts options cannot be given simultaneously"
        exit 1
    fi

    if [ ${show_cmdline_opts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --show-cmdline-opts and --debug options cannot be given simultaneously"
        exit 1
    fi

    if [ ${check_proc_opts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --check-proc-opts and --debug options cannot be given simultaneously"
        exit 1
    fi
}

####################################
# GENERAL PIPE EXECUTION FUNCTIONS #
####################################

load_module()
{
    echo "# Loading module ($pfile)..." >&2

    # Load debasher module containing the program to be executed
    debasher::load_debasher_module "${pfile}" || exit 1

    echo "" >&2
}

########
get_deblib_vars_and_funcs()
{
    echo "# Extracting DeBasher variables and functions..." >&2

    local vars_and_funcs_fname=`debasher::_get_deblib_vars_and_funcs_fname "${outd}"`
    "${debasher_libexecdir}"/debasher_get_deblib_vars_and_funcs > "${vars_and_funcs_fname}" 2> "${vars_and_funcs_fname}".log

    echo "Extraction complete" >&2

    echo "" >&2
}

########
get_mod_vars_and_funcs()
{
    echo "# Extracting module variables and functions..." >&2

    local vars_and_funcs_fname=`debasher::_get_mod_vars_and_funcs_fname "${outd}"`

    # Get variables and functions from program modules
    "${debasher_libexecdir}"/debasher_get_vars_and_funcs "${DEBASHER_PROGRAM_MODULES[@]}" > "${vars_and_funcs_fname}" 2> "${vars_and_funcs_fname}".log

    # Get newly created process functions
    debasher::_get_newly_created_process_funcs >> "${vars_and_funcs_fname}"

    echo "Extraction complete" >&2

    echo "" >&2
}

########
ensure_program_not_being_executed()
{
    local initial_procspec_file=$1

    if [ -f "${initial_procspec_file}" ]; then
        if there_are_in_progress_processes "${outd}" "${initial_procspec_file}"; then
            echo "Error: this program has processes being executed. Please use debasher_status or debasher_stop tools to interact with the program. The execution of debasher_exec will be aborted" >&2
            exit 1
        fi
    fi
}

########
gen_initial_procspec_file()
{
    echo "# Generating initial process specification from $pfile..." >&2

    debasher::_exec_program_func_for_module "${pfile}" || exit 1

    echo "Generation complete" >&2

    echo "" >&2
}

########
check_procspec()
{
    local prefix_of_prg_files=$1

    echo "# Checking process specification..." >&2

    "${debasher_libexecdir}"/debasher_check_prg_files -p "${prefix_of_prg_files}" || return 1

    echo "Checking complete" >&2

    echo "" >&2
}

########
gen_process_graph()
{
    local prefix_of_prg_files=$1
    local procgraph_file_prefix=$2

    echo "# Generating process graph..." >&2

    "${debasher_libexecdir}"/debasher_check_prg_files -p "${prefix_of_prg_files}" -a > "${procgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" || return 1

    if [ -z "${DOT}" ]; then
        echo "Warning: Graphviz is not installed, so the process graph in pdf format won't be generated" >&2
    else
        "${DOT}" -T pdf "${procgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" > "${procgraph_file_prefix}.pdf"

        "${DOT}" -T eps "${procgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" > "${procgraph_file_prefix}.eps"
    fi

    echo "Generation complete" >&2

    echo "" >&2
}

########
gen_dependency_graph()
{
    local prefix_of_prg_files=$1
    local depgraph_file_prefix=$2

    echo "# Generating dependency graph..." >&2

    "${debasher_libexecdir}"/debasher_check_prg_files -p "${prefix_of_prg_files}" -g > "${depgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" || return 1

    if [ -z "${DOT}" ]; then
        echo "Warning: Graphviz is not installed, so the process graph in pdf format won't be generated" >&2
    else
        "${DOT}" -T pdf "${depgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" > "${depgraph_file_prefix}.pdf"

        "${DOT}" -T eps "${depgraph_file_prefix}.${DEBASHER_GRAPHS_FEXT}" > "${depgraph_file_prefix}.eps"
    fi

    echo "Generation complete" >&2

    echo "" >&2
}

########
gen_final_procspec_file()
{
    local cmdline=$1
    local initial_procspec_file=$2

    echo "# Generating final process specification file..." >&2

    # Iterate over process specifications
    while read process_spec; do
        # Extract process information
        local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

        # Extract dependencies from process specification
        local procdeps=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`

        # Check if dependencies were given
        if [ "${procdeps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # Dependencies not given, so they should be obtained
            procdeps=`debasher::_get_procdeps_for_process_cached "${cmdline}" "${process_spec}"`

            # Print process specification plus process dependencies
            debasher::_add_additional_spec "${process_spec}" "${procdeps}"
        else
            # Since the dependencies were given, just print process
            # specification
            echo "${process_spec}"
        fi

    done < "${initial_procspec_file}"

    echo "Generation complete" >&2

    echo "" >&2
}

########
configure_scheduler()
{
    echo "# Configuring scheduler..." >&2
    echo "" >&2

    if [ ${sched_given} -eq 1 ]; then
        echo "## Setting scheduler type from value of \"--sched\" option..." >&2
        debasher::_set_debasher_scheduler "${sched_opt}" || return 1
        echo "scheduler: ${sched_opt}" >&2
        echo "" >&2
    else
        # If --sched option not given, the scheduler is first determined
        # based on information gathered during package configuration
        # (see debasher::_determine_scheduler function in debasher_lib.sh). Once the
        # scheduler is determined, it will be set using the
        # debasher::_set_debasher_scheduler function
        echo "## Scheduler was not specified using \"--sched\" option, it will be automatically determined..." >&2
        local sched=`debasher::_determine_scheduler`
        debasher::_set_debasher_scheduler "${sched}" || return 1
        echo "scheduler: ${sched}" >&2
        echo "" >&2
    fi

    if [ ${dflt_nodes_given} -eq 1 ]; then
        echo "## Setting default nodes for program execution... (${dflt_nodes})" >&2
        debasher::_set_debasher_default_nodes "${dflt_nodes}" || return 1
        echo "" >&2
    fi

    if [ ${dflt_throttle_given} -eq 1 ]; then
        echo "## Setting default job array task throttle... (${dflt_throttle})" >&2
        debasher::_set_debasher_default_array_task_throttle "${dflt_throttle}" || return 1
        echo "" >&2
    fi
}

########
show_cmdline_opts()
{
    echo "# Command line options for the program..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        # Extract process information
        local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
        local explain_cmdline_opts_funcname=`debasher::_get_explain_cmdline_opts_funcname ${processname}`
        DIFFERENTIAL_CMDLINE_OPT_STR=""
        ${explain_cmdline_opts_funcname} || exit 1
        debasher::_update_opt_to_process_map "${processname}" "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    done < "${procspec_file}"

    # Print options
    debasher::_print_program_opts

    echo "" >&2
}

########
check_process_opts()
{
    get_initial_process_spec_info()
    {
        local procspec_file=$1

        while read process_spec; do
            # Store process specification
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
            DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]=${process_spec}

            # Extract dependencies from process specification
            local procdeps=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`

            # Check if dependencies were given
            DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED=1
            if [ "${procdeps}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
                DEBASHER_ALL_PROCESS_DEPS_PRE_SPECIFIED=0
            fi
        done < "${procspec_file}"
    }

    init_option_info()
    {
        local cmdline=$1
        local procspec_file=$2

        while read process_spec; do
            # Define options for process
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
            debasher::_define_opts_for_process "${cmdline}" "${process_spec}" || { echo "Error: option not found for process ${processname}" >&2 ; return 1; }
        done < "${procspec_file}"
    }

    create_option_arrays()
    {
        local cmdline=$1
        local dirname=$2
        local procspec_file=$3

        while read process_spec; do
            # Get process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            if ! debasher::_uses_option_generator "${processname}"; then
                # Load current option list
                debasher::_load_curr_opt_list_loop "${cmdline}" "${processname}"

                # Write option array to file (line by line)
                local opt_array_size=${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}
                local opts_fname=`debasher::_get_sched_opts_fname_for_process "${dirname}" "${processname}"`
                debasher::_write_opt_array "DEBASHER_CURRENT_PROCESS_OPT_LIST" "${opt_array_size}" "${opts_fname}"

                # Clear variables
                debasher::_clear_curr_opt_list_array
            fi
        done < "${procspec_file}"
    }

    print_exh_opt_list_procs()
    {
        local cmdline=$1
        local procspec_file=$2

        while read process_spec; do
            # Get process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            debasher::_show_curr_opt_list "${cmdline}" "${processname}"
        done < "${procspec_file}"
    }

    show_process_opts()
    {
        local cmdline=$1
        local procspec_file=$2
        local max_num_proc_opts_to_display=$3

        while read process_spec; do
            # Get process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Store process options in an array for visualization
            local serial_process_opts=`debasher::_get_serial_process_opts "${cmdline}" "${processname}" "${max_num_proc_opts_to_display}"`

            # Print info about options
            echo "PROCESS: ${processname} ; OPTIONS: ${serial_process_opts} ${ellipsis}" >&2
            echo "PROCESS: ${processname} ; OPTIONS: ${serial_process_opts} ${ellipsis}"
        done < "${procspec_file}"
    }

    register_fifo_users()
    {
        local cmdline=$1
        local procspec_file=$2

        if debasher::_program_uses_fifos; then
            while read process_spec; do
                # Extract process information
                local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

                # Register fifos
                debasher::_register_fifos_used_by_process "${cmdline}" "${processname}"
            done < "${procspec_file}"
        fi
    }

    echo "# Checking process options..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3
    local out_opts_file=$4
    local old_out_opts_file=$5
    local out_opts_exh_file=$6
    local out_fifos_file=$7

    # Clear scheduler options directory
    local sched_opts_dir=`debasher::get_sched_opts_dir_given_basedir "${dirname}"`
    "${RM}" -f "${sched_opts_dir}"/*

    # Get initial process specification information
    get_initial_process_spec_info "${procspec_file}" || return 1

    # Initialize option information
    init_option_info "${cmdline}" "${procspec_file}" || return 1

    # Create option arrays
    create_option_arrays "${cmdline}" "${dirname}" "${procspec_file}" || return 1

    # Print exhaustive option list for processes (only if process graph
    # should be generated)
    if [ "${gen_proc_graph_given}" -eq 1 ]; then
        print_exh_opt_list_procs "${cmdline}" "${procspec_file}" > "${out_opts_exh_file}" || return 1
    fi

    # Store old process options if they exist
    if [ -f "${out_opts_file}" ]; then
        "${MV}" "${out_opts_file}" "${old_out_opts_file}"
    fi

    # Show process options
    show_process_opts "${cmdline}" "${procspec_file}" "${MAX_NUM_PROCESS_OPTS_TO_DISPLAY}" > "${out_opts_file}" || return 1

    # Register fifo users
    register_fifo_users "${cmdline}" "${procspec_file}" || return 1

    # Print info about fifos
    debasher::_show_program_fifos > "${out_fifos_file}" || return 1

    echo "" >&2
}

########
handle_conda_requirements()
{
    echo "# Handling conda requirements (if any)..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Process conda envs information
            local conda_envs_funcname=`debasher::_get_conda_envs_funcname "${processname}"`
            if debasher::_func_exists ${conda_envs_funcname}; then
                echo "Handling conda requirements for process ${processname}..." >&2
                ${conda_envs_funcname} || exit 1
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Handling complete" >&2

    echo "" >&2
}

########
handle_docker_requirements()
{
    echo "# Handling docker requirements (if any)..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Process conda envs information
            local docker_imgs_funcname=`debasher::_get_docker_imgs_funcname "${processname}"`
            if debasher::_func_exists "${docker_imgs_funcname}"; then
                echo "Handling docker requirements for process ${processname}..." >&2
                "${docker_imgs_funcname}" || exit 1
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Handling complete" >&2

    echo "" >&2
}

########
define_reexec_processes_due_to_input_changes()
{
    echo "# Defining processes to be reexecuted due to changes in input parameters..." >&2

    # Read input parameters
    local program_opts_file=$1
    local prev_program_opts_file=$2

    # Obtain processes with input change
    local changed_procs
    changed_procs=`"${debasher_libexecdir}"/debasher_compare_opts --changed "${old_program_opts_file}" "${program_opts_file}" 2>/dev/null`

    # Iterate processes with input change
    while IFS= read -r proc; do
        [ -z "$proc" ] && continue
        debasher::_mark_process_as_reexec "${proc}" "${DEBASHER_INPUT_CHANGE_REEXEC_REASON}"
    done <<< "${changed_procs}"

    # Obtain new processes
    local new_procs
    new_procs=`"${debasher_libexecdir}"/debasher_compare_opts --new "${old_program_opts_file}" "${program_opts_file}" 2>/dev/null`

    # Iterate over new processes
    while IFS= read -r proc; do
        [ -z "$proc" ] && continue
        debasher::_mark_process_as_reexec "${proc}" "${DEBASHER_NEW_PROC_REEXEC_REASON}"
    done <<< "${new_procs}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_reexec_processes_due_to_fifos()
{
    echo "# Defining processes to be reexecuted due to usage of fifos (if any)..." >&2

    # Read input parameters
    local dirname=$1
    local procspec_file=$2

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Get fifo owners for process
            local fifo_owners=`debasher::_get_fifo_owners_for_process "${processname}"`

            # Get status for process
            local status=`debasher::_get_process_status "${dirname}" "${processname}"`

            # Mark process and fifo owners for reexecution
            if [ -n "${fifo_owners}" ]; then
                if [ "${status}" = "${DEBASHER_TODO_PROCESS_EXIT_CODE}" ] \
                       || [ "${status}" = "${DEBASHER_UNFINISHED_PROCESS_STATUS}" ] \
                       || [ "${status}" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ] ; then
                    debasher::_mark_process_as_reexec "${processname}" "${DEBASHER_FIFO_REEXEC_REASON}"
                    while read -r fifo_owner; do
                        debasher::_mark_process_as_reexec "${fifo_owner}" "${DEBASHER_FIFO_REEXEC_REASON}"
                    done <<< "${fifo_owners}"
                fi
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_forced_reexec_processes()
{
    echo "# Defining processes forced to be reexecuted (if any)..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
            local process_forced=`debasher::_extract_force_from_process_spec "$process_spec" "force"`
            if [ ${process_forced} = "yes" ]; then
                debasher::_mark_process_as_reexec $processname ${DEBASHER_FORCED_REEXEC_REASON}
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
check_script_is_older_than_modules()
{
    local script_filename=$1

    # Check if script exists
    if [ -f "${script_filename}" ]; then
        # script exists
        script_older=0
        local mod
        for mod in "${!DEBASHER_PROGRAM_MODULES[@]}"; do
            fullmod="${DEBASHER_PROGRAM_MODULES[$mod]}"
            if [ "${script_filename}" -ot "${fullmod}" ]; then
                script_older=1
                echo "Warning: ${script_filename} is older than module ${fullmod}" >&2
            fi
        done
        # Return value
        if [ "${script_older}" -eq 1 ]; then
            return 0
        else
            return 1
        fi
    else
        # script does not exist
        echo "Warning: ${script_filename} does not exist" >&2
        return 0
    fi
}

########
define_reexec_processes_due_to_code_update()
{
    echo "# Defining processes to be reexecuted due to code updates (if any)..." >&2

    # Read input parameters
    local dirname=$1
    local procspec_file=$2

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`
            local status=`debasher::_get_process_status "${dirname}" "${processname}"`
            local script_filename=`debasher::_get_script_filename "${dirname}" "${processname}"`

            # Handle checkings depending of process status
            if [ "${status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]; then
                if check_script_is_older_than_modules "${script_filename}"; then
                    echo "Warning: last execution of process ${processname} used outdated modules">&2
                    debasher::_mark_process_as_reexec "$processname" "${DEBASHER_OUTDATED_CODE_REEXEC_REASON}"
                fi
            fi

            if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
                if check_script_is_older_than_modules "${script_filename}"; then
                    echo "Warning: current execution of process ${processname} is using outdated modules">&2
                fi
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_reexec_processes_due_to_deps()
{
    echo "# Defining processes to be reexecuted due to dependencies (if any)..." >&2

    local prg_file_pref=$1

    # Obtain list of processes to be reexecuted due to dependencies
    local reexec_processes_string=`debasher::_get_reexec_processes_as_string`
    local reexec_processes_file="${outd}/${REEXEC_PROCESSES_LIST_FNAME}"
    "${debasher_libexecdir}"/db_get_reexec_procs_due_to_deps -r "${reexec_processes_string}" -p "${prg_file_pref}" > "${reexec_processes_file}" || return 1

    # Read information about the processes to be re-executed due to
    # dependencies
    local processname
    while read processname; do
        if [ "${processname}" != "" ]; then
            debasher::_mark_process_as_reexec "$processname" "${DEBASHER_DEPS_REEXEC_REASON}"
        fi
    done < "${reexec_processes_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
print_reexec_processes()
{
    local reexec_processes_string=`debasher::_get_reexec_processes_as_string`

    if [ ! -z "${reexec_processes_string}" ]; then
        echo "# Printing list of processes to be reexecuted..." >&2
        echo "${reexec_processes_string}" >&2
        echo "${DEBASHER_DEBASHER_REEXEC_PROCESSES_WARNING}" >&2
        echo "" >&2
    fi
}

########
release_lock()
{
    local fd=$1
    local file=$2

    # Release the lock
    "$FLOCK" -u "$fd" || return 1

    # Try to acquire the lock again in non-blocking mode to safely remove the file
    if "$FLOCK" -xn "$fd"; then
        "$RM" -f "$file" || return 1
    fi
}

########
prepare_lock()
{
    local -n fd_ref=$1   # nameref: caller variable
    local file=$2

    exec {fd_ref}>"$file" || return 1   # Bash assigns free fd, stores it in fd_ref
    trap "release_lock $fd_ref '$file'" EXIT
}

########
ensure_exclusive_execution()
{
    local outd=$1
    local lockfile="${outd}/lock"

    prepare_lock LOCKFD "$lockfile" || return 1
    "$FLOCK" -xn "$LOCKFD" || return 1
}

########
set_debasher_output_dir()
{
    echo "# Setting DeBasher output directory (the directory will be created if necessary)..." >&2

    # Create directory
    if [ ! -d "${outd}" ]; then
        "${MKDIR}" -p "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi

    # Get absolute file path (very important so as to ensure correct
    # execution of processes)
    outd=`debasher::_get_absolute_path "${outd}"`

    # Set outd as the output directory of debasher
    debasher::_set_debasher_outdir "${outd}"

    echo "" >&2
}

########
create_basic_dirs()
{
    echo "# Creating basic directories..." >&2

    local execdir=`debasher::_get_prg_exec_dir`
    "${MKDIR}" -p "${execdir}" || { echo "Error! cannot create exec directory" >&2; return 1; }

    local sched_opts_dir=`debasher::_get_sched_opts_dir`
    "${MKDIR}" -p "${sched_opts_dir}" || { echo "Error! cannot create scheduler options directory" >&2; return 1; }

    local graphsdir=`debasher::_get_prg_graphs_dir`
    "${MKDIR}" -p "${graphsdir}" || { echo "Error! cannot create graphs directory" >&2; return 1; }

    local fifodir=`debasher::_get_absolute_fifodir`
    "${MKDIR}" -p "${fifodir}" || { echo "Error! cannot create fifos directory" >&2; return 1; }

    local condadir=`debasher::_get_absolute_condadir`
    if [ ${conda_support_given} -eq 1 ]; then
        "${MKDIR}" -p "${condadir}"
    fi

    echo "Creation complete" >&2

    echo "" >&2
}

########
create_mod_shared_dirs()
{
    echo "# Creating shared directories for modules... (if any)" >&2

    # Create shared directories required by the program processes
    # IMPORTANT NOTE: the following functions can only be executed after
    # loading program modules
    debasher::_register_module_program_shdirs
    debasher::_create_mod_shdirs

    debasher::_show_program_shdirs >&2

    echo "Creation complete" >&2

    echo "" >&2
}

########
print_command_line()
{
    echo "cd $PWD" > "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
    debasher::_sep_serialized_to_qstr "${DEBASHER_ARG_SEP}" "${command_line}" >> "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
    echo "" >> "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
}

########
get_processdeps_from_detailed_spec()
{
    local processdeps_spec=$1
    local pdeps=""

    # Iterate over the elements of the process specification: type1:processname1,...,typen:processnamen or type1:processname1?...?typen:processnamen
    local separator=`debasher::_get_processdeps_separator ${processdeps_spec}`
    if [ "${separator}" = "" ]; then
        local processdeps_spec_blanks=${processdeps_spec}
    else
        local processdeps_spec_blanks=`debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps_spec}`
    fi
    local dep_spec
    for dep_spec in ${processdeps_spec_blanks}; do
        local deptype=`debasher::_get_deptype_part_in_dep ${dep_spec}`
        local mapped_deptype=`debasher::_map_deptype_if_necessary ${deptype}`
        local processname=`debasher::_get_processname_part_in_dep ${dep_spec}`
        # Check if there is an id for the process
        if [ ! -z "${PIPE_EXEC_PROCESS_IDS[${processname}]}" ]; then
            if [ -z "${pdeps}" ]; then
                pdeps=${mapped_deptype}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${PIPE_EXEC_PROCESS_IDS[${processname}]}
            else
                pdeps=${pdeps}"${separator}"${mapped_deptype}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${PIPE_EXEC_PROCESS_IDS[${processname}]}
            fi
        fi
    done

    echo ${pdeps}
}

########
get_processdeps()
{
    local process_id_list=$1
    local processdeps_spec=$2
    case ${processdeps_spec} in
            "${DEBASHER_AFTEROK_PROCESSDEP_TYPE}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}all") debasher::_apply_deptype_to_processids "${process_id_list}" "${DEBASHER_AFTEROK_PROCESSDEP_TYPE}"
                    ;;
            "none") echo ""
                    ;;
            *) get_processdeps_from_detailed_spec "${processdeps_spec}"
               ;;
    esac
}

########
prepare_files_and_dirs_for_processes()
{
    echo "# Preparing files and directories for processes..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            prepare_files_and_dirs_for_process "${cmdline}" "${dirname}" "${processname}" "${process_spec}"
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Preparation complete" >&2

    echo "" >&2
}

########
prepare_files_and_dirs_for_process()
{
    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local process_spec=$4

    echo "Preparing files and directories for process ${processname}" >&2

    # Obtain process status
    local status=`debasher::_get_process_status ${dirname} "${processname}"`

    # Decide whether the process should be executed (NOTE: for a
    # process that should not be executed, files and directories are
    # still prepared)
    if [ "${status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" -a "${status}" != "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        # Obtain array size
        local array_size=`debasher::_get_numtasks_for_process "${processname}"`

        # Prepare files and directories for process
        if [ "${status}" = "${DEBASHER_TODO_PROCESS_STATUS}" ]; then
            debasher::_create_exec_dir_for_process "${dirname}" "${processname}" || { echo "Error when creating exec directory for process" >&2 ; return 1; }
            debasher::_create_shdirs_owned_by_process "${processname}" || { echo "Error when creating shared directories determined by script option definition" >&2 ; return 1; }
            debasher::_create_outdir_for_process "${dirname}" "${processname}" || { echo "Error when creating output directory for process" >&2 ; return 1; }
        else
            debasher::_clean_process_files "${dirname}" "${processname}" "${array_size}" || { echo "Error when cleaning files for process" >&2 ; return 1; }
        fi
        debasher::_prepare_fifos_owned_by_process "${processname}"
    fi
}

########
revise_reexec_proc_status()
{
    echo "# Revise process status for processes to be reexecuted..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Get process status
            local status=`debasher::_get_process_status ${dirname} "${processname}"`

            # If process is marked as reexec and it was finished, its process completion is reset
            if debasher::_process_marked_as_reexec ${processname} && [ "${status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]; then
                debasher::_reset_process_completion_signal "${dirname}" "${processname}" || { echo "Error when resetting process completion signal for process" >&2 ; return 1; }
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "Revision complete" >&2

    echo "" >&2
}

########
launch_process()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local process_spec=$4

    # Execute process

    # Obtain process status
    local status=`debasher::_get_process_status ${dirname} "${processname}"`
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    # Decide whether the process should be executed
    if [ "${status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" -a "${status}" != "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        # Create script
        local opt_array_size=`debasher::_get_numtasks_for_process "${processname}"`
        debasher::_create_script "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}"

        # Launch process
        local task_array_list=`debasher::_get_task_array_list "${dirname}" "${processname}" "${opt_array_size}"`
        local processdeps_spec=`debasher::_extract_processdeps_from_process_spec "${process_spec}"`
        local processdeps=`get_processdeps "${process_id_list}" "${processdeps_spec}"`
        debasher::_launch "${dirname}" "${processname}" "${opt_array_size}" "${task_array_list}" "${process_spec}" "${processdeps}" "launch_outvar" || { echo "Error while launching process!" >&2 ; return 1; }

        # Update variables storing id information
        local primary_id=`debasher::_get_primary_id "${launch_outvar}"`
        PIPE_EXEC_PROCESS_IDS[${processname}]=${primary_id}
        process_id_list="${process_id_list}:${PIPE_EXEC_PROCESS_IDS[${processname}]}"

        # Write id to file
        debasher::_write_process_id_info_to_file "${dirname}" "${processname}" "${launch_outvar}"
    else
        # If process is in progress, its id should be retrieved so as to
        # correctly express dependencies
        if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
            local sid_info=`debasher::_read_process_id_info_from_file "${dirname}" "${processname}"` || { echo "Error while retrieving id of in-progress process" >&2 ; return 1; }
            local global_id=`debasher::_get_global_id "${sid_info}"`
            PIPE_EXEC_PROCESS_IDS["${processname}"]=${global_id}
            process_id_list="${process_id_list}:${PIPE_EXEC_PROCESS_IDS[${processname}]}"
        fi
    fi
}

########
launch_processes()
{
    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            launch_process "${cmdline}" "${dirname}" "${processname}" "${process_spec}" || return 1
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"
}

########
launch_program_processes()
{
    echo "# Launching program processes..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # process_id_list will store the process ids of the program
    # processes (it should be defined as a global variable)
    process_id_list=""

    # Launch processes
    launch_processes "${cmdline}" "${dirname}" "${procspec_file}"

    echo "" >&2
}

########
there_are_in_progress_processes()
{
    # Read input parameters
    local dirname=$1
    local initial_procspec_file=$2

    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            # Obtain process status
            local status=`debasher::_get_process_status ${dirname} "${processname}"`

            if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
                return 0
            fi
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${initial_procspec_file}"

    return 1
}

########
wait_for_program_processes()
{
    echo "# Waiting for program processes to finish..." >&2

    # Read input parameters
    local dirname=$1
    local procspec_file=$2

    # Obtain number of processes
    local num_procs=$("${WC}" -l "${procspec_file}" | "${AWK}" '{print $1}')

    while there_are_in_progress_processes "${dirname}" "${procspec_file}"; do
        if [ "${num_procs}" -le 10 ]; then
            "${SLEEP}" "${WAIT_FOR_PROCESSES_SLEEP_TIME_SHORT}"
        else
            "${SLEEP}" "${WAIT_FOR_PROCESSES_SLEEP_TIME_LONG}"
        fi
    done

    echo "Waiting complete" >&2

    echo "" >&2
}

########
debug_process()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local process_spec=$4

    # Debug process

    # Obtain process status
    local status=`debasher::_get_process_status "${dirname}" "${processname}"`
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2
}

########
launch_program_processes_debug()
{
    echo "# Launching program processes... (debug mode)" >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # process_id_list will store the process ids of the program
    # processes (it should be defined as a global variable)
    process_id_list=""

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if debasher::_program_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`debasher::_extract_processname_from_process_spec "$process_spec"`

            debug_process "${cmdline}" "${dirname}" "${processname}" "${process_spec}" || return 1
        else
            echo "Error: process specification (${process_spec}) is not correct" >&2
            exit 1
        fi
    done < "${procspec_file}"

    echo "" >&2
}

########
print_post_exec_wait_help()
{
    echo "Program execution finished, possible next steps:" >&2
    echo "- Inspect program execution status:" >&2
    echo "debasher_status -d <outdir>" >&2
    echo "- Get standard output for a process:"  >&2
    echo "debasher_get_stdout -d <outdir> -p <process_name>" >&2
    echo "- Get scheduler output for a process (useful for debugging):"  >&2
    echo "debasher_get_sched_out -d <outdir> -p <process_name>" >&2
    echo "" >&2
}

########
print_post_exec_nowait_help()
{
    echo "Program execution started, possible next steps:" >&2
    echo "- Inspect program execution status:" >&2
    echo "debasher_status -d <outdir>" >&2
    echo "- Get standard output for a process:"
    echo "debasher_get_stdout -d <outdir> -p <process_name>" >&2
    echo "- Get scheduler output for a process (useful for debugging):"
    echo "debasher_get_sched_out -d <outdir> -p <process_name>" >&2
    echo "" >&2
}

#################
# MAIN FUNCTION #
#################

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

# Save command line
command_line=`debasher::_serialize_args "$0" "$@"`

read_pars "$@" || exit 1

check_pars || exit 1

set_debasher_output_dir || exit 1

create_basic_dirs || exit 1

configure_scheduler || exit 1

load_module || exit 1

# Get name of initial process specification file
initial_procspec_file="${outd}/${DEBASHER_PPEXEC_INITIAL_PROCSPEC_BASENAME}"

# Remove initial process specification file if it exists
if [ -f "${initial_procspec_file}" ]; then
    rm "${initial_procspec_file}"
fi

# Write initial process specification file
gen_initial_procspec_file > "${initial_procspec_file}" || exit 1

# Check if there are running processes and abort execution if true
ensure_program_not_being_executed "${initial_procspec_file}"

# Write debasher library variables and functions
get_deblib_vars_and_funcs || exit 1

# Write module variables and functions (this function should be called
# after calling gen_initial_procspec_file, since it executes the program
# given in pfile input parameter, possibly defining new functions that
# should be written as well)
get_mod_vars_and_funcs || exit 1

if [ ${show_cmdline_opts_given} -eq 1 ]; then
    show_cmdline_opts "${initial_procspec_file}" || exit 1
else
    prg_file_pref="${outd}/${DEBASHER_PPEXEC_PRG_PREF}"
    program_opts_file="${prg_file_pref}.${DEBASHER_PRGOPTS_FEXT}"
    old_program_opts_file="${prg_file_pref}.${DEBASHER_PRGOPTS_OLD_FEXT}"
    program_opts_exh_file="${prg_file_pref}.${DEBASHER_PRGOPTS_EXHAUSTIVE_FEXT}"
    program_fifos_file="${prg_file_pref}.${DEBASHER_FIFOS_FEXT}"
    prg_graphs_dir=`debasher::_get_prg_graphs_dir`
    procgraph_file_prefix="${prg_graphs_dir}/process_graph"
    depgraph_file_prefix="${prg_graphs_dir}/dependency_graph"

    if [ ${check_proc_opts_given} -eq 1 ]; then
        check_process_opts "${command_line}" "${outd}" "${initial_procspec_file}" "${program_opts_file}" "${old_program_opts_file}" \
                           "${program_opts_exh_file}" "${program_fifos_file}" || exit 1
    else
        check_process_opts "${command_line}" "${outd}" "${initial_procspec_file}" "${program_opts_file}" "${old_program_opts_file}" \
                           "${program_opts_exh_file}" "${program_fifos_file}" || exit 1

        procspec_file="${prg_file_pref}.${DEBASHER_PROCSPEC_FEXT}"
        gen_final_procspec_file "${command_line}" "${initial_procspec_file}" > "${procspec_file}" || exit 1

        check_procspec "${prg_file_pref}" || exit 1

        if [ "${gen_proc_graph_given}" -eq 1 ]; then
            gen_process_graph "${prg_file_pref}" "${procgraph_file_prefix}" || exit 1
        fi

        gen_dependency_graph "${prg_file_pref}" "${depgraph_file_prefix}" || exit 1

        # NOTE: exclusive execution should be ensured after creating the output directory
        ensure_exclusive_execution "${outd}" || { echo "Error: there was a problem while trying to ensure exclusive execution of pipe_exec" ; exit 1; }

        create_mod_shared_dirs || exit 1

        if [ ${conda_support_given} -eq 1 ]; then
            handle_conda_requirements "${procspec_file}" || exit 1
        fi

        if [ ${docker_support_given} -eq 1 ]; then
            handle_docker_requirements "${procspec_file}" || exit 1
        fi

        define_reexec_processes_due_to_input_changes "${program_opts_file}" "${old_program_opts_file}" || exit 1

        define_reexec_processes_due_to_fifos "${outd}" "${procspec_file}" || exit 1

        define_forced_reexec_processes "${procspec_file}" || exit 1

        if [ ${reexec_outdated_processes_given} -eq 1 ]; then
            define_reexec_processes_due_to_code_update "${outd}" "${procspec_file}" || exit 1
        fi

        define_reexec_processes_due_to_deps "${prg_file_pref}" || exit 1

        print_reexec_processes || exit 1

        print_command_line || exit 1

        if [ ${debug} -eq 1 ]; then
            launch_program_processes_debug "${command_line}" "${outd}" "${procspec_file}" || exit 1

            # Restore program options file
            "${CP}" "${old_program_opts_file}" "${program_opts_file}"
        else
            sched=`debasher::_determine_scheduler`
            if [ ${sched} = ${DEBASHER_BUILTIN_SCHEDULER} ]; then
                debasher_builtin_sched::execute_program_processes "${command_line}" "${outd}" "${procspec_file}" "${builtin_sched_cpus}" "${builtin_sched_mem}" || exit 1
                print_post_exec_wait_help
            else
                revise_reexec_proc_status "${command_line}" "${outd}" "${procspec_file}" || return 1
                prepare_files_and_dirs_for_processes "${command_line}" "${outd}" "${procspec_file}"
                launch_program_processes "${command_line}" "${outd}" "${procspec_file}" || exit 1
                if [ "${wait}" -eq 1 ]; then
                    wait_for_program_processes "${outd}" "${procspec_file}" || exit 1
                    print_post_exec_wait_help
                else
                    print_post_exec_nowait_help
                fi
            fi
        fi
    fi
fi
