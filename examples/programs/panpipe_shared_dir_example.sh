# PanPipe package
# Copyright (C) 2019,2020 Daniel Ortiz-Mart\'inez
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
panpipe_shared_dir_example_shared_dirs()
{
    define_shared_dir "data"
}

#######################################
# PIPELINE SOFTWARE TESTING PROCESSES #
#######################################

########
shared_dir_writer_document()
{
    process_description "Writes a given value to a file in data directory."
}

########
shared_dir_writer_explain_cmdline_opts()
{
    # -h option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-h" "<int>" "$description"
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

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Define output file option
    local outf="${abs_shrdir}/${process_name}.out"
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

##################################
# PIPELINE DEFINED BY THE MODULE #
##################################

########
panpipe_shared_dir_example_pipeline()
{
    add_panpipe_process "shared_dir_writer" "cpus=1 mem=32 time=00:01:00"
}
