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

# Load modules
load_debasher_module "debasher_telegram"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_telegram_array_shared_dirs()
{
    :
}

#####################
# PROGRAM PROCESSES #
#####################

########
decomposer_explain_cmdline_opts()
{
    # -f option
    local description="Prefix of files to be processed"
    explain_cmdline_req_opt "-f" "<string>" "$description"
}

########
decomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Obtain value of -f option
    pref_of_files=`get_cmdline_opt "${cmdline}" "-f"`

    # Define shared directory
    define_shared_dir "data"

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Process files
    local i=0
    for file in "${pref_of_files}"*; do
        local specific_optlist=${optlist}

        # Define name of input file
        define_opt "-f" "${file}" specific_optlist || return 1

        # Define name of output file
        local outf="${abs_shrdir}/words_$i.txt"
        define_opt "-outf" "${outf}" specific_optlist || return 1

        # Save option list
        save_opt_list specific_optlist

        # Increase index
        i=$((i + 1))
    done
}

########
recomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Obtain value of -f option
    pref_of_files=`get_cmdline_opt "${cmdline}" "-f"`

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Process files
    local i=0
    for file in "${pref_of_files}"*; do
        local specific_optlist=${optlist}

        # -inf option
        define_opt_from_proc_task_out "-inf" "decomposer" "$i" "-outf" specific_optlist || return 1

        # Define name of output file
        local outf="${process_outdir}/output_$i.txt"
        define_opt "-outf" "${outf}" specific_optlist || return 1

        # Save option list
        save_opt_list specific_optlist

        # Increase index
        i=$((i + 1))
    done
}

#####################################
# PROGRAM IMPLEMENTED BY THE MODULE #
#####################################

########
debasher_telegram_array_program()
{
    add_debasher_program "debasher_telegram" ""
}
