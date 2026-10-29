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

############################################
# SCHEDULER FUNCTIONS RELATED TO PROCESSES #
############################################

########
debasher::_get_processid_filename()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    echo "${execdir}/$processname.${DEBASHER_PROCESSID_FEXT}"
}

########
debasher::_get_array_taskid_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get exec dir
    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    echo "${execdir}/${processname}_${idx}.${DEBASHER_ARRAY_TASKID_FEXT}"
}

########
debasher::_get_array_taskid()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    file=$(debasher::_get_array_taskid_filename "${dirname}" ${processname} ${idx})
    if [ -f "${file}" ]; then
        "${CAT}" "$file"
    else
        echo ${DEBASHER_INVALID_ARRAY_TID}
    fi
}

########
debasher::_get_process_finished_filename_prefix()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    echo "${execdir}/${processname}"
}

########
debasher::_get_process_finished_filename()
{
    local dirname=$1
    local processname=$2

    # Get prefix
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")

    echo "${prefix}.${DEBASHER_FINISHED_PROCESS_FEXT}"
}

########
debasher::_get_task_finished_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get prefix
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")

    echo "${prefix}_${idx}.${DEBASHER_FINISHED_PROCESS_FEXT}"
}

########
# The cancellation marker of a process with a single task, which the
# built-in scheduler writes when the task will not be launched in the run
# because its dependencies can no longer hold
debasher::_get_process_cancelled_filename()
{
    local dirname=$1
    local processname=$2

    # Get prefix
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")

    echo "${prefix}.${DEBASHER_CANCELLED_TASK_FEXT}"
}

########
# The cancellation marker of the task with the given index of an array
# process (see debasher::_get_process_cancelled_filename)
debasher::_get_task_cancelled_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get prefix
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")

    echo "${prefix}_${idx}.${DEBASHER_CANCELLED_TASK_FEXT}"
}

########
# Writes the cancellation marker of a task, with the cause that keeps it
# from being launched: the dependency that can no longer hold, or the
# cancelled task at the other end of one of its fifos
debasher::_signal_task_cancellation()
{
    local dirname=$1
    local processname=$2
    local idx=$3
    local num_tasks=$4
    local cause=$5

    local cancelled_filename
    if [ "${num_tasks}" -eq 1 ]; then
        cancelled_filename=$(debasher::_get_process_cancelled_filename "${dirname}" "${processname}")
    else
        cancelled_filename=$(debasher::_get_task_cancelled_filename "${dirname}" "${processname}" "${idx}")
    fi
    echo "Cancelled task idx: ${idx} ; Total: ${num_tasks} ; Cause: ${cause}" > "${cancelled_filename}"
}

########
# Removes the cancellation markers of a process, so that its cancelled
# tasks are launched in the run that prepares it
debasher::_reset_task_cancellations()
{
    local dirname=$1
    local processname=$2

    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")
    "${RM}" -f "${prefix}.${DEBASHER_CANCELLED_TASK_FEXT}" "${prefix}"_*.${DEBASHER_CANCELLED_TASK_FEXT}
}

########
# The number of cancelled tasks of an array process
debasher::_get_num_array_tasks_cancelled()
{
    local dirname=$1
    local processname=$2
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")

    local num_tasks_cancelled=0
    local file
    for file in "${prefix}"_*.${DEBASHER_CANCELLED_TASK_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks_cancelled=$((num_tasks_cancelled + 1))
        fi
    done

    echo "${num_tasks_cancelled}"
}

########
debasher::_get_list_of_pending_tasks_in_array()
{
    # NOTE: a pending task here is just one that is not finished
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Create associative map containing completed jobs
    local -A completed_tasks
    local finished_filename_pref=$(debasher::_get_process_finished_filename_prefix "${dirname}" ${processname})
    local file
    for file in "${finished_filename_pref}"_*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$DEBASHER_FINISHED_PROCESS_FEXT}"
            completed_tasks[${id}]="1"
        fi
    done

    # Create string enumerating pending tasks
    local pending_tasks=""
    local idx=0
    while [ $idx -lt ${array_size} ]; do
        if [ -z "${completed_tasks[${idx}]}" ]; then
            if [ -z "${pending_tasks}" ]; then
                pending_tasks=${idx}
            else
                pending_tasks="${pending_tasks},${idx}"
            fi
        fi
        idx=$((idx + 1))
    done

    echo ${pending_tasks}
}

########
# The number of tasks of a process, from the header of its process script
# (its DEBASHER_NUM_TASKS line), so that it is known whether or not any task
# has finished; 0 when the process has no script, never having been launched
debasher::_get_num_array_tasks()
{
    local dirname=$1
    local processname=$2
    local script_filename=$(debasher::_get_script_filename "${dirname}" ${processname})

    local num_tasks=0
    if [ -f "${script_filename}" ]; then
        local line
        line=$("${GREP}" -m1 "^DEBASHER_NUM_TASKS=" "${script_filename}")
        if [ -n "${line}" ]; then
            num_tasks=${line#DEBASHER_NUM_TASKS=}
        fi
    fi

    echo "${num_tasks}"
}

########
debasher::_get_num_tasks_completed()
{
    local dirname=$1
    local processname=$2
    local finished_filename_pref=$(debasher::_get_process_finished_filename_prefix "${dirname}" ${processname})

    local num_tasks_completed=0
    for file in "${finished_filename_pref}"*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            num_tasks_completed=$((num_tasks_completed + 1))
        fi
    done

    echo "${num_tasks_completed}"
}

########
debasher::_get_task_array_list()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local num_completed_tasks=$(debasher::_get_num_tasks_completed "${dirname}" "${processname}")
    if [ "${num_completed_tasks}" -eq 0 ]; then
        # No tasks were completed, return list containing all of them
        local last_task_idx=$((array_size - 1))
        echo "0-${last_task_idx}"
    else
        # Some tasks were completed, return list containing pending ones
        debasher::_get_list_of_pending_tasks_in_array "${dirname}" "${processname}" "${array_size}"
    fi
}

########
# Prepares a process to run again: takes away its ids, of the process and of
# its tasks, and then its completion markers. In that order, a reading of its
# status in between finds it FINISHED or TO-DO, and never launched and
# unfinished, with the ids of the run before and no completion marker
debasher::_reset_process_completion_signal()
{
    local dirname=$1
    local processname=$2

    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")
    "${RM}" -f "$(debasher::_get_processid_filename "${dirname}" "${processname}")" \
          "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}

    local finished_filename_pref=$(debasher::_get_process_finished_filename_prefix "${dirname}" ${processname})
    "${RM}" -f "${finished_filename_pref}"*.${DEBASHER_FINISHED_PROCESS_FEXT}
}

########
# Removes what an earlier run left in the exec directory of a process that
# is about to be launched, under the Slurm scheduler. The built-in
# scheduler does it in its own loop
# (debasher_builtin_sched::_clean_process_files), so this does nothing for
# it
debasher::_clean_process_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            debasher::_clean_process_files_slurm "$dirname" "$processname" "$array_size"
            ;;
    esac
}

########
debasher::_write_process_id_info_to_file()
{
    local dirname=$1
    local processname=$2
    local id_info=$3
    local filename=$(debasher::_get_processid_filename "${dirname}" ${processname})

    echo ${id_info} > "$filename"
}

########
debasher::_read_process_id_info_from_file()
{
    local dirname=$1
    local processname=$2

    # Return id for process
    local filename=$(debasher::_get_processid_filename "${dirname}" ${processname})
    if [ -f "$filename" ]; then
        "${CAT}" "$filename"
    else
        echo ${DEBASHER_INVALID_SID}
    fi
}

########
debasher::_read_ids_from_files()
{
    local dirname=$1
    local processname=$2
    local ids

    # Return id for process
    local filename=$(debasher::_get_processid_filename "${dirname}" ${processname})
    if [ -f "$filename" ]; then
        ids=$("${CAT}" "$filename")
    fi

    # Get exec dir
    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    # Return ids for array tasks if any
    local id
    for taskid_file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            id=$("${CAT}" "${taskid_file}")
            if [ -z "${ids}" ]; then
                ids=$id
            else
                ids="${ids} ${id}"
            fi
        fi
    done

    echo ${ids}
}

########
debasher::_signal_process_completion()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local idx=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        local finished_filename=$(debasher::_get_process_finished_filename "${dirname}" ${processname})
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    else
        local finished_filename=$(debasher::_get_task_finished_filename "${dirname}" ${processname} ${idx})
        echo "Finished task idx: $idx ; Total: $total" > "${finished_filename}"
    fi
}

########
debasher::_get_signal_process_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local taskidx_varname=$3
    local total=$4

    # Signal completion
    if [ ${total} -eq 1 ]; then
        echo "echo \"Finished task idx: 0 ; Total: $total\" > $(debasher::_get_process_finished_filename "${dirname}" ${processname})"
    else
        echo "echo \"Finished task idx: \${${taskidx_varname}} ; Total: $total\" > \$(debasher::_get_task_finished_filename \"${dirname}\" ${processname} \${${taskidx_varname}})"
    fi
}

########
debasher::_stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Launch process
    local sched=$(debasher::_get_scheduler)
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER}) ## Launch using slurm
            debasher::_slurm_stop_process "${ids_info}" || return 1
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_builtin_sched_stop_process "${ids_info}" || return 1
            ;;
    esac
}

########
# Echoes the ids of a process that may still run: those of its tasks that
# have no completion marker, and the id of the process as a whole while it
# has not finished. The id of a task that has its completion marker is left
# out: the task has ended, and its id may name another process by now, as a
# process id that the system gave again does when the scheduler cannot tell
# them apart (see debasher::_builtin_sched_live_pid).
debasher::_read_ids_of_unfinished_tasks()
{
    local dirname=$1
    local processname=$2

    # The id of the process as a whole
    local filename=$(debasher::_get_processid_filename "${dirname}" "${processname}")
    if [ -f "${filename}" ] && ! debasher::_process_is_finished "${dirname}" "${processname}"; then
        "${CAT}" "${filename}"
    fi

    # The ids of the tasks of an array
    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")
    local taskid_file idx
    for taskid_file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}; do
        [ -f "${taskid_file}" ] || continue
        idx=${taskid_file#"${execdir}/${processname}_"}
        idx=${idx%".${DEBASHER_ARRAY_TASKID_FEXT}"}
        debasher::_array_task_is_finished "${dirname}" "${processname}" "${idx}" && continue
        "${CAT}" "${taskid_file}"
    done
}

########
# Whether some id of a process that may still run (see
# debasher::_read_ids_of_unfinished_tasks) still runs
debasher::_process_is_in_progress()
{
    local dirname=$1
    local processname=$2

    local id
    for id in $(debasher::_read_ids_of_unfinished_tasks "${dirname}" "${processname}"); do
        # Get global id (when executing multiple attempts, multiple ids
        # will be associated to a given process)
        local global_id=$(debasher::_get_global_id "${id}")
        if debasher::_id_exists "${global_id}"; then
            return 0
        fi
    done

    return 1
}

########
debasher::_get_launched_array_task_ids()
{
    local dirname=$1
    local processname=$2

    # Get exec dir
    execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")

    # Return ids for array tasks if any
    local taskid_file
    for taskid_file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            "${CAT}" "${taskid_file}"
        fi
    done

}

########
debasher::_get_finished_array_task_indices()
{
    local dirname=$1
    local processname=$2

    local finished_filename_pref=$(debasher::_get_process_finished_filename_prefix "${dirname}" ${processname})
    local file
    for file in "${finished_filename_pref}"_*.${DEBASHER_FINISHED_PROCESS_FEXT}; do
        if [ -f "${file}" ]; then
            local temp="${file#${finished_filename_pref}_}"
            local id="${temp%.$DEBASHER_FINISHED_PROCESS_FEXT}"
            echo ${id}
        fi
    done
}

########
debasher::_array_task_is_finished()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Check if finished task file exists
    local finished_filename=$(debasher::_get_task_finished_filename "${dirname}" ${processname} "${idx}")
    if [ ! -f "${finished_filename}" ]; then
        return 1
    fi
}

########
debasher::_process_is_finished()
{
    local dirname=$1
    local processname=$2

    local num_tasks_completed=$(debasher::_get_num_tasks_completed "${dirname}" "${processname}")

    if [ "${num_tasks_completed}" -eq 0 ]; then
        return 1
    else
        local num_tasks=$(debasher::_get_num_array_tasks "${dirname}" "${processname}")
        if [ "${num_tasks_completed}" -eq "${num_tasks}" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
debasher::_process_is_unfinished_but_runnable()
{
    local dirname=$1
    local processname=$2

    # Check status depending on the scheduler
    local sched=$(debasher::_get_scheduler)
    local exit_code
    case $sched in
        ${DEBASHER_SLURM_SCHEDULER})
            # DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS status is not
            # considered for SLURM scheduler, since task arrays are
            # executed as a single job
            return 1
            ;;
        ${DEBASHER_BUILTIN_SCHEDULER})
            debasher::_process_is_unfinished_but_runnable_builtin_sched "${dirname}" "${processname}"
            exit_code=$?
            return ${exit_code}
        ;;
    esac
}

########
# Whether some task of a process has been launched or cancelled: it has an
# id, of the process or of a task, or a cancellation marker. A process
# script with neither is that of a process prepared to be launched and not
# launched yet
debasher::_process_was_launched_or_cancelled()
{
    local dirname=$1
    local processname=$2

    [ -f "$(debasher::_get_processid_filename "${dirname}" "${processname}")" ] && return 0

    local execdir=$(debasher::_get_prg_exec_dir_for_process "${dirname}" "${processname}")
    local prefix=$(debasher::_get_process_finished_filename_prefix "${dirname}" "${processname}")
    local file
    for file in "${execdir}"/${processname}_*.${DEBASHER_ARRAY_TASKID_FEXT} \
                "${prefix}.${DEBASHER_CANCELLED_TASK_FEXT}" "${prefix}"_*.${DEBASHER_CANCELLED_TASK_FEXT}; do
        [ -f "${file}" ] && return 0
    done

    return 1
}

########
debasher::_get_process_status()
{
    local dirname=$1
    local processname=$2
    local script_filename=$(debasher::_get_script_filename "${dirname}" ${processname})

    if [ -f "${script_filename}" ]; then
        # Prepared and not launched yet: the scheduler writes the process
        # script before it launches the process, and a new run takes the
        # ids away from a process that it runs again before relaunching it.
        # Asked first, so that an id written while the status is read
        # makes the process launched for every question that follows
        if ! debasher::_process_was_launched_or_cancelled "$dirname" "$processname" \
                && ! debasher::_process_is_finished "$dirname" "$processname"; then
            echo "${DEBASHER_TODO_PROCESS_STATUS}"
            return ${DEBASHER_TODO_PROCESS_EXIT_CODE}
        fi

        if debasher::_process_is_in_progress "$dirname" "$processname"; then
            echo "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
            return ${DEBASHER_INPROGRESS_PROCESS_EXIT_CODE}
        fi

        if debasher::_process_is_finished "$dirname" "$processname"; then
            echo "${DEBASHER_FINISHED_PROCESS_STATUS}"
            return ${DEBASHER_FINISHED_PROCESS_EXIT_CODE}
        else
            if debasher::_process_is_unfinished_but_runnable "$dirname" "$processname"; then
                echo "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}"
                return ${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_EXIT_CODE}
            fi
        fi

        echo "${DEBASHER_UNFINISHED_PROCESS_STATUS}"
        return ${DEBASHER_UNFINISHED_PROCESS_EXIT_CODE}
    else
        echo "${DEBASHER_TODO_PROCESS_STATUS}"
        return ${DEBASHER_TODO_PROCESS_EXIT_CODE}
    fi
}
