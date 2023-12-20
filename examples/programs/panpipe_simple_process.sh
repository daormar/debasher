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
panpipe_simple_process_shared_dirs()
{
    :
}

#######################################
# PIPELINE SOFTWARE TESTING PROCESSES #
#######################################

########
simple_process_document()
{
    process_description "Sleeps a given number of seconds and exits."
}

########
simple_process_explain_cmdline_opts()
{
    # -a option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-a" "<int>" "$description"
}

########
simple_process_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -a option
    define_cmdline_opt "$cmdline" "-a" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
simple_process()
{
    # Initialize variables
    local sleep_time=$(read_opt_value_from_func_args "-a" "$@")

    # sleep some time
    sleep ${sleep_time}
}

########
simple_process_skip()
{
    # Initialize variables
    local sleep_time=$(read_opt_value_from_func_args "-a" "$@")

    # Skip if sleep time is above 10 seconds
    if [ "${sleep_time}" -gt 10 ]; then
        return 0
    else
        return 1
    fi
}

##################################
# PIPELINE DEFINED BY THE MODULE #
##################################

########
panpipe_simple_process_pipeline()
{
    add_panpipe_process "simple_process" "cpus=1 mem=32 time=00:01:00,00:02:00,00:03:00"
}
