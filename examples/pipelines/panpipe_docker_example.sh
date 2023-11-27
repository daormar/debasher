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

#############
# CONSTANTS #
#############

#################
# CFG FUNCTIONS #
#################

########
panpipe_docker_example_shared_dirs()
{
    :
}

#######################################
# PIPELINE SOFTWARE TESTING PROCESSES #
#######################################

########
docker_example_explain_cmdline_opts()
{
    :
}

########
docker_example_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define name of output file
    define_opt "-outf" "${process_outdir}/hello_world.txt" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
docker_example()
{
    # Initialize variables
    local outf=$(read_opt_value_from_func_args "-outf" "$@")

    # Write python version to file
    "${DOCKER}" run hello-world > "${outf}" 2>&1 || return 1
}

########
docker_example_docker_imgs()
{
    pull_docker_img "library/hello-world"
}

##################################
# PIPELINE DEFINED BY THE MODULE #
##################################

########
panpipe_docker_example_pipeline()
{
    add_panpipe_process "docker_example" "cpus=1 mem=32 time=00:01:00"
}
