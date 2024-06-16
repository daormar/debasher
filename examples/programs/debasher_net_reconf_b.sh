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
load_debasher_module "debasher_net_reconf_a"

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
process2_explain_cmdline_opts()
{
    :
}

########
process2_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -inf option
    define_opt_from_proc_out "-inf" "process1" "-outf" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
debasher_net_reconf_b_program()
{
    add_debasher_program " debasher_net_reconf_a"
}
