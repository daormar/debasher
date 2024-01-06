# DeBasher package
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

# Load modules
load_debasher_module "debasher_telegram"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_telegram_jobsteps_shared_dirs()
{
    define_shared_dir "data"
}

#####################
# PROGRAM PROCESSES #
#####################

########
decomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -f option
    define_cmdline_opt "$cmdline" "-f" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Define name of output file
    local outf="${abs_shrdir}/words.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
recomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Define name of input file
    local inf="${abs_shrdir}/words.txt"
    define_opt "-inf" "${inf}" optlist || return 1

    # Define name of output file
    local outf="${process_outdir}/output.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

#####################################
# PROGRAM IMPLEMENTED BY THE MODULE #
#####################################

########
debasher_telegram_jobsteps_program()
{
    add_debasher_process "decomposer"  "cpus=1 mem=32 time=00:05:00"
    add_debasher_process "recomposer"  "cpus=1 mem=32 time=00:05:00"
}