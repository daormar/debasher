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
debasher_hello_world_r_shared_dirs()
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
hello_world_r=$(cat <<'EOF'
args <- commandArgs(trailingOnly = TRUE)

# Function to parse arguments
parse_args <- function(args) {
  options <- list()
  i <- 1
  while (i <= length(args)) {
    if (args[i] == "-s") {
      if ((i + 1) <= length(args)) {
        options$string <- args[i + 1]
        i <- i + 1
      } else {
        stop("Option -s requires a string argument.")
      }
    }
    i <- i + 1
  }
  return(options)
}

# Parse the command-line arguments
options <- parse_args(args)

# Ensure the string was provided
if (is.null(options$string)) {
  stop("You must provide a string with the -s option.")
}

# Print the string
print(options$string)
EOF
)

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_hello_world_r_program()
{
    add_debasher_process "hello_world" "cpus=1 mem=32 time=00:01:00"
}
