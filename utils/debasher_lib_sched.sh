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
    local cmdline=$1
    local dirname=$2
    local processname=$3
    local opt_array_size=$4

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            create_slurm_script "${cmdline}" "${dirname}" "$processname" "${opt_array_size}"
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
            slurm_id_exists "$id"
            exit_code=$?
            return "${exit_code}"
            ;;
        ${BUILTIN_SCHEDULER})
            builtin_sched_id_exists "$id"
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
        local dirname=$1

        # Write DeBasher start variables and functions
        local vars_and_funcs_fname=`get_deblib_vars_and_funcs_fname "${dirname}"`
        "${CAT}" "${vars_and_funcs_fname}"

        # Write initialized variables
        declare -p DEBASHER_SCHEDULER
        declare -p INITIAL_PROCESS_SPEC
        declare -p PROGRAM_OUTDIR
        declare -p MEMOIZED_OPTS
        declare -p OUT_VALUE_TO_PROCESSES
    }

    write_mod_env_vars_and_funcs()
    {
        local dirname=$1

        local vars_and_funcs_fname=`get_mod_vars_and_funcs_fname "${dirname}"`
        "${CAT}" "${vars_and_funcs_fname}"
    }

    local dirname=$1

    # Write Debasher-related variables and functions
    write_debasher_env_vars_and_funcs "${dirname}"

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
