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

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
debasher_conda_example_shared_dirs()
{
    :
}

######################################
# PROGRAM SOFTWARE TESTING PROCESSES #
######################################

########
conda_example_document()
{
    process_description "Prints Python version to file \`python_ver.txt\`."
}

########
conda_example_explain_cmdline_opts()
{
    :
}

########
conda_example_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define name of output file
    define_opt "-outf" "${process_outdir}/python_ver.txt" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
conda_example()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Activate conda environment
    conda activate py27 || return 1

    # Write python version to file
    python --version > "${outf}" 2>&1 || return 1

    # Deactivate conda environment
    conda deactivate
}

########
conda_example_conda_envs()
{
    define_conda_env py27 py27.yml
}

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_conda_example_program()
{
    add_debasher_process "conda_example" "cpus=1 mem=32 time=00:01:00"
}
