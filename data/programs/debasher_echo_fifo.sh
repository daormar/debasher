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
debasher_echo_fifo_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
echo_fifo_document()
{
    document_process "Copies the contents of an input fifo to an output fifo."
}

########
echo_fifo_explain_opts()
{
    # -inf option
    local description="input fifo"
    explain_opt "-inf" "<string>" "$description"

    # -outf option
    description="output fifo"
    explain_opt "-outf" "<string>" "$description"
}

########
echo_fifo_identify_cmdline_opts()
{
    :
}

########
echo_fifo_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input FIFO
    local infifoname="echo_fifo_in"
    define_fifo_opt "-inf" "${infifoname}" optlist || return 1

    # Define option for output FIFO
    local outfifoname="echo_fifo_out"
    define_fifo_opt "-outf" "${outfifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
echo_fifo()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Read input line by line and copy it to the output fifo
    local line
    while IFS= read -r line < "${inf}"; do
        if [ "${line}" = "${DEBASHER_SHUTDOWN_TOKEN}" ]; then
            break
        else
            echo "${line}" > "${outf}"
        fi
    done
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_echo_fifo_program()
{
    add_debasher_process "echo_fifo" "cpus=1 mem=32 time=00:10:00"
}
