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
debasher_define_opt_deps_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
stream_writer_document()
{
    document_process "Prints a string to a FIFO."
}

########
stream_writer_explain_opts()
{
    # -outf option
    local description="output fifo"
    explain_opt "-outf" "<string>" "$description"
}

########
stream_writer_identify_cmdline_opts()
{
    :
}

########
stream_writer_define_opts()
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
stream_writer()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Write string to FIFO
    echo "Hello World" > "${outf}"
}

########
stream_reader_document()
{
    document_process "Reads a string from a FIFO and writes it to a file."
}

########
stream_reader_explain_opts()
{
    # -inf option
    local description="input fifo"
    explain_opt "-inf" "<string>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
stream_reader_identify_cmdline_opts()
{
    :
}

########
stream_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input FIFO
    define_opt_from_proc_out "-inf" "stream_writer" "-outf" optlist || return 1

    # Define option for output file
    local filename="${process_outdir}/received.txt"
    define_opt "-outf" "${filename}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
stream_reader_define_opt_deps()
{
    # Initialize variables
    local opt=$1
    local producer_process=$2

    # An option connected to a FIFO makes no dependency by default, so
    # that both ends start together; "after" asks instead for the reader
    # to be launched once the writer has started. Printing nothing keeps
    # the type DeBasher infers.
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
stream_reader()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Copy string from FIFO to file
    cat < "${inf}" > "${outf}"
}

########
stream_report_document()
{
    document_process "Reports what the reader received, whether it succeeded or failed."
}

########
stream_report_explain_opts()
{
    # -inf option
    local description="input file"
    explain_opt "-inf" "<file>" "$description"
}

########
stream_report_identify_cmdline_opts()
{
    :
}

########
stream_report_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input file
    define_opt_from_proc_out "-inf" "stream_reader" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
stream_report_define_opt_deps()
{
    # Initialize variables
    local opt=$1
    local producer_process=$2

    # An option connected to a file makes an "afterok" dependency by
    # default, so that the report would only run if the reader
    # succeeded; "afterany" asks for it to run once the reader has
    # ended, whether it succeeded or failed.
    case ${opt} in
        "-inf")
            echo "afterany"
            ;;
        *)
            echo ""
            ;;
    esac
}

########
stream_report()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Report what the reader received
    if [ -s "${inf}" ]; then
        echo "Received: $(cat "${inf}")"
    else
        echo "Nothing was received"
    fi
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_define_opt_deps_example_program()
{
    add_debasher_process "stream_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "stream_reader" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "stream_report" "cpus=1 mem=32 time=00:01:00"
}
