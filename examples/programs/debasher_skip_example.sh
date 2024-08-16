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
debasher_skip_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
value_writer_document()
{
    process_description "Takes two numbers and produce their sum as output."
}

########
value_writer_explain_cmdline_opts()
{
    # -num-a option
    local description="First number to be summed"
    explain_cmdline_req_opt "-num-a" "<int>" "$description"

    # -num-b option
    local description="Second number to be summed"
    explain_cmdline_req_opt "-num-b" "<int>" "$description"
}

########
value_writer_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -num-a option
    define_cmdline_opt "$cmdline" "-num-a" optlist || return 1

    # -num-b option
    define_cmdline_opt "$cmdline" "-num-b" optlist || return 1

    # Define value descriptor option
    define_value_desc_opt "-outv" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
value_writer()
{
    # Initialize variables
    local num_a=$(read_opt_value_from_func_args "-num-a" "$@")
    local num_b=$(read_opt_value_from_func_args "-num-b" "$@")
    local outv=$(read_opt_value_from_func_args "-outv" "$@")

    # Calculate the sum
    local sum=$((num_a + num_b))

    # Write value to descriptor
    write_value_to_desc "${sum}" "${outv}"
}

########
value_reader_document()
{
    process_description "Get a value produced by another process, increases it in one unit and writes it in own directory."
}

########
value_reader_explain_cmdline_opts()
{
    :
}

########
value_reader_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define value descriptor option related to output value of
    # value_writer
    define_opt_from_proc_out "-val-desc" "value_writer" "-outv" optlist || return 1

    # Define output file option
    local outf="${process_outdir}/${process_name}.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
value_reader()
{
    # Initialize variables
    local val_desc=$(read_opt_value_from_func_args "-val-desc" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Read value from descriptor
    value=$(read_value_from_desc "${val_desc}")

    # Increment value by 1
    ((value++))

    # Write value to file
    echo "$value" > "${outf}"
}

########
value_reader_skip()
{
    # Initialize variables
    local val_desc=$(read_opt_value_from_func_args "-val-desc" "$@")
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Read value from descriptor
    local value=$(read_value_from_desc "${val_desc}")

    # Skip if read value is odd
    if ((value % 2 == 0)); then
        return 1
    else
        return 0
    fi
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_skip_example_program()
{
    add_debasher_process "value_writer" "cpus=1 mem=32 time=00:01:00"
    add_debasher_process "value_reader" "cpus=1 mem=32 time=00:01:00"
}
