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
debasher_file_example_document()
{
    module_description "This module implements a simple program with two processes, one writes a string to a file and the other one reads it and prints it to the standard output."
}

########
debasher_file_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
file_writer_document()
{
    process_description "Prints a string to a file."
}

########
file_writer_explain_cmdline_opts()
{
    # -s option
    local description="String to be displayed"
    explain_cmdline_opt "-s" "<string>" "$description"
}

########
file_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -s option
    define_cmdline_opt "$cmdline" "-s" optlist || return 1

    # Define option for output file
    local filename="${process_outdir}/out.txt"
    define_opt "-outf" "${filename}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
file_writer()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Write string to file
    echo "Hello World" > "${outf}"
}

########
file_reader_document()
{
    process_description "Reads a string from a file."
}

########
file_reader_explain_cmdline_opts()
{
    :
}

########
file_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input file
    define_opt_from_proc_out "-inf" "file_writer" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
file_reader()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Read string from file
    cat < "${inf}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_file_example_program()
{
    add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "file_reader" "cpus=1 mem=32 time=00:01:00"
}
