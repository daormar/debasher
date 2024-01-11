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

#######################
# SCHEDULER FUNCTIONS #
#######################

# INCLUDE BASH LIBRARY
. "${debasher_libexecdir}"/debasher_lib_sched_slurm || exit 1
. "${debasher_libexecdir}"/debasher_lib_sched_builtin || exit 1
. "${debasher_libexecdir}"/debasher_lib_sched_procs || exit 1

########
set_debasher_outdir()
{
    local abs_outd=$1

    PROGRAM_OUTDIR=${abs_outd}
}

########
get_prg_outd()
{
    echo "${PROGRAM_OUTDIR}"
}

########
set_debasher_scheduler()
{
    local sched=$1

    case $sched in
        ${SLURM_SCHEDULER})
            # Verify SLURM availability
            if [ "$SBATCH" = "" ]; then
                echo "Error: SLURM scheduler is not installed in your system"
                return 1
            fi
            DEBASHER_SCHEDULER=${SLURM_SCHEDULER}
            init_slurm_scheduler
            ;;
        ${BUILTIN_SCHEDULER})
            DEBASHER_SCHEDULER=${BUILTIN_SCHEDULER}
            ;;
        *)  echo "Error: ${sched} is not a valid scheduler"
            DEBASHER_SCHEDULER=""
            return 1
            ;;
    esac
}

########
set_debasher_default_nodes()
{
    local value=$1

    DEBASHER_DEFAULT_NODES=$value
}

########
set_debasher_default_array_task_throttle()
{
    local value=$1

    DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE=$value
}

########
determine_scheduler()
{
    # Check if schedulers were disabled
    if [ ${DISABLE_SCHEDULERS} = "yes" ]; then
        echo ${BUILTIN_SCHEDULER}
    else
        # Check if scheduler was already specified
        if [ -z "${DEBASHER_SCHEDULER}" ]; then
            # Scheduler not specified, set it based on information
            # gathered during package configuration
            if [ -z "${SBATCH}" ]; then
                echo ${BUILTIN_SCHEDULER}
            else
                echo ${SLURM_SCHEDULER}
            fi
        else
            echo ${DEBASHER_SCHEDULER}
        fi
    fi
}

########
get_scheduler()
{
    echo ${DEBASHER_SCHEDULER}
}

########
create_script()
{
    # Init variables
    local dirname=$1
    local processname=$2
    local opts_fname=$3
    local opt_array_size=$4

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            create_slurm_script "${dirname}" "$processname" "${opts_fname}" "${opt_array_size}"
            ;;
    esac
}

########
archive_script()
{
    local dirname=$1
    local processname=$2
    local script_filename=`get_script_filename "${dirname}" ${processname}`

    # Archive script with date info
    local curr_date=`date '+%Y_%m_%d'`
    "${CP}" "${script_filename}" "${script_filename}.${curr_date}"
}

########
get_scheduler_throttle()
{
    local process_spec_throttle=$1

    if [ "${process_spec_throttle}" = ${ATTR_NOT_FOUND} ]; then
        echo "${DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE}"
    else
        echo "${process_spec_throttle}"
    fi
}

########
get_num_attempts()
{
    # Initialize variables
    local time=$1
    local mem=$2

    # Obtain arrays for time and memory limits
    local time_array
    local mem_array
    IFS="$ATTEMPT_SEP" read -r -a time_array <<< "${time}"
    IFS="$ATTEMPT_SEP" read -r -a mem_array <<< "${mem}"

    # Return length of longest array
    if [ ${#time_array[@]} -gt ${#mem_array[@]} ]; then
        echo ${#time_array[@]}
    else
        echo ${#mem_array[@]}
    fi
}

########
get_mem_attempt_value()
{
    # Initialize variables
    local mem=$1
    local attempt_no=$2

    # Obtain array for memory limits
    local mem_array
    IFS="$ATTEMPT_SEP" read -r -a mem_array <<< "${mem}"

    # Return value for attempt
    local array_idx=$(( attempt_no - 1 ))
    local array_len=${#mem_array[@]}
    if [ ${array_idx} -lt  ${array_len} ]; then
        echo ${mem_array[${array_idx}]}
    else
        local last_array_idx=$(( array_len - 1 ))
        echo ${mem_array[${last_array_idx}]}
    fi
}

########
get_time_attempt_value()
{
    # Initialize variables
    local time=$1
    local attempt_no=$2

    # Obtain array for time limits
    local time_array
    IFS="$ATTEMPT_SEP" read -r -a time_array <<< "${time}"

    # Return value for attempt
    local array_idx=$(( attempt_no - 1 ))
    local array_len=${#time_array[@]}
    if [ ${array_idx} -lt ${array_len} ]; then
        echo ${time_array[${array_idx}]}
    else
        last_array_idx=$(( array_len - 1 ))
        echo ${time_array[${last_array_idx}]}
    fi
}

########
launch()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local processdeps=$6
    local outvar=$7

    # Launch process
    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER}) ## Launch using slurm
            slurm_launch "${dirname}" "${processname}" "${array_size}" "${task_array_list}" "${process_spec}" "${processdeps}" "${outvar}" || return 1
            ;;
    esac
}

########
get_primary_id()
{
    # Returns the primary id of a process. The primary id is the
    # job/process directly executing the process (additional jobs/processes
    # may be necessary to complete process execution)
    local launch_id_info=$1

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            get_primary_id_slurm "${launch_id_info}"
            ;;
        ${BUILTIN_SCHEDULER})
            echo "${launch_id_info}"
            ;;
    esac
}

########
get_global_id()
{
    # Returns the global id of a process. The global id is the job/process
    # registering the process as finished. It is only executed when all of
    # the others jobs/processes are completed
    local launch_id_info=$1

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            get_global_id_slurm "${launch_id_info}"
            ;;
        ${BUILTIN_SCHEDULER})
            echo "${launch_id_info}"
            ;;
    esac
}

########
pid_exists()
{
    local pid=$1

    kill -0 "$pid"  > /dev/null 2>&1 || return 1

    return 0
}

########
stop_pid()
{
    local pid=$1

    kill -9 "$pid"  > /dev/null 2>&1 || return 1

    return 0
}

########
id_exists()
{
    local id=$1

    # Check id depending on the scheduler
    local sched=`get_scheduler`
    local exit_code
    case $sched in
        ${SLURM_SCHEDULER})
            slurm_jid_exists "$id"
            exit_code=$?
            return "${exit_code}"
            ;;
        ${BUILTIN_SCHEDULER})
            pid_exists "$id"
            exit_code=$?
            return "${exit_code}"
        ;;
    esac
}

########
map_deptype_if_necessary()
{
    local deptype=$1

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            map_deptype_if_necessary_slurm "${deptype}"
            ;;
        *)
            echo "${deptype}"
            ;;
    esac
}


########
write_env_vars_and_funcs()
{
    write_debasher_env_vars_and_funcs()
    {
        # Write variables
        for conda_var in CONDA_EXE CONDA_PYTHON_EXE _CE_M _CE_CONDA; do
            declare -p "${conda_var}"
        done
        declare -p DEBASHER_SCHEDULER
        declare -p SLURM_SCHEDULER
        declare -p BUILTIN_SCHEDULER
        declare -p DISABLE_SCHEDULERS
        declare -p OPT_FILE_LINES_PER_BLOCK
        declare -p DEBASHER_SCRIPTS_DIRNAME
        declare -p PROGRAM_OUTDIR
        declare -p MOD_VARS_AND_FUNCS_BASENAME
        declare -p PROCESS_METHOD_NAME_OUTDIR
        declare -p VALUE_DESCRIPTOR_NAME_PREFIX
        declare -p FINISHED_PROCESS_FEXT
        declare -p PROCESSID_FEXT
        declare -p ARRAY_TASKID_FEXT
        declare -p STDOUT_FEXT
        declare -p ARG_SEP
        declare -p OPT_NOT_FOUND
        declare -p FUNCT_NOT_FOUND
        declare -p DEBASHER_LOG_ERROR_MSG_START
        declare -p DEBASHER_LOG_WARNING_MSG_START
        declare -p BASH
        declare -p BASENAME
        declare -p DIRNAME
        declare -p MKTEMP
        declare -p RM
        declare -p CAT
        declare -p HEAD
        declare -p TAIL
        declare -p AWK

        # Write functions
        for conda_func in __conda_activate __conda_exe __conda_hashr __conda_reactivate conda; do
            declare -f "${conda_func}"
        done
        declare -f pipe_fail
        declare -f get_process_finished_filename
        declare -f get_prg_scripts_dir
        declare -f get_prg_scripts_dir_for_process
        declare -f get_prg_scripts_dir_given_basedir
        declare -f read_opt_value_from_func_args
        declare -f get_opt_value_from_func_args
        declare -f str_is_val_descriptor
        declare -f write_value_to_desc
        declare -f read_value_from_desc
        declare -f str_is_output_option
        declare -f is_absolute_path
        declare -f read_value_from_desc
        declare -f get_nth_file_line
        declare -f get_file_opts_for_process_and_task
        declare -f deserialize_args
        declare -f deserialize_args_given_sep
        declare -f display_begin_process_message
        declare -f display_end_process_message
        declare -f default_reset_outfiles_for_process
        declare -f get_process_outdir_given_dirname
        declare -f get_default_process_outdir_given_dirname
        declare -f get_outdir_funcname
        declare -f process_function_outdir
        declare -f default_reset_outfiles_for_process_array
        declare -f get_prg_scripts_dir_given_basedir
        declare -f get_prg_scripts_dir_for_process
        declare -f get_process_stdout_filename
        declare -f search_process_func
        declare -f get_process_funcname
        declare -f remove_suffix_from_processname
        declare -f func_exists
        declare -f signal_process_completion
        declare -f get_scheduler
        declare -f exclude_readonly_vars
        declare -f init_bash_shebang_var
        declare -f write_env_vars_and_funcs
        declare -f get_mod_vars_and_funcs_fname
        declare -f seq_execute
        declare -f logmsg
        declare -f get_script_log_filenames
        declare -f filter_warnings_in_script_log_file
        declare -f filter_errors_in_script_log_file
        declare -f create_script_log_file_errwarn_entry
        declare -f filter_errwarns_in_script_log_files_pref
    }

    write_mod_env_vars_and_funcs()
    {
        local dirname=$1

        local vars_and_funcs_fname=`get_mod_vars_and_funcs_fname "${dirname}"`
        "${CAT}" "${vars_and_funcs_fname}"
    }

    local dirname=$1

    # Write Debasher-related variables and functions
    write_debasher_env_vars_and_funcs

    # Write module-related variables and functions
    write_mod_env_vars_and_funcs "${dirname}"
}

########
seq_execute()
{
    local sched=`get_scheduler`

    case $sched in
        ${SLURM_SCHEDULER})
            seq_execute_slurm "$@"
            ;;
        ${BUILTIN_SCHEDULER})
            seq_execute_builtin "$@"
            ;;
        *)
            local process_to_launch=$1
            # Execute process
            shift
            "${process_to_launch}" "$@" || return 1
            ;;
    esac
}
