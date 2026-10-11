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

##########################################
# SCHEDULER FUNCTIONS RELATED TO BUILTIN #
##########################################

########
# The start time of the process with id $1, with no blanks and in a form
# that depends neither on the locale nor on the time zone of whoever asks,
# so that the one recorded when a task is launched compares with the one
# read later by any tool. Fails when there is no such process, or no ps to
# ask.
debasher::_builtin_sched_pid_start_time()
{
    local pid=$1

    local start
    start=$(LC_ALL=C TZ=UTC0 "${PS}" -o lstart= -p "${pid}" 2> /dev/null) || return 1

    # Squeeze the blanks, the day of the month being padded with one
    local -a words
    read -r -a words <<< "${start}"
    [ ${#words[@]} -gt 0 ] || return 1
    local IFS="_"
    echo "${words[*]}"
}

########
# The id of a task that the built-in scheduler launched as process $1, as
# its .id file keeps it: "<pid>@<start time>". A process id alone does not
# name the task for good: once the task has ended, the system may give the
# same id to another process, which would then be taken for the task, as
# running and as what to stop. The start time tells them apart. Without ps
# to ask, the id is the process id alone; a process that has already ended
# when its start time is read gets an empty one, and is never taken for a
# running task.
debasher::_builtin_sched_launch_id_info()
{
    local pid=$1

    local start
    if start=$(debasher::_builtin_sched_pid_start_time "${pid}"); then
        echo "${pid}@${start}"
    elif kill -0 "${pid}" > /dev/null 2>&1; then
        echo "${pid}"
    else
        echo "${pid}@"
    fi
}

########
# Echoes the process id of the task that the id $1 names (see
# debasher::_builtin_sched_launch_id_info) if it still runs, and fails
# otherwise: a process with that id exists, can be signalled by this user
# and, when the id has a start time, started at that time. A start time
# that cannot be read now, with no ps to ask, leaves the process id alone
# to decide, as does an id without one.
debasher::_builtin_sched_live_pid()
{
    local id_info=$1

    local pid=${id_info%%@*}
    kill -0 "${pid}" > /dev/null 2>&1 || return 1

    if [ "${id_info}" != "${pid}" ]; then
        local recorded=${id_info#*@}
        [ -n "${recorded}" ] || return 1
        local current
        if current=$(debasher::_builtin_sched_pid_start_time "${pid}"); then
            [ "${current}" = "${recorded}" ] || return 1
        fi
    fi

    echo "${pid}"
}

########
debasher::_builtin_sched_id_exists()
{
    local id_info=$1

    debasher::_builtin_sched_live_pid "${id_info}" > /dev/null
}

########
# Stops the tasks of a process that still run, among those that the ids in
# $1 name: the ids of the tasks that have ended are left alone, since their
# process ids may now belong to other processes.
debasher::_builtin_sched_stop_process()
{
    # Initialize variables
    local ids_info=$1

    local id pid
    for id in ${ids_info}; do
        pid=$(debasher::_builtin_sched_live_pid "${id}") || continue
        debasher::_stop_pid "${pid}" || { echo "Error while stopping process with id ${pid}" >&2 ; return 1; }
    done
}

########
debasher::_process_is_unfinished_but_runnable_builtin_sched()
{
    # Processes where the following is true are assigned this status:
    #  - process is an array of tasks
    #  - there are no tasks in progres (otherwise, it would be an in-progress process)
    #  - at least one task has been launched or cancelled
    #  - at least one task has been neither, and can start execution

    local dirname=$1
    local processname=$2

    # Get .id files of launched tasks
    local ids=$(debasher::_get_launched_array_task_ids "$dirname" $processname)
    local -A launched_array_tids
    local id
    for id in ${ids}; do
        launched_array_tids[${id}]=1
    done

    # A cancelled task counts with the launched ones
    local num_launched_tasks=${#launched_array_tids[@]}
    local num_cancelled_tasks=$(debasher::_get_num_array_tasks_cancelled "${dirname}" "${processname}")
    local num_handled_tasks=$((num_launched_tasks + num_cancelled_tasks))

    # If no array task was launched or cancelled, process is not array or
    # it is not an unfinished one
    if [ ${num_handled_tasks} -eq 0 ]; then
        return 1
    else
        # Process is array with some tasks already launched or cancelled

        # Check that not all array tasks were launched or cancelled,
        # whether or not any of them has finished: an array whose every
        # task was launched or cancelled, and some failed or were
        # cancelled, is not runnable, and the scheduler takes it as failed
        local num_array_tasks=$(debasher::_get_num_array_tasks "${dirname}" "${processname}")
        if [ ${num_handled_tasks} -ge ${num_array_tasks} ]; then
            return 1
        fi

        # Check there are no tasks in progress
        for id in ${!launched_array_tids[@]}; do
            if debasher::_id_exists $id; then
                return 1
            fi
        done

        # All conditions satisfied
        return 0
    fi
}

########
debasher::_get_elapsed_time_for_process_builtin()
{
    local dirname=$1
    local processname=$2

    # Obtain number of tasks completed
    local num_tasks_completed=$(debasher::_get_num_tasks_completed "${dirname}" ${processname})

    if [ "${num_tasks_completed}" -gt 0 ]; then
        # Get number of array tasks
        local num_tasks=$(debasher::_get_num_array_tasks "${dirname}" "${processname}")
        case $num_tasks in
            0)  echo ${DEBASHER_UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
                ;;
            1)  # Process is not a task array
                log_filename=$(debasher::_get_process_log_filename "${dirname}" ${processname})
                local difft=$(debasher::_get_elapsed_time_from_logfile "${log_filename}")
                echo ${difft}
                ;;
            *)  # Process is a task array
                debasher::_get_elapsed_time_for_array_process "${dirname}" "${processname}" debasher::_get_task_log_filename
                ;;
        esac
    else
        echo ${DEBASHER_UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
    fi
}

########
debasher::_seq_execute_builtin()
{
    local process_to_launch=$1

    # Execute process
    shift
    "${process_to_launch}" "$@" || return 1
}
