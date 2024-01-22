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
debasher_telegram_morrison_shared_dirs()
{
    :
}

#####################
# PROGRAM PROCESSES #
#####################

########
rseq_document()
{
    step_description "Telegram problem RSEQ module."
}

########
rseq_explain_cmdline_opts()
{
    # -f option
    local description="File to be processed"
    explain_cmdline_req_opt "-f" "<string>" "$description"
}

########
rseq_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define FIFO
    local fifoname="rseq_fifo"
    define_fifo "${fifoname}"

    # Get absolute name of FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for rseq FIFO
    define_opt "-outf" "${abs_fifoname}" optlist || return 1

    # -f option
    define_cmdline_opt "$cmdline" "-f" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
rseq()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    local file=$(read_opt_value_from_func_args "-f" "$@")

    # Read sequence
    cat "${file}" > "${outf}" || return 1
}

########
decomposer_document()
{
    step_description "Telegram Problem Decomposer module."
}

########
decomposer_explain_cmdline_opts()
{
    :
}

########
decomposer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Get absolute name of FIFO
    local rseq=$(get_adaptive_processname "rseq")
    local fifoname="rseq_fifo"
    local abs_fifoname=$(get_absolute_fifoname "${rseq}" "${fifoname}")

    # Define option for rseq FIFO
    define_opt "-inf" "${abs_fifoname}" optlist || return 1

    # Define FIFO
    fifoname="dc_fifo"
    define_fifo "${fifoname}"

    # Get absolute name of FIFO
    abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for decomposer FIFO
    define_opt "-outf" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
decomposer()
{
    # Initialize variables
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Decompose input
    awk '{for(i=1;i<=NF;++i) print $i}' "${inf}" > "${outf}" ; pipe_fail || return 1
}

########
recomposer_document()
{
    step_description "Telegram Problem Recomposer module."
}

########
recomposer_explain_cmdline_opts()
{
    # -c option
    local description="Line length in characters"
    explain_cmdline_req_opt "-c" "<int>" "$description"
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

    # Get absolute name of FIFO
    local decomposer=$(get_adaptive_processname "decomposer")
    local fifoname="dc_fifo"
    local abs_fifoname=$(get_absolute_fifoname "${decomposer}" "${fifoname}")

    # Define option for decomposer FIFO
    define_opt "-inf" "${abs_fifoname}" optlist || return 1

    # Define FIFO
    fifoname="rc_fifo"
    define_fifo "${fifoname}"

    # Get absolute name of FIFO
    abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for decomposer FIFO
    define_opt "-outf" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
recompose()
{
    local char_lim=$1
    local file=$2

    awk -v char_lim="${char_lim}" '{
          current_line = current_line $0
          if (length(current_line) < char_lim)
           current_line = current_line " "
          else {
           print current_line
           current_line = $0
          }
         }
        END {
         if (length(current_line) > 0)
          print current_line
        }' "${file}"
}

########
recomposer()
{
    # Initialize variables
    local char_lim=$(read_opt_value_from_func_args "-c" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Recompose input
    recompose "${char_lim}" "${inf}" > "${outf}" ; pipe_fail || return 1
}

########
wseq_document()
{
    step_description "Telegram Problem WSEQ module."
}

########
wseq_explain_cmdline_opts()
{
    :
}

########
wseq_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define name of output file
    local outf="${process_outdir}/output.txt"
    define_opt "-outf" "${outf}" optlist || return 1

    # Get absolute name of FIFO
    local recomposer=$(get_adaptive_processname "recomposer")
    local fifoname="rc_fifo"
    local abs_fifoname=$(get_absolute_fifoname "${recomposer}" "${fifoname}")

    # Define option for decomposer FIFO
    define_opt "-inf" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
wseq()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")
    local inf=$(read_opt_value_from_func_args "-inf" "$@")

    # Write sequence
    cat "${inf}" > "${outf}" || return 1
}

#####################################
# PROGRAM IMPLEMENTED BY THE MODULE #
#####################################

########
debasher_telegram_morrison_program()
{
    add_debasher_process "rseq"        "cpus=1 mem=32 time=00:05:00"
    add_debasher_process "decomposer"  "cpus=1 mem=32 time=00:05:00"
    add_debasher_process "recomposer"  "cpus=1 mem=32 time=00:05:00"
    add_debasher_process "wseq"        "cpus=1 mem=32 time=00:05:00"
}
