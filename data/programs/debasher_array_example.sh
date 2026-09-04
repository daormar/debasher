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

# Same scenario as debasher_array_example.sh (an array of 4 writer/reader
# tasks), but each _define_opts follows the frontend's "array" option
# handler convention instead of a hand-rolled loop: a fixed-name array
# ("array") built by user code, looped over with a fixed index ("idx").
# This is the exact shape api/script_generation.py's _add_array_opts_func
# emits and api/option_handler_import.py's _parse_array_define_opts
# recovers, so importing this file resolves both processes to "array"
# mode in the app rather than falling back to "manual".

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_array_example_ui_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
array_writer_document()
{
    document_process "Executes an array of 4 tasks. Each task creates a file containing the task index."
}

########
array_writer_explain_opts()
{
    # -c option
    local description="Sleep time in seconds"
    explain_opt "-c" "<int>" "$description"

    # -id option
    local description="id of writer"
    explain_opt "-id" "<int>" "$description"

    # -outf option
    local description="output file of writer"
    explain_opt "-outf" "<file>" "$description"
}

########
array_writer_identify_cmdline_opts()
{
    opt_is_cmdline "-c"
}

########
array_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # Array of task ids: the simplest case, where each element is just
    # its own index
    array=(0 1 2 3)

    for idx in "${!array[@]}"; do
        local optlist=""

        # -c option (its value never depends on idx, but every option is
        # still defined once per iteration — the app's array mode always
        # re-emits every option's call inside the loop, rather than
        # hoisting idx-independent ones out of it)
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # -id option
        define_opt "-id" "${array[$idx]}" optlist || return 1

        # -outf option
        define_opt "-outf" "${process_outdir}/${idx}" optlist || return 1

        # Save option list
        save_opt_list optlist
    done
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
array_reader_document()
{
    document_process "Reads each array_writer task's output file and copies its content to the reader's own output file."
}

########
array_reader_explain_opts()
{
    # -id option
    local description="id of reader"
    explain_opt "-id" "<int>" "$description"

    # -outdir option
    local description="output directory of reader"
    explain_opt "-outdir" "<file>" "$description"
}

########
array_reader_identify_cmdline_opts()
{
    :
}

########
array_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    array=(0 1 2 3)

    for idx in "${!array[@]}"; do
        local optlist=""

        # -id option
        define_opt "-id" "${array[$idx]}" optlist || return 1

        # -infile option: connected to array_writer's own task idx
        define_opt_from_proc_task_out "-infile" "array_writer" "${idx}" "-outf" optlist || return 1

        # -outdir option
        define_opt "-outdir" "${process_outdir}" optlist || return 1

        # Save option list
        save_opt_list optlist
    done
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
debasher_array_example_ui_program()
{
    add_debasher_process "array_writer" "cpus=1 mem=32 time=00:01:00,00:02:00 throttle=2"
    add_debasher_process "array_reader" "cpus=1 mem=32 time=00:01:00 throttle=4"
}
