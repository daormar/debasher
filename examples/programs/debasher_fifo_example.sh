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
debasher_fifo_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
fifo_writer_document()
{
    process_description "Prints a string to a FIFO."
}

########
fifo_writer_explain_cmdline_opts()
{
    :
}

########
fifo_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for FIFO
    local fifoname="fifo"
    define_fifo_opt "-outf" "${fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
fifo_writer()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Write string to FIFO
    echo "Hello World" > "${outf}"
}

########
fifo_reader_document()
{
    process_description "Reads a string from a FIFO."
}

########
fifo_reader_explain_cmdline_opts()
{
    :
}

########
fifo_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "fifo_writer" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
fifo_reader_define_opt_deps()
{
    # Initialize variables
    local opt=$1
    local producer_process=$2

    case ${opt} in
        "-inf")
            echo "after"
            ;;
        *)
            echo ""
            ;;
    esac
}

########
fifo_reader()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Read strings from FIFO
    cat < "${inf}"
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_fifo_example_program()
{
    add_debasher_process "fifo_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "fifo_reader" "cpus=1 mem=32 time=00:01:00"
}
