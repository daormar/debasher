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
debasher_hello_world_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
hello_world_document()
{
    process_description "Prints a hello world message."
}

########
hello_world_explain_cmdline_opts()
{
    # -s option
    local description="String to be displayed ('Hello World!' by default)"
    explain_cmdline_opt "-s" "<string>" "$description"
}

########
hello_world_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Obtain value of -s option
    local str=$(get_cmdline_opt "${cmdline}" "-s")

    # -s option
    if [ "${str}" = "${OPT_NOT_FOUND}" ]; then
        define_opt "-s" "Hello World!" optlist || return 1
    else
        define_opt "-s" "$str" optlist || return 1
    fi

    # Save option list
    save_opt_list optlist
}

########
hello_world_py=$(cat <<'EOF'
import argparse

# Create the parser
parser = argparse.ArgumentParser()

# Add the "-s" option with an integer argument
parser.add_argument('-s', type=str, required=True, help='String to be displayed')

# Parse the arguments
args = parser.parse_args()

# Access the value of "-s"
s = args.s

# Print message
print(s)
EOF
)

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_hello_world_py_program()
{
    add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
}
