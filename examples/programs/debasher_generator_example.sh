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

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_generator_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
array_writer_document()
{
    process_description "Executes an array of 4 tasks. Each task creates a file containing the task index."
}

########
array_writer_explain_cmdline_opts()
{
    # -c option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-c" "<int>" "$description"
}

########
array_writer_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    echo 4
}

########
array_writer_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # -id option
    define_opt "-id" $task_idx optlist || return 1

    # -outf option
    define_opt "-outf" "${process_outdir}/${task_idx}" optlist || return 1

    save_opt_list optlist
}

########
array_writer()
{
    # Initialize variables
    local sleep_time=$(read_opt_value_from_func_args "-c" "$@")
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Sleep some time
    sleep ${sleep_time}

    # Create file
    echo $id > "${outf}"
}

########
array_writer_reset_outfiles()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Remove output file
    if [ -f "${outf}" ]; then
        rm "${outf}"
    fi
}

########
array_reader_explain_cmdline_opts()
{
    :
}

########
array_reader_generate_opts_size()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    echo 4
}

########
array_reader_generate_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local task_idx=$5
    local optlist=""

    # -id option
    define_opt "-id" $task_idx optlist || return 1

    # -infile option
    define_opt_from_proc_task_out "-infile" "array_writer" "${task_idx}" "-outf" optlist || return 1

    # -outdir option
    define_opt "-outdir" "${process_outdir}" optlist || return 1

    save_opt_list optlist
}

########
array_reader()
{
    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local infile=$(read_opt_value_from_func_args "-infile" "$@")
    local outd=$(read_opt_value_from_func_args "-outdir" "$@")

    # Copy content of infile to auxiliary file
    cat "${infile}" > "${outd}"/${id}_aux

    # Copy content of infile to final file
    cat "${outd}"/${id}_aux > "${outd}"/${id}
}

########
array_reader_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=$(read_opt_value_from_func_args "-id" "$@")
    local outd=$(read_opt_value_from_func_args "-outdir" "$@")

    # Remove auxiliary file
    rm "${outd}"/${id}_aux

    logmsg "Cleaning finished"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_generator_example_program()
{
    add_debasher_process "array_writer" "cpus=1 mem=32 time=00:01:00,00:02:00 throttle=2"
    add_debasher_process "array_reader" "cpus=1 mem=32 time=00:01:00 throttle=4"
}
