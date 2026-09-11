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
load_debasher_module "debasher_hello_world"

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_hello_world_alias_opt_map_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

# This process is an alias of "hello_world" (see
# data/programs/debasher_hello_world.sh), whose implementation reads
# its greeting string from a "-s" option. Here the process is meant to
# expose a more descriptive "-msg" option on the command line instead
# of "-s" -- the two option names never coexist within one program, so
# a plain alias (see debasher_hello_world_alias.sh) can't reconcile
# them: whatever _define_opts puts into the optlist under "-msg" would
# reach "hello_world"'s implementation as "-msg", not the "-s" it
# actually reads.
#
# The "alias_opt_map" additional spec attribute solves exactly this:
# it renames "-msg" into "-s" right before delegating to "hello_world",
# while _explain_opts/_identify_cmdline_opts/_define_opts below keep
# using "-msg" throughout, as if no renaming were involved at all.

########
hello_world_msg_document()
{
    document_process "Prints a hello world message, illustrating the alias_opt_map additional spec attribute."
}

########
hello_world_msg_explain_opts()
{
    # -msg option
    local description="String to be displayed ('Hello World!' by default)"
    explain_opt "-msg" "<string>" "$description"
}

########
hello_world_msg_identify_cmdline_opts()
{
    opt_is_non_mandatory_cmdline "-msg"
}

########
hello_world_msg_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -msg option
    define_cmdline_opt_if_given "${cmdline}" "-msg" optlist || return 1

    # Save option list
    save_opt_list optlist
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_hello_world_alias_opt_map_program()
{
    add_debasher_process "hello_world_msg" "cpus=1 mem=32 time=00:01:00" "alias=hello_world;alias_opt_map=-msg:-s"
}
