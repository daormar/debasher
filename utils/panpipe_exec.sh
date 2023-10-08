# PanPipe package# Copyright (C) 2019,2020 Daniel Ortiz-Mart\'inez
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
. "${panpipe_bindir}"/panpipe_lib || exit 1
. "${panpipe_libexecdir}"/panpipe_builtin_sched_lib || exit 1

#############
# CONSTANTS #
#############

# MISC. CONSTANTS
LOCKFD=99
MAX_NUM_PROCESS_OPTS_TO_DISPLAY=10
REEXEC_PROCESSES_LIST_FNAME=".reexec_processes_due_to_deps.txt"

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
    echo "panpipe_exec executes general purpose pipelines"
    echo "type \"panpipe_exec --help\" to get usage information"
}

########
usage()
{
    echo "panpipe_exec              --pfile <string> --outdir <string> [--sched <string>]"
    echo "                          [--builtinsched-cpus <int>] [--builtinsched-mem <int>]"
    echo "                          [--dflt-nodes <string>] [--dflt-throttle <string>]"
    echo "                          [--reexec-outdated-procs] [--conda-support]"
    echo "                          [--showopts|--checkopts|--debug]"
    echo "                          [--builtinsched-debug] [--version] [--help]"
    echo ""
    echo "--pfile <string>          File with pipeline processes to be performed (see manual"
    echo "                          for additional information)"
    echo "--outdir <string>         Output directory"
    echo "--sched <string>          Scheduler used to execute the pipeline (if not given,"
    echo "                          it is determined using information gathered during"
    echo "                          package configuration)"
    echo "--builtinsched-cpus <int> Available CPUs for built-in scheduler (${BUILTIN_SCHED_CPUS} by default)."
    echo "                          A value of zero means unlimited CPUs"
    echo "--builtinsched-mem <int>  Available memory in MB for built-in scheduler"
    echo "                          (${BUILTIN_SCHED_MEM} by default). A value of zero"
    echo "                          means unlimited memory"
    echo "--dflt-nodes <string>     Default set of nodes used to execute the pipeline"
    echo "--dflt-throttle <string>  Default task throttle used when executing job arrays"
    echo "--reexec-outdated-procs   Reexecute those processes with outdated code"
    echo "--conda-support           Enable conda support"
    echo "--showopts                Show pipeline options"
    echo "--checkopts               Check pipeline options"
    echo "--debug                   Do everything except launching pipeline processes"
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
    builtinsched_cpus_given=0
    builtinsched_mem_given=0
    dflt_nodes_given=0
    dflt_throttle_given=0
    reexec_outdated_processes_given=0
    conda_support_given=0
    showopts_given=0
    checkopts_given=0
    debug=0
    builtinsched_debug=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--version") panpipe_version
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
                      builtinsched_cpus=$1
                      if ! str_is_natural_number ${builtinsched_cpus}; then
                          echo "Value for --builtinsched_cpus option should be a natural number" >&2
                          return 1
                      fi
                      builtinsched_cpus_given=1
                  fi
                  ;;
            "--builtinsched-mem") shift
                  if [ $# -ne 0 ]; then
                      builtinsched_mem=$1
                      builtinsched_mem=`convert_mem_value_to_mb ${builtinsched_mem}` || { echo "Invalid memory specification for --builtinsched_mem option}" >&2; return 1; }
                      if ! str_is_natural_number ${builtinsched_mem}; then
                          echo "Value for --builtinsched_mem option should be a natural number" >&2
                          return 1
                      fi
                      builtinsched_mem_given=1
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
            "--showopts") showopts_given=1
                          ;;
            "--checkopts") checkopts_given=1
                           ;;
            "--debug") debug=1
                       ;;
            "--builtinsched-debug") builtinsched_debug=1
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

    if [ ${showopts_given} -eq 1 -a ${checkopts_given} -eq 1 ]; then
        echo "Error! --showopts and --checkopts options cannot be given simultaneously"
        exit 1
    fi

    if [ ${showopts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --showopts and --debug options cannot be given simultaneously"
        exit 1
    fi

    if [ ${checkopts_given} -eq 1 -a ${debug} -eq 1 ]; then
        echo "Error! --checkopts and --debug options cannot be given simultaneously"
        exit 1
    fi
}

########
absolutize_file_paths()
{
    if [ ${pfile_given} -eq 1 ]; then
        pfile=`get_absolute_path "${pfile}"`
    fi

    if [ ${outdir_given} -eq 1 ]; then
        outd=`get_absolute_path "${outd}"`
    fi
}

####################################
# GENERAL PIPE EXECUTION FUNCTIONS #
####################################

load_module()
{
    echo "# Loading module ($pfile)..." >&2

    # Load panpipe module containing the pipeline to be executed
    load_panpipe_module "${pfile}" || exit 1

    echo "" >&2
}

########
gen_initial_procspec_file()
{
    echo "# Generating initial process specification from $pfile..." >&2

    exec_pipeline_func_for_module "${pfile}" || exit 1

    echo "" >&2
}

########
check_pipeline()
{
    local prefix_of_ppl_files=$1

    echo "# Checking process specification..." >&2

    "${panpipe_libexecdir}"/panpipe_check -p "${prefix_of_ppl_files}" || return 1

    echo "" >&2
}

########
gen_final_procspec_file()
{
    local initial_procspec_file=$1

    echo "# Generating final process specification file..." >&2

    # Iterate over process specifications
    while read process_spec; do
        # Extract process information
        local processname=`extract_processname_from_process_spec "$process_spec"`

        # Obtain process dependencies
        procdeps=`get_procdeps_for_process ${processname}`

        # Print process specification plus process dependencies
        echo "${process_spec}" "${procdeps}"
    done < "${initial_procspec_file}"


    echo "" >&2
}

########
gen_processdeps()
{
    local prefix_of_ppl_files=$1

    echo "# Generating process dependencies information..." >&2

    "${panpipe_libexecdir}"/panpipe_check -p "${prefix_of_ppl_files}" -d || return 1

    echo "" >&2
}

########
configure_scheduler()
{
    echo "# Configuring scheduler..." >&2
    echo "" >&2

    if [ ${sched_given} -eq 1 ]; then
        echo "## Setting scheduler type from value of \"--sched\" option..." >&2
        set_panpipe_scheduler ${sched_opt} || return 1
        echo "scheduler: ${sched_opt}" >&2
        echo "" >&2
    else
        # If --sched option not given, the scheduler is first determined
        # based on information gathered during package configuration
        # (see determine_scheduler function in panpipe_lib.sh). Once the
        # scheduler is determined, it will be set using the
        # set_panpipe_scheduler function
        echo "## Scheduler was not specified using \"--sched\" option, it will be automatically determined..." >&2
        local sched=`determine_scheduler`
        set_panpipe_scheduler ${sched} || return 1
        echo "scheduler: ${sched}" >&2
        echo "" >&2
    fi

    if [ ${dflt_nodes_given} -eq 1 ]; then
        echo "## Setting default nodes for pipeline execution... (${dflt_nodes})" >&2
        set_panpipe_default_nodes ${dflt_nodes} || return 1
        echo "" >&2
    fi

    if [ ${dflt_throttle_given} -eq 1 ]; then
        echo "## Setting default job array task throttle... (${dflt_throttle})" >&2
        set_panpipe_default_array_task_throttle ${dflt_throttle} || return 1
        echo "" >&2
    fi
}

########
show_pipeline_opts()
{
    echo "# Pipeline options..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        # Extract process information
        local processname=`extract_processname_from_process_spec "$process_spec"`
        local explain_cmdline_opts_funcname=`get_explain_cmdline_opts_funcname ${processname}`
        DIFFERENTIAL_CMDLINE_OPT_STR=""
        ${explain_cmdline_opts_funcname} || exit 1
        update_opt_to_process_map ${processname} "${DIFFERENTIAL_CMDLINE_OPT_STR}"
    done < "${procspec_file}"

    # Print options
    print_pipeline_opts

    echo "" >&2
}

########
check_pipeline_opts()
{
    echo "# Checking pipeline options..." >&2

    # Read input parameters
    local cmdline=$1
    local procspec_file=$2
    local out_opts_file=$3
    local out_fifos_file=$4

    # Remove output files
    rm -f "${out_opts_file}" "${out_fifos_file}"

    # Read information about the processes to be executed
    while read process_spec; do
        # Extract process information
        local processname=`extract_processname_from_process_spec "$process_spec"`
        define_opts_for_process "${cmdline}" "${process_spec}" || return 1
        local process_opts_array=()
        for process_opts in "${CURRENT_PROCESS_OPT_LIST[@]}"; do
            # Obtain human-readable representation of script options
            hr_process_opts=$(sargs_to_sargsquotes "${process_opts}")
            process_opts_array+=("${hr_process_opts}")
        done
        # Generate info about options
        local serial_process_opts=`serialize_string_array "process_opts_array" "${ARRAY_TASK_SEP}" ${MAX_NUM_PROCESS_OPTS_TO_DISPLAY}`
        echo "PROCESS: ${processname} ; OPTIONS: ${serial_process_opts}" >&2
        echo "PROCESS: ${processname} ; OPTIONS: ${serial_process_opts}" >> "${out_opts_file}"

        # Generate info about fifos
        show_pipeline_fifos_def_opts >> "${out_fifos_file}"
    done < "${procspec_file}"

    echo "" >&2
}

########
handle_conda_req_entry()
{
    local env_name=$1
    local yml_fname=$2

    # Check if environment already exists
    if conda_env_exists "${env_name}"; then
        :
    else
        local condadir=`get_absolute_condadir`

        # Obtain absolute yml file name
        local abs_yml_fname=`get_abs_yml_fname "${yml_fname}"`

        echo "Creating conda environment "${env_name}" from file ${abs_yml_fname}..." >&2
        conda_env_prepare "${env_name}" "${abs_yml_fname}" "${condadir}" || return 1
        echo "Package successfully installed"
    fi
}

########
handle_conda_requirements_for_process()
{
    processname=$1
    process_conda_envs=$2

    # Read information about conda environments
    while read conda_env_entry; do
        # Convert string to array
        local array
        IFS=' ' read -r -a array <<< $conda_env_entry
        local arraylen=${#array[@]}
        if [ ${arraylen} -ge 2 ]; then
            local env_name=${array[0]}
            local yml_fname=${array[1]}
            handle_conda_req_entry "${env_name}" "${yml_fname}" || return 1
        else
            echo "Error: invalid conda entry for process ${processname}; Entry: ${process_conda_envs}" >&2
        fi
    done < <(echo "${process_conda_envs}")
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
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`extract_processname_from_process_spec "$process_spec"`

            # Process conda envs information
            local conda_envs_funcname=`get_conda_envs_funcname ${processname}`
            if func_exists ${conda_envs_funcname}; then
                process_conda_envs=`${conda_envs_funcname}` || exit 1
                handle_conda_requirements_for_process "${processname}" "${process_conda_envs}" || return 1
            fi
        fi
    done < "${procspec_file}"

    echo "Handling complete" >&2

    echo "" >&2
}

########
define_dont_execute_processes()
{
    echo "# Define processes that should not be executed (if any)..." >&2

    # Read input parameters
    local cmdline=$1
    local procspec_file=$2

    # Read information about the processes to be executed
    while read process_spec; do
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`extract_processname_from_process_spec "$process_spec"`
            local should_execute_funcname=`get_should_execute_funcname ${processname}`
            if [ "${should_execute_funcname}" != ${FUNCT_NOT_FOUND} ]; then
                if ! ${should_execute_funcname} "${cmdline}" "${process_spec}"; then
                    mark_process_as_dont_execute ${processname} "${EXECFUNCT_DONT_EXEC_REASON}"
                fi
            fi
        fi
    done < "${procspec_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_forced_exec_processes()
{
    echo "# Defining processes forced to be reexecuted (if any)..." >&2

    # Read input parameters
    local procspec_file=$1

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`extract_processname_from_process_spec "$process_spec"`
            local process_forced=`extract_attr_from_process_spec "$process_spec" "force"`
            if [ ${process_forced} = "yes" ]; then
                mark_process_as_reexec $processname ${FORCED_REEXEC_REASON}
            fi
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
        for mod in "${!PIPELINE_MODULES[@]}"; do
            fullmod="${PIPELINE_MODULES[$mod]}"
            if [ "${script_filename}" -ot ${fullmod} ]; then
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
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process information
            local processname=`extract_processname_from_process_spec "$process_spec"`
            local status=`get_process_status "${dirname}" ${processname}`
            local script_filename=`get_script_filename "${dirname}" ${processname}`

            # Handle checkings depending of process status
            if [ "${status}" = "${FINISHED_PROCESS_STATUS}" ]; then
                if check_script_is_older_than_modules "${script_filename}"; then
                    echo "Warning: last execution of process ${processname} used outdated modules">&2
                    mark_process_as_reexec $processname ${OUTDATED_CODE_REEXEC_REASON}
                fi
            fi

            if [ "${status}" = "${INPROGRESS_PROCESS_STATUS}" ]; then
                if check_script_is_older_than_modules "${script_filename}"; then
                    echo "Warning: current execution of process ${processname} is using outdated modules">&2
                fi
            fi
        fi
    done < "${procspec_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
define_reexec_processes_due_to_deps()
{
    echo "# Defining processes to be reexecuted due to dependencies (if any)..." >&2

    local processdeps_file=$1

    # Obtain list of processes to be reexecuted due to dependencies
    local reexec_processes_string=`get_reexec_processes_as_string`
    local reexec_processes_file="${outd}/${REEXEC_PROCESSES_LIST_FNAME}"
    "${panpipe_libexecdir}"/pp_get_reexec_procs_due_to_deps -r "${reexec_processes_string}" -d "${processdeps_file}" > "${reexec_processes_file}" || return 1

    # Read information about the processes to be re-executed due to
    # dependencies
    local processname
    while read processname; do
        if [ "${processname}" != "" ]; then
            mark_process_as_reexec $processname ${DEPS_REEXEC_REASON}
        fi
    done < "${reexec_processes_file}"

    echo "Definition complete" >&2

    echo "" >&2
}

########
print_reexec_processes()
{
    local reexec_processes_string=`get_reexec_processes_as_string`

    if [ ! -z "${reexec_processes_string}" ]; then
        echo "# Printing list of processes to be reexecuted..." >&2
        echo "${reexec_processes_string}" >&2
        echo "${PANPIPE_REEXEC_PROCESSES_WARNING}" >&2
        echo "" >&2
    fi
}

########
release_lock()
{
    local fd=$1
    local file=$2

    # Drop lock
    $FLOCK -u $fd || return 1

    # Try to acquire lock and remove associated file (if acquisition was
    # successful)
    $FLOCK -xn $fd && rm -f "$file" || return 1
}

########
prepare_lock()
{
    local fd=$1
    local file=$2
    eval "exec $fd>\"$file\"" && trap "release_lock $fd $file" EXIT;
}

########
ensure_exclusive_execution()
{
    local lockfile="${outd}"/lock

    prepare_lock $LOCKFD "$lockfile" || return 1

    # Try to acquire lock exclusively
    "$FLOCK" -xn $LOCKFD || return 1
}

########
create_basic_dirs()
{
    echo "# Creating basic directories..." >&2

    mkdir -p ${outd} || { echo "Error! cannot create output directory" >&2; return 1; }
    set_panpipe_outdir "${outd}"

    local scriptsdir=`get_ppl_scripts_dir`
    mkdir -p "${scriptsdir}" || { echo "Error! cannot create scripts directory" >&2; return 1; }

    local fifodir=`get_absolute_fifodir`
    mkdir -p "${fifodir}" || { echo "Error! cannot create fifos directory" >&2; return 1; }

    local condadir=`get_absolute_condadir`
    if [ ${conda_support_given} -eq 1 ]; then
        mkdir -p "${condadir}"
    fi

    echo "Creation complete" >&2

    echo "" >&2
}

########
create_mod_shared_dirs()
{
    echo "# Creating shared directories for modules... (if any)" >&2

    # Create shared directories required by the pipeline processes
    # IMPORTANT NOTE: the following functions can only be executed after
    # loading pipeline modules
    register_module_pipeline_shdirs
    create_pipeline_shdirs

    show_pipeline_shdirs >&2

    echo "Creation complete" >&2

    echo "" >&2
}

########
print_command_line()
{
    echo "cd $PWD" > "${outd}/${PPL_COMMAND_LINE_BASENAME}"
    sargs_to_sargsquotes "${command_line}" >> "${outd}/${PPL_COMMAND_LINE_BASENAME}"
}

########
get_processdeps_from_detailed_spec()
{
    local processdeps_spec=$1
    local sdeps=""

    # Iterate over the elements of the process specification: type1:processname1,...,typen:processnamen or type1:processname1?...?typen:processnamen
    local separator=`get_processdeps_separator ${processdeps_spec}`
    if [ "${separator}" = "" ]; then
        local processdeps_spec_blanks=${processdeps_spec}
    else
        local processdeps_spec_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps_spec}`
    fi
    local dep_spec
    for dep_spec in ${processdeps_spec_blanks}; do
        local deptype=`get_deptype_part_in_dep ${dep_spec}`
        local mapped_deptype=`map_deptype_if_necessary ${deptype}`
        local processname=`get_processname_part_in_dep ${dep_spec}`
        # Check if there is an id for the process
        if [ ! -z "${PIPE_EXEC_PROCESS_IDS[${processname}]}" ]; then
            if [ -z "${sdeps}" ]; then
                sdeps=${mapped_deptype}":"${PIPE_EXEC_PROCESS_IDS[${processname}]}
            else
                sdeps=${sdeps}"${separator}"${mapped_deptype}":"${PIPE_EXEC_PROCESS_IDS[${processname}]}
            fi
        fi
    done

    echo ${sdeps}
}

########
get_processdeps()
{
    local process_id_list=$1
    local processdeps_spec=$2
    case ${processdeps_spec} in
            "afterok:all") apply_deptype_to_processids "${process_id_list}" afterok
                    ;;
            "none") echo ""
                    ;;
            *) get_processdeps_from_detailed_spec "${processdeps_spec}"
               ;;
    esac
}

########
prepare_files_and_dirs_for_process()
{
    # Read input parameters
    local dirname=$1
    local processname=$2
    local process_spec=$3

    ## Obtain process status
    local status=`get_process_status ${dirname} ${processname}`

    ## Decide whether the process should be executed (NOTE: for a
    ## process that should not be executed, files and directories are
    ## still prepared)
    if [ "${status}" != "${FINISHED_PROCESS_STATUS}" -a "${status}" != "${INPROGRESS_PROCESS_STATUS}" ]; then
        # Initialize array_size variable and populate array of shared directories
        define_opts_for_process "${cmdline}" "${process_spec}" || return 1
        local process_opts_array=("${CURRENT_PROCESS_OPT_LIST[@]}")
        local array_size=${#process_opts_array[@]}

        # Prepare files and directories for process
        create_shdirs_owned_by_process || { echo "Error when creating shared directories determined by script option definition" >&2 ; return 1; }
        update_process_completion_signal "${dirname}" ${processname} ${status} || { echo "Error when updating process completion signal for process" >&2 ; return 1; }
        clean_process_log_files "${dirname}" ${processname} ${array_size} || { echo "Error when cleaning log files for process" >&2 ; return 1; }
        clean_process_id_files "${dirname}" ${processname} ${array_size} || { echo "Error when cleaning id files for process" >&2 ; return 1; }
        create_outdir_for_process "${dirname}" ${processname} || { echo "Error when creating output directory for process" >&2 ; return 1; }
        prepare_fifos_owned_by_process ${processname}
    fi
}

########
prepare_files_and_dirs_for_processes()
{
    # Read input parameters
    local dirname=$1
    local procspec_file=$2

    local process_spec
    while read process_spec; do
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`extract_processname_from_process_spec "$process_spec"`

            prepare_files_and_dirs_for_process "${dirname}" ${processname} "${process_spec}"
        fi
    done < "${procspec_file}"
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

    ## Obtain process status
    local status=`get_process_status ${dirname} ${processname}`
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    ## Decide whether the process should be executed
    if [ "${status}" != "${FINISHED_PROCESS_STATUS}" -a "${status}" != "${INPROGRESS_PROCESS_STATUS}" -a "${status}" != "${DONT_EXECUTE_PROCESS_STATUS}" ]; then
        # Create script
        define_opts_for_process "${cmdline}" "${process_spec}" || return 1
        local process_opts_array=("${CURRENT_PROCESS_OPT_LIST[@]}")
        local array_size=${#process_opts_array[@]}
        create_script "${dirname}" ${processname} "process_opts_array"

        # Archive script
        archive_script "${dirname}" ${processname}

        # Launch process
        local task_array_list=`get_task_array_list "${dirname}" ${processname} ${array_size}`
        local processdeps_spec=`extract_processdeps_from_process_spec "$process_spec"`
        local processdeps=`get_processdeps "${process_id_list}" ${processdeps_spec}`
        launch "${dirname}" ${processname} ${array_size} ${task_array_list} "${process_spec}" "${processdeps}" "launch_outvar" || { echo "Error while launching process!" >&2 ; return 1; }

        # Update variables storing id information
        local primary_id=`get_primary_id ${launch_outvar}`
        PIPE_EXEC_PROCESS_IDS[${processname}]=${primary_id}
        process_id_list="${process_id_list}:${PIPE_EXEC_PROCESS_IDS[${processname}]}"

        # Write id to file
        write_process_id_info_to_file "${dirname}" ${processname} ${launch_outvar}
    else
        # If process is in progress, its id should be retrieved so as to
        # correctly express dependencies
        if [ "${status}" = "${INPROGRESS_PROCESS_STATUS}" ]; then
            local sid_info=`read_process_id_info_from_file "${dirname}" ${processname}` || { echo "Error while retrieving id of in-progress process" >&2 ; return 1; }
            local global_id=`get_global_id ${sid_info}`
            PIPE_EXEC_PROCESS_IDS[${processname}]=${global_id}
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
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`extract_processname_from_process_spec "$process_spec"`

            launch_process "${cmdline}" "${dirname}" ${processname} "${process_spec}" || return 1
        fi
    done < "${procspec_file}"
}

########
execute_pipeline_processes()
{
    echo "# Executing pipeline processes..." >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # Prepare files and directories for processes
    prepare_files_and_dirs_for_processes "${dirname}" "${procspec_file}"

    # process_id_list will store the process ids of the pipeline processes
    local process_id_list=""

    # Launch processes
    launch_processes "${cmdline}" "${dirname}" "${procspec_file}"

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

    ## Obtain process status
    local status=`get_process_status "${dirname}" ${processname}`
    echo "PROCESS: ${processname} ; STATUS: ${status} ; PROCESS_SPEC: ${process_spec}" >&2

    ## Obtain process options
    local define_opts_funcname=`get_define_opts_funcname ${processname}`
    local process_outdir=`get_process_outdir_given_dirname "${dirname}" "${process_name}"`
    ${define_opts_funcname} "${cmdline}" "${process_spec}" "${processname}" "${process_outdir}" || return 1
}

########
execute_pipeline_processes_debug()
{
    echo "# Executing pipeline processes... (debug mode)" >&2

    # Read input parameters
    local cmdline=$1
    local dirname=$2
    local procspec_file=$3

    # process_id_list will store the process ids of the pipeline processes
    local process_id_list=""

    # Read information about the processes to be executed
    local process_spec
    while read process_spec; do
        if pipeline_process_spec_is_ok "$process_spec"; then
            # Extract process name
            local processname=`extract_processname_from_process_spec "$process_spec"`

            debug_process "${cmdline}" "${dirname}" ${processname} "${process_spec}" || return 1
        fi
    done < "${procspec_file}"

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
command_line=`serialize_args "$0" "$@"`

read_pars "$@" || exit 1

check_pars || exit 1

absolutize_file_paths || exit 1

create_basic_dirs || exit 1

load_module || exit

initial_procspec_file="${outd}/${PPEXEC_INITIAL_PROCSPEC_BASENAME}"
gen_initial_procspec_file > "${initial_procspec_file}" || exit 1

configure_scheduler || exit 1

if [ ${showopts_given} -eq 1 ]; then
    show_pipeline_opts "${initial_procspec_file}" || exit 1
else
    ppl_file_pref="${outd}/${PPEXEC_PPL_PREF}"
    pipeline_opts_file="${ppl_file_pref}.${PPLOPTS_FEXT}"
    pipeline_fifos_file="${ppl_file_pref}.${FIFOS_FEXT}"
    if [ ${checkopts_given} -eq 1 ]; then
        check_pipeline_opts "${command_line}" "${initial_procspec_file}" "${pipeline_opts_file}" "${pipeline_fifos_file}" || exit 1
    else
        check_pipeline_opts "${command_line}" "${initial_procspec_file}" "${pipeline_opts_file}" "${pipeline_fifos_file}" || exit 1

        procspec_file="${ppl_file_pref}.${PROCSPEC_FEXT}"
        gen_final_procspec_file "${initial_procspec_file}" > "${procspec_file}" || exit 1

        check_pipeline "${ppl_file_pref}" || exit 1

        processdeps_file="${outd}"/.processdeps.txt
        gen_processdeps "${ppl_file_pref}" > "${processdeps_file}" || exit 1

        # NOTE: exclusive execution should be ensured after creating the output directory
        ensure_exclusive_execution || { echo "Error: there was a problem while trying to ensure exclusive execution of pipe_exec" ; exit 1; }

        create_mod_shared_dirs || exit 1

        if [ ${conda_support_given} -eq 1 ]; then
            handle_conda_requirements "${procspec_file}" || exit 1
        fi

        define_dont_execute_processes "${command_line}" "${procspec_file}" || exit 1

        define_forced_exec_processes "${procspec_file}" || exit 1

        if [ ${reexec_outdated_processes_given} -eq 1 ]; then
            define_reexec_processes_due_to_code_update "${outd}" "${procspec_file}" || exit 1
        fi

        define_reexec_processes_due_to_deps "${processdeps_file}" || exit 1

        print_reexec_processes || exit 1

        print_command_line || exit 1

        if [ ${debug} -eq 1 ]; then
            execute_pipeline_processes_debug "${command_line}" "${outd}" "${procspec_file}" || exit 1
        else
            sched=`determine_scheduler`
            if [ ${sched} = ${BUILTIN_SCHEDULER} ]; then
                builtin_sched_execute_pipeline_processes "${command_line}" "${outd}" "${procspec_file}" || exit 1
            else
                execute_pipeline_processes "${command_line}" "${outd}" "${procspec_file}" || exit 1
            fi
        fi
    fi
fi
