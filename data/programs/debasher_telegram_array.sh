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
decomposer_explain_opts()
{
    # -pref option
    local description="Prefix of files to be processed"
    explain_opt "-pref" "<string>" "$description"

    # -f option
    local description="File to be processed"
    explain_opt "-f" "<file>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
decomposer_identify_cmdline_opts()
{
    opt_is_cmdline "-pref"
}

########
decomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # Obtain value of -pref option
    pref_of_files=$(get_cmdline_opt "${cmdline}" "-pref")

    # Array of files matching the -pref prefix
    array=()
    for file in "${pref_of_files}"*; do
        array+=("${file}")
    done

    for idx in "${!array[@]}"; do
        local optlist=""

        # Define name of input file
        define_opt "-f" "${array[$idx]}" optlist || return 1

        # Define name of output file
        local outf="${process_outdir}/words_${idx}.txt"
        define_opt "-outf" "${outf}" optlist || return 1

        # Save option list
        save_opt_list optlist
    done
}

########
recomposer_explain_opts()
{
    # -pref option
    local description="Prefix of files to be processed"
    explain_opt "-pref" "<string>" "$description"

    # -c option
    local description="Line length in characters"
    explain_opt "-c" "<int>" "$description"

    # -inf option
    local description="input fifo"
    explain_opt "-inf" "<file>" "$description"

    # -outf option
    local description="output file"
    explain_opt "-outf" "<file>" "$description"
}

########
recomposer_identify_cmdline_opts()
{
    opt_is_cmdline "-pref"
    opt_is_cmdline "-c"
}

########
recomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4

    # Obtain value of -pref option
    pref_of_files=$(get_cmdline_opt "${cmdline}" "-pref")

    # Array of files matching the -pref prefix
    array=()
    for file in "${pref_of_files}"*; do
        array+=("${file}")
    done

    for idx in "${!array[@]}"; do
        local optlist=""

        # -c option (its value never depends on idx, but every option is
        # still defined once per iteration — array mode always re-emits
        # every option's call inside the loop, rather than hoisting
        # idx-independent ones out of it)
        define_cmdline_opt "$cmdline" "-c" optlist || return 1

        # -inf option
        define_opt_from_proc_task_out "-inf" "decomposer" "${idx}" "-outf" optlist || return 1

        # Define name of output file
        local outf="${process_outdir}/output_${idx}.txt"
        define_opt "-outf" "${outf}" optlist || return 1

        # Save option list
        save_opt_list optlist
    done
}

#####################################
# PROGRAM IMPLEMENTED BY THE MODULE #
#####################################

########
debasher_telegram_array_program()
{
    add_debasher_program "debasher_telegram"
}
