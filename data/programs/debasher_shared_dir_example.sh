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

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_shared_dir_example_document()
{
    document_module "This module implements a simple program with two processes, one writes a value to a file in a shared directory and the other one reads it and prints it to the standard output."
}

########
debasher_shared_dir_example_shared_dirs()
{
    define_shared_dir "data"
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
shared_dir_writer_document()
{
    document_process "Writes a given value to a file in data directory."
}

########
shared_dir_writer_explain_opts()
{
    # -h option
    local description="Value to write to file in data directory"
    explain_opt "-h" "<int>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
shared_dir_writer_identify_cmdline_opts()
{
    opt_is_cmdline "-h"
}

########
shared_dir_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -h option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Define output file option
    local outf="$(get_absolute_shdirname "data")/${process_name}.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
shared_dir_writer()
{
    # Initialize variables
    local value=$(read_opt_value_from_func_args "-h" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Write value to file
    echo "$value" > "${outf}"
}

########
shared_dir_reader_document()
{
    document_process "Reads a value from the file written by shared_dir_writer in data directory."
}

########
shared_dir_reader_explain_opts()
{
    # -inf option
    local description="input file"
    explain_opt "-inf" "<file>" "$description"
}

########
shared_dir_reader_identify_cmdline_opts()
{
    :
}

########
shared_dir_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input file
    define_opt_from_proc_out "-inf" "shared_dir_writer" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
shared_dir_reader()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Read value from file
    cat < "${inf}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_shared_dir_example_program()
{
    add_debasher_process "shared_dir_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "shared_dir_reader" "cpus=1 mem=32 time=00:01:00"
}
