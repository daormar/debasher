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

# *- bash -*

# INCLUDE BASH LIBRARIES
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_builtin_sched_lib || exit 1

#############
# CONSTANTS #
#############

DB_EXEC_MAX_NUM_PROCESS_OPTS_TO_DISPLAY=10
DB_EXEC_WAIT_FOR_PROCESSES_SLEEP_TIME_SHORT=5
DB_EXEC_WAIT_FOR_PROCESSES_SLEEP_TIME_LONG=10

####################
# GLOBAL VARIABLES #
####################

# Declare associative array to store process ids
declare -A DB_EXEC_PROCESS_IDS

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
    echo "                          [--builtinsched-oneshot]"
    echo "                          [--dflt-nodes <string>] [--dflt-throttle <string>]"
    echo "                          [--rerun-outdated-procs] [--conda-support]"
    echo "                          [--docker-support] [--gen-proc-graph]"
    echo "                          [--show-cmdline-opts|--check-proc-opts|--validate]"
    echo "                          [--wait] [--builtinsched-debug] [--version] [--help]"
    echo ""
    echo "--pfile <string>          File with program processes to be executed (see"
    echo "                          manual for additional information); a relative path"
    echo "                          is looked for in the current directory and then in"
    echo "                          the directories of DEBASHER_MOD_DIR"
    echo "--outdir <string>         Output directory"
    echo "--sched <string>          Scheduler used to execute the program (if not given,"
    echo "                          SLURM when sbatch is found in the PATH, BUILTIN"
    echo "                          otherwise)"
    echo "--builtinsched-cpus <int> Available CPUs for built-in scheduler (${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} by default)."
    echo "                          A value of ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} means unlimited CPUs"
    echo "--builtinsched-mem <int>  Available memory in MB for built-in scheduler"
    echo "                          (${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} by default). A value of ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} means unlimited memory"
    echo "--builtinsched-oneshot    Launch all processes in a single scheduling iteration and"
    echo "                          return immediately, without waiting for them to finish."
    echo "                          Only valid with the built-in scheduler, enough cpus and"
    echo "                          memory to launch every process at once, and a program"
    echo "                          whose processes have no explicit dependencies between"
    echo "                          them (pure FIFO-based programs)"
    echo "--dflt-nodes <string>     Default set of nodes used to execute the program"
    echo "--dflt-throttle <string>  Default task throttle used when executing job arrays"
    echo "--rerun-outdated-procs    Rerun those processes with outdated code"
    echo "--conda-support           Enable conda support"
    echo "--docker-support          Enable docker support"
    echo "--gen-proc-graph          Generate process graph"
    echo "--show-cmdline-opts       Show command line options for the program"
    echo "--check-proc-opts         Check process options"
    echo "--validate                Do everything except launching program processes,"
    echo "                          and check that the resources of each process fit"
    echo "                          the limits of the built-in scheduler"
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
    builtin_sched_oneshot_given=0
    dflt_nodes_given=0
    dflt_throttle_given=0
    rerun_outdated_processes_given=0
    conda_support_given=0
    docker_support_given=0
    gen_proc_graph_given=0
    show_cmdline_opts_given=0
    check_proc_opts_given=0
    validate=0
    wait=0
    builtin_sched_debug=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 0
                      ;;
            "--version") debasher::debasher_version
                         exit 0
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
                      if [ "${builtin_sched_cpus}" != "${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}" ] && ! debasher::_str_is_positive_integer "${builtin_sched_cpus}"; then
                          echo "Value for --builtinsched-cpus option should be a positive integer, or ${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS} for unlimited cpus" >&2
                          return 1
                      fi
                      builtin_sched_cpus_given=1
                  fi
                  ;;
            "--builtinsched-mem") shift
                  if [ $# -ne 0 ]; then
                      builtin_sched_mem=$1
                      if [ "${builtin_sched_mem}" != "${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}" ]; then
                          builtin_sched_mem=$(debasher::_convert_mem_value_to_mb "${builtin_sched_mem}") || { echo "Invalid memory specification for --builtinsched-mem option" >&2; return 1; }
                          if ! debasher::_str_is_positive_integer "${builtin_sched_mem}"; then
                              echo "Value for --builtinsched-mem option should be a positive amount of memory, or ${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM} for unlimited memory" >&2
                              return 1
                          fi
                      fi
                      builtin_sched_mem_given=1
                  fi
                  ;;
            "--builtinsched-oneshot")
                  if [ $# -ne 0 ]; then
                      builtin_sched_oneshot_given=1
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
            "--rerun-outdated-procs")
                  if [ $# -ne 0 ]; then
                      rerun_outdated_processes_given=1
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
            "--validate") validate=1
                          ;;
            # An unknown option would be taken for an option of the program,
            # and a script that still asks for the dry run of --debug would
            # launch the program instead
            "--debug") echo "Error! --debug was renamed --validate" >&2
                       exit 1
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
        # Resolve the program file to an absolute path (it may be found
        # through DEBASHER_MOD_DIR)
        pfile=$(debasher::_resolve_pfile "${pfile}") || exit 1
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

    if [ ${show_cmdline_opts_given} -eq 1 -a ${validate} -eq 1 ]; then
        echo "Error! --show-cmdline-opts and --validate options cannot be given simultaneously"
        exit 1
    fi

    if [ ${check_proc_opts_given} -eq 1 -a ${validate} -eq 1 ]; then
        echo "Error! --check-proc-opts and --validate options cannot be given simultaneously"
        exit 1
    fi
}

#######################################
# GENERAL PROGRAM EXECUTION FUNCTIONS #
#######################################

load_module()
{
    echo "# Loading module ($pfile)..." >&2

    local pfile=$1

    # Load debasher module containing the program to be executed
    debasher::load_debasher_module "${pfile}" || exit 1

    echo "" >&2
}

########
write_exec_context()
{
    echo "# Writing the context of the process scripts..." >&2

    local outd=$1

    debasher::_write_exec_context "$(debasher::_get_exec_context_fname "${outd}")" || { echo "Error: the context of the process scripts could not be written" >&2; return 1; }

    echo "" >&2
}

########
# A fifo carries its data through the kernel of the machine where it is
# opened, not through the filesystem that holds its name, even a shared
# one: its two ends only meet when they run on the same machine, which
# nothing makes the jobs of Slurm do. A program that uses fifos is
# therefore refused on Slurm, instead of hanging with each end of a fifo
# waiting for the other.
ensure_scheduler_supports_fifos()
{
    if [ "$(debasher::_get_scheduler)" = "${DEBASHER_SLURM_SCHEDULER}" ] && debasher::_program_uses_fifos; then
        echo "Error: this program uses fifos, which cannot be run with the ${DEBASHER_SLURM_SCHEDULER} scheduler (the two ends of a fifo only meet when they run on the same machine); use --sched ${DEBASHER_BUILTIN_SCHEDULER} instead" >&2
        return 1
    fi
}

########
ensure_program_not_being_executed()
{
    if there_are_in_progress_processes "${outd}"; then
        echo "Error: this program has processes being executed. Please use debasher_status or debasher_stop tools to interact with the program. The execution of debasher_exec will be aborted" >&2
        exit 1
    fi
}

########
initialize_procspec()
{
    echo "# Initialize process specification..." >&2

    local pfile=$1

    debasher::_resolve_program_type "${pfile}" || exit 1

    debasher::_exec_program_func_for_module "${pfile}" || exit 1

    echo "Initialization complete" >&2

    echo "" >&2
}

########
# A "resident" program (long-running, stateful processes, see
# to_do_fbp.md) only ever runs under the built-in scheduler, in
# oneshot mode: debasher_exec launches every process and returns
# immediately rather than waiting for them to finish, since they are
# not expected to ever finish on their own. This is forced here,
# rather than left for the caller (frontend or otherwise) to remember
# to pass --builtinsched-oneshot/--sched BUILTIN, so the behavior is
# correct regardless of how debasher_exec is invoked.
enforce_resident_program_scheduling()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        return 0
    fi

    echo "# Program type is '${DEBASHER_PROGRAM_TYPE_RESIDENT}': forcing the built-in scheduler in oneshot mode..." >&2

    if [ ${sched_given} -eq 1 ] && [ "${sched_opt}" != "${DEBASHER_BUILTIN_SCHEDULER}" ]; then
        echo "Error! a '${DEBASHER_PROGRAM_TYPE_RESIDENT}' program only supports the built-in scheduler (requested: ${sched_opt})" >&2
        return 1
    fi

    # Resource limits (--builtinsched-cpus/--builtinsched-mem) are not
    # forced to be unrestricted here: a resident program is free to use
    # them like any other. Since oneshot mode never waits for a process
    # to finish (see debasher_builtin_sched::execute_program_processes),
    # it cannot correct course if not everything fits in one round: that
    # case is instead detected there and aborted before anything gets
    # launched, rather than silently launching only a subset.
    debasher::_set_debasher_scheduler "${DEBASHER_BUILTIN_SCHEDULER}" || return 1
    builtin_sched_oneshot_given=1

    echo "" >&2
}

########
# The command line saved in the output directory (see print_command_line)
# is where the tools that operate on it later (debasher_status,
# debasher_stop, debasher_stats, ...) learn which scheduler the program
# runs with. When --sched was not given, the scheduler in use was chosen
# here (the default of the machine, or the one forced for the program
# type), so it is added to the saved command line: otherwise those tools
# would have to work it out again, and would not necessarily get the same
# answer.
record_effective_scheduler_in_command_line()
{
    local sched=$(debasher::_get_scheduler)
    if [ -z "${sched}" ]; then
        return 0
    fi

    command_line=$(debasher::_add_sched_to_serialized_cmdline "${command_line}" "${sched}")
}

########
gen_final_procspec()
{
    echo "# Generate final process specification..." >&2

    local command_line=$1

    debasher::_gen_final_procspec "${command_line}" || exit 1

    debasher::_print_final_procspec "${command_line}" || exit 1

    echo "Generation complete" >&2

    echo "" >&2
}

########
topologically_sort_processes()
{
    echo "# Topologically sorting processes according to their dependencies..." >&2

    debasher::_topo_sort_processes

    echo "Sorting complete" >&2

    echo "" >&2
}

########
check_oneshot_precondition()
{
    # Dependencies of type "after" only require the depended-on process to
    # have started (not finished), so they are compatible with
    # --builtinsched-oneshot: the builtin scheduler resolves them without
    # waiting, by repeatedly launching newly-startable processes until none
    # are left, all within the same call and without sleeping. Dependencies
    # of type afterok/afternotok/afterany/aftercorr require a process to
    # have actually finished (or failed), which cannot be guaranteed without
    # waiting, so they are incompatible with this mode.

    is_blocking_deptype()
    {
        local deptype=$1

        case ${deptype} in
            "${DEBASHER_AFTER_PROCESSDEP_TYPE}"|"${DEBASHER_NONE_PROCESSDEP_TYPE}")
                return 1
                ;;
            *)
                return 0
                ;;
        esac
    }

    get_first_blocking_deptype()
    {
        local processdeps_spec=$1

        local separator=$(debasher::_get_processdeps_separator ${processdeps_spec})
        local processdeps_spec_blanks
        if [ "${separator}" = "" ]; then
            processdeps_spec_blanks=${processdeps_spec}
        else
            processdeps_spec_blanks=$(debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps_spec})
        fi

        local dep_spec
        for dep_spec in ${processdeps_spec_blanks}; do
            local deptype=$(debasher::_get_deptype_part_in_dep ${dep_spec})
            if is_blocking_deptype "${deptype}"; then
                echo "${deptype}"
                return 0
            fi
        done

        return 1
    }

    check_process_oneshot_deps()
    {
        local processname=$1
        local process_spec=$2

        local processdeps_spec=$(debasher::_extract_processdeps_from_process_spec "${process_spec}")

        if [ -z "${processdeps_spec}" -o "${processdeps_spec}" = "none" -o "${processdeps_spec}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            return 0
        fi

        local blocking_deptype
        if blocking_deptype=$(get_first_blocking_deptype "${processdeps_spec}"); then
            echo "Error! --builtinsched-oneshot requires a pure FIFO-based program with no completion-based dependencies between processes (afterok/afternotok/afterany/aftercorr), but process \"${processname}\" has a \"${blocking_deptype}\" dependency (in: ${processdeps_spec})" >&2
            return 1
        fi
    }

    check_process_oneshot_throttle()
    {
        local processname=$1
        local process_spec=$2

        if ! debasher::_throttle_lets_all_tasks_run "${processname}" "${process_spec}"; then
            local throttle=$(debasher::_get_scheduler_throttle "$(debasher::_extract_throttle_from_process_spec "${process_spec}")")
            local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
            echo "Error! --builtinsched-oneshot never waits for a task to end, but process \"${processname}\" has ${num_tasks} tasks and a throttle of ${throttle}, so some of them would never be launched; remove the throttle or raise it to the number of tasks" >&2
            return 1
        fi
    }

    echo "# Checking program is compatible with --builtinsched-oneshot..." >&2

    local processname
    for processname in "${!DEBASHER_FINAL_PROCESS_SPEC[@]}"; do
        check_process_oneshot_deps "${processname}" "${DEBASHER_FINAL_PROCESS_SPEC[${processname}]}" || exit 1
        check_process_oneshot_throttle "${processname}" "${DEBASHER_FINAL_PROCESS_SPEC[${processname}]}" || exit 1
    done

    echo "Check complete" >&2

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
        # If --sched option not given, the scheduler is determined from
        # what is available on this machine (see
        # debasher::_determine_scheduler). This is the only place where it
        # is decided: everything after it uses debasher::_get_scheduler
        echo "## Scheduler was not specified using \"--sched\" option, it will be automatically determined..." >&2
        local sched=$(debasher::_determine_scheduler)
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

    # Iterate over the processes to be executed
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local opts_funcname
        local identify_cmdline_opt_funcname
        opts_funcname=$(debasher::_get_explain_cmdline_opts_funcname ${processname})
        if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            opts_funcname=$(debasher::_get_explain_opts_funcname ${processname})
            if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                echo "Warning: function to explain command-line options for process ${processname} was not found" >&2
                continue
            else
                identify_cmdline_opt_funcname=$(debasher::_get_identify_cmdline_opts_funcname ${processname})
                if [ "${identify_cmdline_opt_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                    identify_cmdline_opt_funcname=""
                fi
            fi
        fi
        ${opts_funcname} || exit 1
        if [ -n "${identify_cmdline_opt_funcname}" ]; then
            ${identify_cmdline_opt_funcname} || exit 1
        fi
    done

    # Print options
    debasher::_print_program_cmdline_opts

    echo "" >&2
}

########
check_process_opts()
{
    init_option_info()
    {
        local cmdline=$1

        # Iterate over the processes to be executed
        local processname
        for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
            # Define options for process
            local process_spec="${DEBASHER_INITIAL_PROCESS_SPEC[${processname}]}"
            debasher::_define_opts_for_process "${cmdline}" "${process_spec}" || { echo "Error: option not found for process ${processname}" >&2 ; return 1; }
        done
    }

    create_option_arrays()
    {
        local cmdline=$1
        local dirname=$2

        # Iterate over the processes to be executed
        local processname
        for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
            if ! debasher::_uses_option_generator "${processname}"; then
                # Load current option list
                debasher::_load_curr_opt_list_loop "${cmdline}" "${processname}"

                # Write option array to file (line by line)
                local opt_array_size=${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}
                local opts_fname=$(debasher::_get_sched_opts_fname_for_process "${processname}")
                debasher::_write_opt_array "DEBASHER_CURRENT_PROCESS_OPT_LIST" "${opt_array_size}" "${opts_fname}"

                # Clear variables
                debasher::_clear_curr_opt_list_array
            fi
        done
    }

    print_exh_opt_list_procs()
    {
        local cmdline=$1

        # Iterate over the processes to be executed
        local processname
        for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
            debasher::_show_curr_opt_list "${cmdline}" "${processname}"
        done
    }

    # Prints, for each process, its number of tasks and the options of
    # its first tasks, up to the given maximum. The result goes to
    # program.opts too, which debasher_compare_opts compares with the
    # one of the previous run to detect input changes: the options of an
    # array are assumed to be uniform across its tasks, so a change is
    # looked for in the first tasks only, while a change in the number of
    # tasks is always detected.
    show_process_opts()
    {
        local cmdline=$1
        local max_num_proc_opts_to_display=$2

        # Iterate over the processes to be executed
        local processname
        for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
            # Store process options in an array for visualization
            local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
            local serial_process_opts=$(debasher::_get_serial_process_opts "${cmdline}" "${processname}" "${max_num_proc_opts_to_display}")

            # Print info about options
            local line="PROCESS: ${processname} ; NUM_TASKS: ${num_tasks} ; OPTIONS: ${serial_process_opts}"
            echo "${line}" >&2
            echo "${line}"
        done
    }

    register_fifo_readers()
    {
        local cmdline=$1

        if debasher::_program_uses_fifos; then
            # Iterate over the processes to be executed
            local processname
            for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
                # Register fifos
                debasher::_register_fifos_read_by_process "${cmdline}" "${processname}" || return 1
            done
        fi
    }

    echo "# Checking process options..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local program_opts_file=$3
    local program_opts_exh_file=$4
    local program_fifos_file=$5

    # Clear scheduler options directory
    local sched_opts_dir=$(debasher::_get_sched_opts_dir)
    "${RM}" -f "${sched_opts_dir}"/*

    # Initialize option information
    init_option_info "${cmdline}" || return 1

    # Verify that the options each process actually defines match the
    # ones it declares via explain_opts (aborts on an undeclared option;
    # see debasher::_check_opt_names_vs_explain)
    debasher::_check_opt_names_vs_explain "${cmdline}" || return 1

    # Create option arrays
    create_option_arrays "${cmdline}" "${dirname}" || return 1

    # Print exhaustive option list for processes (only if process graph
    # should be generated)
    if [ "${gen_proc_graph_given}" -eq 1 ]; then
        print_exh_opt_list_procs "${cmdline}" > "${program_opts_exh_file}" || return 1
    fi

    # Show process options
    show_process_opts "${cmdline}" "${DB_EXEC_MAX_NUM_PROCESS_OPTS_TO_DISPLAY}" > "${program_opts_file}" || return 1

    # Register fifo readers
    register_fifo_readers "${cmdline}" || return 1

    # Check the tags of the fifos, now that the other end of every fifo is
    # known (see debasher::_validate_program_fifo_kinds)
    debasher::_validate_program_fifo_kinds || return 1

    # Give each node of a resident program its ports, which the checks above
    # guarantee are consistent (see debasher::_register_resident_task_ports)
    debasher::_register_resident_task_ports || return 1

    # Print info about fifos
    debasher::_show_program_fifos > "${program_fifos_file}" || return 1

    echo "" >&2
}

########
register_all_rerun_processes()
{
    echo "# Registering all processes to rerun (if any)..." >&2

    local dirname=$1
    local program_opts_file=$2
    local old_program_opts_file=$3
    local rerun_outdated_processes=$4

    if [ -f "${old_program_opts_file}" ]; then
        debasher::_define_rerun_processes_due_to_input_changes "${program_opts_file}" "${old_program_opts_file}" || exit 1
    fi

    debasher::_define_forced_rerun_processes || exit 1

    if [ ${rerun_outdated_processes} -eq 1 ]; then
        debasher::_define_rerun_processes_due_to_code_update "${dirname}" || exit 1
    fi

    if debasher::_program_uses_fifos ; then
        debasher::_define_rerun_processes_due_to_proc_status_of_fifo_owner_reader "${dirname}" || exit 1
    fi

    debasher::_define_rerun_processes_due_to_resident_resume "${dirname}" || exit 1

    debasher::_propagate_rerun_processes "${dirname}" || exit 1

    echo "Registering complete" >&2

    echo "" >&2
}

########
print_rerun_processes()
{
    local rerun_processes_string=$(debasher::_get_rerun_processes_as_string)

    if [ ! -z "${rerun_processes_string}" ]; then
        echo "# Printing list of processes to rerun..." >&2
        echo "${rerun_processes_string}" >&2
        debasher::_log_warning_rerun

        echo "" >&2
    fi
}

########
# The lock file is left in place when the lock is released: removing it
# would let a process that opened it before the removal lock the old
# file while another one locks a new file of the same name, both
# believing they hold the lock.
release_lock()
{
    local fd=$1

    "$FLOCK" -u "$fd"
}

########
prepare_lock()
{
    local -n fd_ref=$1   # nameref: caller variable
    local file=$2

    exec {fd_ref}>>"$file" || return 1   # Bash assigns free fd, stores it in fd_ref
    trap "release_lock $fd_ref" EXIT
}

########
# Takes the lock of the output directory, held until debasher_exec exits,
# so that no two debasher_exec prepare or launch a run on the same output
# directory at once. It is taken before anything is written there and
# before checking for processes in progress, so that the check and what
# follows it are one step for any other debasher_exec.
ensure_exclusive_execution()
{
    local outd=$1
    local lockfile="${outd}/${DEBASHER_LOCK_BASENAME}"

    prepare_lock LOCKFD "$lockfile" || return 1
    if ! "$FLOCK" -xn "$LOCKFD"; then
        echo "Error: another debasher_exec is preparing or running a program in ${outd}" >&2
        return 1
    fi

    # The process id goes into the lock file, so that debasher_stop can
    # stop this debasher_exec, the built-in scheduler of the run, before
    # it stops the processes (see debasher::_stop_run_scheduler)
    echo "$$" > "$lockfile" || return 1
}

########
# Creates the output directory if necessary and makes the global outd
# absolute, since everything derived from it after this point (the
# scripts of the processes, their completion markers, the paths given to
# them) must not depend on the working directory of the process that
# reads it.
set_debasher_output_dir()
{
    echo "# Setting DeBasher output directory (the directory will be created if necessary)..." >&2

    # Create directory
    if [ ! -d "${outd}" ]; then
        "${MKDIR}" -p "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi

    # Get absolute file path
    outd=$(debasher::_get_absolute_path "${outd}")

    # Set outd as the output directory of debasher
    debasher::_set_debasher_outdir "${outd}"

    echo "" >&2
}

########
# debasher_exec --check-proc-opts computes the options of every task as a
# run would, but writes them into a temporary directory removed on exit
# instead of the .sched_opts directory of the output directory, which the
# tasks of a run in progress read.
use_temporary_sched_opts_dir()
{
    DEBASHER_SCHED_OPTS_DIR=$("${MKTEMP}" -d) || { echo "Error! cannot create temporary directory" >&2; return 1; }
    trap '"${RM}" -rf "${DEBASHER_SCHED_OPTS_DIR}"' EXIT
}

########
create_basic_dirs()
{
    echo "# Creating basic directories..." >&2

    local execdir=$(debasher::_get_prg_exec_dir)
    "${MKDIR}" -p "${execdir}" || { echo "Error! cannot create exec directory" >&2; return 1; }

    local sched_opts_dir=$(debasher::_get_sched_opts_dir)
    "${MKDIR}" -p "${sched_opts_dir}" || { echo "Error! cannot create scheduler options directory" >&2; return 1; }

    local graphsdir=$(debasher::_get_prg_graphs_dir)
    "${MKDIR}" -p "${graphsdir}" || { echo "Error! cannot create graphs directory" >&2; return 1; }

    local fifodir=$(debasher::_get_absolute_fifodir)
    "${MKDIR}" -p "${fifodir}" || { echo "Error! cannot create fifos directory" >&2; return 1; }

    local condadir=$(debasher::_get_absolute_condadir)
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
    local outd=$1
    local command_line=$2

    printf 'cd %q\n' "${PWD}" > "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
    debasher::_sep_serialized_to_qstr "${DEBASHER_ARG_SEP}" "${command_line}" >> "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
    echo "" >> "${outd}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"
}

########
prepare_files_and_dirs_for_process()
{
    # Read input parameters
    local dirname=$1
    local processname=$2
    local process_spec=$3

    echo "Preparing files and directories for process ${processname}" >&2

    # Obtain process status
    local status=$(debasher::_get_process_status ${dirname} "${processname}")

    # Decide whether the process should be executed (NOTE: for a
    # process that should not be executed, files and directories are
    # still prepared)
    if [ "${status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" -a "${status}" != "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        # Obtain array size
        local array_size=$(debasher::_get_numtasks_for_process "${processname}")

        # Prepare files and directories for process
        if [ "${status}" = "${DEBASHER_TODO_PROCESS_STATUS}" ]; then
            debasher::_create_exec_dir_for_process "${dirname}" "${processname}" || { echo "Error when creating exec directory for process" >&2 ; return 1; }
            debasher::_create_outdir_for_process "${dirname}" "${processname}" || { echo "Error when creating output directory for process" >&2 ; return 1; }
        else
            debasher::_clean_process_files "${dirname}" "${processname}" "${array_size}" || { echo "Error when cleaning files for process" >&2 ; return 1; }
        fi
        debasher::_prepare_fifos_owned_by_process "${processname}"
    fi
}

########
prepare_files_and_dirs_for_processes()
{
    echo "# Preparing files and directories for processes..." >&2

    # Read input parameters
    local dirname=$1

    local processname
    for processname in "${!DEBASHER_FINAL_PROCESS_SPEC[@]}"; do
        local process_spec="${DEBASHER_FINAL_PROCESS_SPEC[${processname}]}"
        prepare_files_and_dirs_for_process "${dirname}" "${processname}" "${process_spec}"
    done

    echo "Preparation complete" >&2

    echo "" >&2
}

########
revise_rerun_proc_status()
{
    echo "# Revise process status for processes to rerun..." >&2

    # Read input parameters
    local dirname=$1

    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        # Get process status
        local status=$(debasher::_get_process_status ${dirname} "${processname}")

        # If process is marked as rerun and it was finished, its process completion is reset
        if debasher::_process_marked_as_rerun ${processname} && [ "${status}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]; then
            debasher::_reset_process_completion_signal "${dirname}" "${processname}" || { echo "Error when resetting process completion signal for process" >&2 ; return 1; }
        fi
    done

    echo "Revision complete" >&2

    echo "" >&2
}

########
get_processdeps_with_id_info_from_detailed_spec()
{
    local processdeps_spec=$1
    local pdeps=""

    # Iterate over the elements of the process specification: type1:processname1,...,typen:processnamen or type1:processname1?...?typen:processnamen
    local separator=$(debasher::_get_processdeps_separator ${processdeps_spec})
    if [ "${separator}" = "" ]; then
        local processdeps_spec_blanks=${processdeps_spec}
    else
        local processdeps_spec_blanks=$(debasher::_replace_str_elem_sep_with_blank "${separator}" ${processdeps_spec})
    fi
    local dep_spec
    for dep_spec in ${processdeps_spec_blanks}; do
        local deptype=$(debasher::_get_deptype_part_in_dep ${dep_spec})
        local mapped_deptype=$(debasher::_map_deptype_if_necessary ${deptype})
        local processname=$(debasher::_get_processname_part_in_dep ${dep_spec})
        # Check if there is an id for the process
        if [ ! -z "${DB_EXEC_PROCESS_IDS[${processname}]}" ]; then
            if [ -z "${pdeps}" ]; then
                pdeps=${mapped_deptype}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${DB_EXEC_PROCESS_IDS[${processname}]}
            else
                pdeps=${pdeps}"${separator}"${mapped_deptype}${DEBASHER_PROCESS_PLUS_DEPTYPE_SEP}${DB_EXEC_PROCESS_IDS[${processname}]}
            fi
        fi
    done

    echo ${pdeps}
}

########
get_processdeps_with_id_info()
{
    local processdeps_spec=$1
    case ${processdeps_spec} in
            "none") echo ""
                    ;;
            *) get_processdeps_with_id_info_from_detailed_spec "${processdeps_spec}"
               ;;
    esac
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
    local status=$(debasher::_get_process_status ${dirname} "${processname}")
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    # Decide whether the process should be executed
    if [ "${status}" != "${DEBASHER_FINISHED_PROCESS_STATUS}" -a "${status}" != "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
        # Leave the process unlaunched, and so the processes that depend on
        # it, when it depends on processes that are not launched in this run
        # in a way that can never hold (see
        # debasher::_deps_without_ids_can_hold)
        local processdeps_spec=$(debasher::_extract_processdeps_from_process_spec "${process_spec}")
        if ! debasher::_deps_without_ids_can_hold "${processdeps_spec}" "${dirname}" DB_EXEC_PROCESS_IDS; then
            echo "Process ${processname} is not launched: its dependencies (${processdeps_spec}) cannot hold in this run" >&2
            return 0
        fi

        # Create script
        local opt_array_size=$(debasher::_get_numtasks_for_process "${processname}")
        debasher::_create_script "${cmdline}" "${dirname}" "${processname}" "${opt_array_size}"

        # Launch process
        local task_array_list=$(debasher::_get_task_array_list "${dirname}" "${processname}" "${opt_array_size}")
        local processdeps=$(get_processdeps_with_id_info "${processdeps_spec}")
        debasher::_launch "${dirname}" "${processname}" "${opt_array_size}" "${task_array_list}" "${process_spec}" "${processdeps}" "launch_outvar" || { echo "Error while launching process!" >&2 ; return 1; }

        # Update variables storing id information
        local primary_id=$(debasher::_get_primary_id "${launch_outvar}")
        DB_EXEC_PROCESS_IDS[${processname}]=${primary_id}

        # Write id to file
        debasher::_write_process_id_info_to_file "${dirname}" "${processname}" "${launch_outvar}"
    else
        # If process is in progress, its id should be retrieved so as to
        # correctly express dependencies
        if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
            local sid_info=$(debasher::_read_process_id_info_from_file "${dirname}" "${processname}") || { echo "Error while retrieving id of in-progress process" >&2 ; return 1; }
            local global_id=$(debasher::_get_global_id "${sid_info}")
            DB_EXEC_PROCESS_IDS["${processname}"]=${global_id}
        fi
    fi
}

########
launch_program_processes()
{
    echo "# Launching program processes..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2

    # A SIGTERM, which debasher_stop sends before it stops the processes
    # (see debasher::_stop_run_scheduler), asks for nothing more to be
    # launched: it is only noted here, and acted upon before the next
    # process, so that a process is never left half launched (its job
    # submitted, but held, or without its id written)
    local stop_requested=0
    trap 'stop_requested=1' TERM

    # WARNING: Before launching a particular process, its dependencies
    # should have been launched first. That's why the
    # processes are explored in topological order
    local processname
    for processname in "${DEBASHER_PROGRAM_PROCESSES_TOPO_SORT[@]}"; do
        if [ ${stop_requested} -eq 1 ]; then
            echo "Stop requested: no more processes are launched" >&2
            trap - TERM
            return 1
        fi
        launch_process "${cmdline}" "${dirname}" "${processname}" "${DEBASHER_FINAL_PROCESS_SPEC[$processname]}" || { trap - TERM; return 1; }
    done
    trap - TERM

    echo "" >&2
}

########
there_are_in_progress_processes()
{
    # Read input parameters
    local dirname=$1

    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        # Obtain process status
        local status=$(debasher::_get_process_status ${dirname} "${processname}")

        if [ "${status}" = "${DEBASHER_INPROGRESS_PROCESS_STATUS}" ]; then
            return 0
        fi
    done

    return 1
}

########
wait_for_program_processes()
{
    echo "# Waiting for program processes to finish..." >&2

    # Read input parameters
    local dirname=$1

    # Obtain number of processes
    local num_procs=$(debasher::_get_num_processes)

    while there_are_in_progress_processes "${dirname}"; do
        if [ "${num_procs}" -le 10 ]; then
            "${SLEEP}" "${DB_EXEC_WAIT_FOR_PROCESSES_SLEEP_TIME_SHORT}"
        else
            "${SLEEP}" "${DB_EXEC_WAIT_FOR_PROCESSES_SLEEP_TIME_LONG}"
        fi
    done

    echo "Waiting complete" >&2

    echo "" >&2
}

########
show_process_to_launch()
{
    # Initialize variables
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local process_spec=$4

    # Show the status and the specification of the process, launching
    # nothing

    # Obtain process status
    local status=$(debasher::_get_process_status "${dirname}" "${processname}")
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2
}

########
show_program_processes_to_launch()
{
    echo "# Program processes that a launch would start... (validation)" >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2

    # WARNING: Before launching a particular process, its dependencies
    # should have been launched first. That's why the
    # processes are explored in topological order
    local processname
    for processname in "${DEBASHER_PROGRAM_PROCESSES_TOPO_SORT[@]}"; do
        show_process_to_launch "${cmdline}" "${dirname}" "${processname}" "${DEBASHER_FINAL_PROCESS_SPEC[$processname]}" || return 1
    done

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
    echo "- Get standard output for a process:" >&2
    echo "debasher_get_stdout -d <outdir> -p <process_name>" >&2
    echo "- Get scheduler output for a process (useful for debugging):" >&2
    echo "debasher_get_sched_out -d <outdir> -p <process_name>" >&2
    echo "" >&2
}

########
restore_old_process_options()
{
    local old_program_opts_file=$1
    local program_opts_file=$2

    if [ -f "${old_program_opts_file}" ]; then
        "${CP}" "${old_program_opts_file}" "${program_opts_file}"
    fi
}

########
store_old_process_options()
{
    local old_program_opts_file=$1
    local program_opts_file=$2

    "${CP}" "${program_opts_file}" "${old_program_opts_file}"
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
command_line=$(debasher::_serialize_args "$0" "$@")

read_pars "$@" || exit 1

check_pars || exit 1

# The command line saved in the output directory gives the resolved
# program file, not the one given: the tools that operate on the
# directory later (debasher_status, debasher_stop, ...) find the program
# from it, and they may not run with the same DEBASHER_MOD_DIR
command_line=$(debasher::_set_opt_value_in_serialized_cmdline "${command_line}" "--pfile" "${pfile}")

set_debasher_output_dir || exit 1

# Everything but showing or checking the options may write into the
# output directory, and takes its lock first
if [ ${show_cmdline_opts_given} -eq 0 ] && [ ${check_proc_opts_given} -eq 0 ]; then
    ensure_exclusive_execution "${outd}" || exit 1
    debasher::_check_outdir_not_moved "${outd}" || exit 1
fi

if [ ${check_proc_opts_given} -eq 1 ]; then
    use_temporary_sched_opts_dir || exit 1
fi

create_basic_dirs || exit 1

configure_scheduler || exit 1

load_module "${pfile}" || exit 1

# Initialize process specification
initialize_procspec "${pfile}" || exit 1

debasher::_validate_resident_program_processes || exit 1

enforce_resident_program_scheduling || exit 1

record_effective_scheduler_in_command_line || exit 1

if [ ${show_cmdline_opts_given} -eq 1 ]; then
    show_cmdline_opts || exit 1

    exit 0
fi

if [ ${check_proc_opts_given} -eq 1 ]; then
    null_file="/dev/null"
    check_process_opts "${command_line}" "${outd}" "${null_file}" \
                       "${null_file}" "${null_file}" || exit 1

    exit 0
fi

# Check if there are running processes and abort execution if true
ensure_program_not_being_executed

# Define basic file variables
prg_file_pref="${outd}/${DEBASHER_PRG_PREF}"
program_opts_file="${prg_file_pref}.${DEBASHER_PRGOPTS_FEXT}"
old_program_opts_file="${prg_file_pref}.${DEBASHER_PRGOPTS_OLD_FEXT}"
program_opts_exh_file="${prg_file_pref}.${DEBASHER_PRGOPTS_EXHAUSTIVE_FEXT}"
program_fifos_file="${prg_file_pref}.${DEBASHER_FIFOS_FEXT}"
prg_graphs_dir=$(debasher::_get_prg_graphs_dir)
procgraph_file_prefix="${prg_graphs_dir}/process_graph"
depgraph_file_prefix="${prg_graphs_dir}/dependency_graph"

check_process_opts "${command_line}" "${outd}" "${program_opts_file}" \
                   "${program_opts_exh_file}" "${program_fifos_file}" || exit 1

ensure_scheduler_supports_fifos || exit 1

procspec_file="${prg_file_pref}.${DEBASHER_PROCSPEC_FEXT}"
gen_final_procspec "${command_line}" > "${procspec_file}" || exit 1

topologically_sort_processes || exit 1

if [ ${builtin_sched_oneshot_given} -eq 1 ]; then
    check_oneshot_precondition || exit 1
fi

# Generate graphs
if [ "${gen_proc_graph_given}" -eq 1 ]; then
    gen_process_graph "${prg_file_pref}" "${procgraph_file_prefix}" || exit 1
fi

gen_dependency_graph "${prg_file_pref}" "${depgraph_file_prefix}" || exit 1

create_mod_shared_dirs || exit 1

if [ ${conda_support_given} -eq 1 ]; then
    debasher::_prepare_conda_envs || exit 1
fi

if [ ${docker_support_given} -eq 1 ]; then
    debasher::_pull_docker_imgs || exit 1
fi

# Register all processes to rerun
register_all_rerun_processes "${outd}" "${program_opts_file}" "${old_program_opts_file}" "${rerun_outdated_processes_given}"

print_rerun_processes || exit 1

print_command_line "${outd}" "${command_line}" || exit 1

# Write the context that the script of every process starts with, now
# that the program is fully defined and before anything is launched
write_exec_context "${outd}" || exit 1

# Launch processes
if [ ${validate} -eq 1 ]; then
    show_program_processes_to_launch "${command_line}" "${outd}" || exit 1

    # What the built-in scheduler checks before its first round, the
    # resources of each process against its budget, is checked too, so that
    # a program that passes the validation is not refused for what a single
    # process asks for
    comp_res_ok=1
    if [ "$(debasher::_get_scheduler)" = "${DEBASHER_BUILTIN_SCHEDULER}" ]; then
        debasher_builtin_sched::check_program_comp_res "${procspec_file}" "${builtin_sched_cpus}" "${builtin_sched_mem}" || comp_res_ok=0
    fi

    # Restore old process options (if they exist)
    restore_old_process_options "${old_program_opts_file}" "${program_opts_file}"

    [ ${comp_res_ok} -eq 1 ] || exit 1
else
    sched=$(debasher::_get_scheduler)
    if [ ${builtin_sched_oneshot_given} -eq 1 ] && [ "${sched}" != "${DEBASHER_BUILTIN_SCHEDULER}" ]; then
        echo "Error! --builtinsched-oneshot can only be used with the built-in scheduler" >&2
        exit 1
    fi
    if [ "${sched}" = "${DEBASHER_BUILTIN_SCHEDULER}" ]; then
        debasher_builtin_sched::execute_program_processes "${command_line}" "${outd}" "${procspec_file}" "${builtin_sched_cpus}" "${builtin_sched_mem}" "${builtin_sched_oneshot_given}" || exit 1
        if [ ${builtin_sched_oneshot_given} -eq 1 ]; then
            print_post_exec_nowait_help
        else
            print_post_exec_wait_help
        fi
    else
        revise_rerun_proc_status "${outd}" || exit 1
        prepare_files_and_dirs_for_processes "${outd}"
        launch_program_processes "${command_line}" "${outd}" || exit 1
        if [ "${wait}" -eq 1 ]; then
            wait_for_program_processes "${outd}" || exit 1
            print_post_exec_wait_help
        else
            print_post_exec_nowait_help
        fi
    fi
    # Store old process options
    store_old_process_options "${old_program_opts_file}" "${program_opts_file}"
fi
