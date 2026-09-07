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

# Name of the file shared_dir_writer writes into the shared data
# directory and shared_dir_reader reads back from it.
SHARED_DIR_EXAMPLE_VALUE_FNAME="value.out"

#################
# CFG FUNCTIONS #
#################

########
debasher_shared_dir_example_document()
{
    document_module "This module implements a simple program with two processes that both work with the same shared directory: one writes a value to a file in it and the other one reads that file and prints its content to the standard output."
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
    document_process "Writes a given value to a file in the shared data directory."
}

########
shared_dir_writer_explain_opts()
{
    # -h option
    local description="Value to write to file in data directory"
    explain_opt "-h" "<int>" "$description"

    # -out-datadir option
    local description="data directory"
    explain_opt "-out-datadir" "<file>" "$description"
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

    # Define data directory option (the shared directory itself, not a
    # specific file inside it)
    define_opt_from_shared_dir "-out-datadir" "data" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
shared_dir_writer()
{
    # Initialize variables
    local value=$(read_opt_value_from_func_args "-h" "$@")
    local datadir=$(read_opt_value_from_func_args "-out-datadir" "$@")

    # Write value to file
    echo "$value" > "${datadir}/${SHARED_DIR_EXAMPLE_VALUE_FNAME}"
}

########
shared_dir_reader_document()
{
    document_process "Reads the value shared_dir_writer wrote to a file in the shared data directory and prints it."
}

########
shared_dir_reader_explain_opts()
{
    # -datadir option
    local description="data directory"
    explain_opt "-datadir" "<file>" "$description"
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

    # Define data directory option (the shared directory itself; not
    # connected to shared_dir_writer's own "-out-datadir" via
    # define_opt_from_proc_out, since both simply name the same shared
    # directory: the engine derives the dependency between the two
    # processes on its own, from both resolving to the identical
    # absolute path)
    define_opt_from_shared_dir "-datadir" "data" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
shared_dir_reader()
{
    # Initialize variables
    local datadir=$(read_opt_value_from_func_args "-datadir" "$@")

    # Read value from file
    cat < "${datadir}/${SHARED_DIR_EXAMPLE_VALUE_FNAME}"
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
