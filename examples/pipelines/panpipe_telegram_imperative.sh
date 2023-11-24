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

# Module imports
load_panpipe_module "panpipe_telegram_jobsteps"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
panpipe_telegram_imperative_shared_dirs()
{
    :
}

######################
# PIPELINE PROCESSES #
######################

########
telegram_document()
{
    step_description "Telegram Problem."
}

########
telegram_explain_cmdline_opts()
{
    # -f option
    local description="File to be processed"
    explain_cmdline_req_opt "-f" "<string>" "$description"

    # -c option
    local description="Line length in characters"
    explain_cmdline_req_opt "-c" "<int>" "$description"
}

########
telegram_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define the -out-processdir option, the output directory for the process
    define_opt "-out-processdir" "${process_outdir}" optlist || return 1

    # -f option
    define_cmdline_opt "$cmdline" "-f" optlist || return 1

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
telegram()
{
    # Initialize variables
    local outd=$(read_opt_value_from_func_args "-out-processdir" "$@")
    local file=$(read_opt_value_from_func_args "-f" "$@")
    local char_lim=$(read_opt_value_from_func_args "-c" "$@")

    # Execute decomposer
    seq_execute decomposer -f "${file}" -outf "${outd}"/words.txt || return 1

    # Obtain number of lines of decomposer output
    nlines=$("${WC}" -l "${outd}"/words.txt | "${AWK}" '{print $1}')

    if [ "${nlines}" -eq 0 ]; then
        echo "Warning: Decomposer's output is empty" >&2
        echo -n "${outd}"/output.txt || return 1
    else
        # Execute recomposer
        seq_execute recomposer -c "${char_lim}" -inf "${outd}"/words.txt -outf "${outd}"/output.txt || return 1
    fi
}

######################################
# PIPELINE IMPLEMENTED BY THE MODULE #
######################################

########
panpipe_telegram_imperative_pipeline()
{
    add_panpipe_process "telegram"  "cpus=1 mem=32 time=00:05:00"
}
