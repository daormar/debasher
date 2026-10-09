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

# The tasks of a process that write into a shared directory each get a
# directory of their own below it, and a process that gathers what every
# task wrote reads all of them. "square" is an option generator with one
# task per number from 0 to n-1: each task receives its number (the data
# of its work, which happens to be its task index) and writes its square
# into a file of a fixed name, square.txt, in its shared subdirectory
# "squares/<task index>", which the engine creates before the task runs.
# "total" reads the shared subdirectory of every task through a fanout
# family, "-indith", one option per task: since each of those options
# holds the path of an output of one task, "total" also waits for every
# task of "square" to finish.

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_shared_subdir_example_document()
{
    document_module "This module implements a program whose tasks each write into a directory of their own below a shared directory, and a process that gathers what all of them wrote."
}

########
debasher_shared_subdir_example_shared_dirs()
{
    define_shared_dir "squares"
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
square_document()
{
    document_process "Executes one task per number from 0 to n-1. Each task writes the square of its number into a directory of its own below the shared directory."
}

########
square_explain_opts()
{
    # -num option
    local description="number to square"
    explain_opt "-num" "<int>" "$description"

    # -outd option
    local description="directory of the task, below the shared directory"
    explain_opt "-outd" "<file>" "$description"
}

########
square_explain_task_shaping_opts()
{
    # -n option
    local description="Number of numbers to square."
    explain_task_shaping_opt "-n" "<int>" "$description"
}

########
square_identify_cmdline_opts()
{
    :
}

########
square_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    debasher::read_opt_value_from_line "${cmdline}" "-n"
}

########
square_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # -num option: the number of the task, the data of its work
    define_opt "-num" "${task_idx}" optlist || return 1

    # -outd option: a directory of the task's own below the shared
    # directory, which the engine creates before the task runs
    define_opt_from_shared_dir "-outd" "squares" optlist --subdir "${task_idx}" || return 1

    save_opt_list optlist
}

########
square()
{
    # Initialize variables
    local num=$(read_opt_value_from_func_args "-num" "$@")
    local outd=$(read_opt_value_from_func_args "-outd" "$@")

    # Write the square of the number, under the same name in every task
    echo $(( num * num )) > "${outd}/square.txt"
}

########
total_document()
{
    document_process "Adds up the squares that every task of square wrote."
}

########
total_explain_opts()
{
    # -n option
    local description="Number of numbers to square."
    explain_opt "-n" "<int>" "$description"

    # -indith option
    local description="i'th directory of a task of square"
    explain_opt "-indith" "<file>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
total_identify_cmdline_opts()
{
    opt_is_cmdline "-n"
}

########
total_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -n option
    define_cmdline_opt "$cmdline" "-n" optlist || return 1

    # -indith options: the shared subdirectory of every task of square
    local n=$(debasher::read_opt_value_from_line "${cmdline}" "-n")
    for ((i=0; i<n; i++)); do
        define_opt_from_proc_task_out "-ind${i}" "square" "${i}" "-outd" optlist || return 1
    done

    # -outf option
    define_opt "-outf" "${process_outdir}/total.txt" optlist || return 1

    save_opt_list optlist
}

########
total()
{
    # Initialize variables
    local n=$(read_opt_value_from_func_args "-n" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Add up the square that each task wrote into its own directory
    local sum=0
    local i
    for ((i=0; i<n; i++)); do
        local ind=$(read_opt_value_from_func_args "-ind${i}" "$@")
        sum=$(( sum + $(cat "${ind}/square.txt") ))
    done
    echo "${sum}" > "${outf}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_shared_subdir_example_program()
{
    add_debasher_process "square" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "total"  "cpus=1 mem=32 time=00:01:00"
}
