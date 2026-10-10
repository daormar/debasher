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

# Each task of an array that reads what the task with the same index of
# another array wrote depends on that task alone (aftercorr), not on the
# whole of the other array. "first" and "second" have one task per number
# from 0 to n-1, with n at least 2. Each task of "first" writes its number
# into a file, and the task of "second" with the same index copies it into
# its shared subdirectory "signals/<task index>". The first task of "first"
# shows the dependency at work: it ends only once the last task of "second"
# has left its copy in the shared directory, which that task can do only
# while the first task of "first" still runs. A scheduler that made every
# task of "second" wait for the whole of "first" would never let it, and
# the first task of "first" fails after waiting for a minute. It reads the
# whole shared directory, which gives it no dependency on "second".

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_aftercorr_example_document()
{
    document_module "This module implements a program in which each task of an array waits only for the task with the same index of another array."
}

########
debasher_aftercorr_example_shared_dirs()
{
    define_shared_dir "signals"
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
first_document()
{
    document_process "Executes one task per number from 0 to n-1. Each task writes its number into a file; the first one also waits for the last task of second to leave its copy in the shared directory."
}

########
first_explain_opts()
{
    # -num option
    local description="number of the task"
    explain_opt "-num" "<int>" "$description"

    # -last option
    local description="index of the last task of second"
    explain_opt "-last" "<int>" "$description"

    # -sigd option
    local description="shared directory where the tasks of second leave their copies"
    explain_opt "-sigd" "<dir>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
first_explain_task_shaping_opts()
{
    # -n option
    local description="Number of tasks, at least 2."
    explain_task_shaping_opt "-n" "<int>" "$description"
}

########
first_identify_cmdline_opts()
{
    :
}

########
first_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    debasher::read_opt_value_from_line "${cmdline}" "-n"
}

########
first_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # -num option
    define_opt "-num" "${task_idx}" optlist || return 1

    # -last option
    local n=$(debasher::read_opt_value_from_line "${cmdline}" "-n")
    define_opt "-last" "$((n - 1))" optlist || return 1

    # -sigd option: the whole shared directory, not a shared subdirectory
    # that a task of second writes, so that it makes no dependency on them
    define_opt_from_shared_dir "-sigd" "signals" optlist || return 1

    # -outf option
    define_opt "-outf" "${process_outdir}/${task_idx}.txt" optlist || return 1

    save_opt_list optlist
}

########
first()
{
    # Initialize variables
    local num=$(read_opt_value_from_func_args "-num" "$@")
    local last=$(read_opt_value_from_func_args "-last" "$@")
    local sigd=$(read_opt_value_from_func_args "-sigd" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    echo "${num}" > "${outf}"

    # The first task waits for the copy of the last task of second, which
    # only starts once the last task of first has finished
    if [ "${num}" -eq 0 ]; then
        local i
        for i in $(seq 60); do
            [ -f "${sigd}/${last}/copy.txt" ] && return 0
            sleep 1
        done
        echo "Error: the last task of second did not run while the first task of first was running" >&2
        return 1
    fi
}

########
second_document()
{
    document_process "Executes one task per number from 0 to n-1. Each task copies what the task of first with the same index wrote into its own directory below the shared directory."
}

########
second_explain_opts()
{
    # -inf option
    local description="file written by the task of first with the same index"
    explain_opt "-inf" "<file>" "$description"

    # -outd option
    local description="directory of the task, below the shared directory"
    explain_opt "-outd" "<dir>" "$description"
}

########
second_explain_task_shaping_opts()
{
    # -n option
    local description="Number of tasks, at least 2."
    explain_task_shaping_opt "-n" "<int>" "$description"
}

########
second_identify_cmdline_opts()
{
    :
}

########
second_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    debasher::read_opt_value_from_line "${cmdline}" "-n"
}

########
second_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # -inf option: the output of the task of first with the same index,
    # which makes the aftercorr dependency
    define_opt_from_proc_task_out "-inf" "first" "${task_idx}" "-outf" optlist || return 1

    # -outd option: a directory of the task's own below the shared
    # directory
    define_opt_from_shared_dir "-outd" "signals" optlist --subdir "${task_idx}" || return 1

    save_opt_list optlist
}

########
second()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    cp "${inf}" "${outd}/copy.txt"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_aftercorr_example_program()
{
    add_debasher_process "first"  "cpus=1 mem=32 time=00:02:00"
    add_debasher_process "second" "cpus=1 mem=32 time=00:02:00"
}
