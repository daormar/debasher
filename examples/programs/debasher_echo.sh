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
debasher_echo_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
stream_echo_document()
{
    process_description "Executes a process reading and writing from fifos."
}

########
stream_echo_explain_cmdline_opts()
{
    :
}

########
stream_echo_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define option for input FIFO
    local fifoname="stream_echo_in"
    define_fifo_opt "-inf" "${fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
stream_echo()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Increase value iteratively until it reaches n
    local stream=$(cat "${inf}")
    while [ "${stream}" != "${SHUTDOWN_TOKEN}" ]; do
        echo "${stream}"
        stream=$(cat "${inf}")
    done
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_echo_program()
{
    add_debasher_process "stream_echo" "cpus=1 mem=32 time=00:10:00"
}
