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
panpipe_software_test_shared_dirs()
{
    define_shared_dir "data"
}

########
panpipe_software_test_fifos()
{
    define_fifo "step_d_fifo" step_d
}

###################################
# PIPELINE SOFTWARE TESTING STEPS #
###################################

########
step_a_document()
{
    step_description "Sleeps a given number of seconds and exits."
}

########
step_a_explain_cmdline_opts()
{
    # -a option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-a" "<int>" "$description"
}

########
step_a_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # -a option
    define_cmdline_opt "$cmdline" "-a" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
step_a()
{
    # Initialize variables
    local sleep_time=`read_opt_value_from_line "$*" "-a"`

    # sleep some time
    sleep ${sleep_time}
}

########
step_b_document()
{
    step_description "Writes a given value to the file \`step_b.out\` in data directory."
}

########
step_b_explain_cmdline_opts()
{
    # -b option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-b" "<int>" "$description"
}

########
step_b_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-b" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=`get_absolute_shdirname "data"`

    # Define name of output file
    local outf="${abs_shrdir}/step_b.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
step_b()
{
    # Initialize variables
    local value=`read_opt_value_from_line "$*" "-b"`
    local outf=`read_opt_value_from_line "$*" "-outf"`

    # sleep some time
    sleep 10

    # Write value to file
    echo "$value" > "${outf}"
}

########
step_c_document()
{
    step_description "Executes an array of 4 tasks. Each task creates an empty file named with the task index."
}

########
step_c_explain_cmdline_opts()
{
    # -c option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-c" "<int>" "$description"
}

########
step_c_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Save option list so as to execute step four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
step_c()
{
    # Initialize variables
    local sleep_time=`read_opt_value_from_line "$*" "-c"`
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    touch "${PANPIPE_STEP_OUTDIR}"/${id}_aux

    # sleep some time
    sleep ${sleep_time}

    # create file
    touch "${PANPIPE_STEP_OUTDIR}"/$id
}

########
step_c_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # Remove auxiliary file
    rm "${PANPIPE_STEP_OUTDIR}"/${id}_aux

    logmsg "Cleaning finished"
}

########
step_c_reset_outdir()
{
    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    rm -f "${PANPIPE_STEP_OUTDIR}"/${id}*
}

########
step_d_document()
{
    step_description "Prints a string to a FIFO."
}

########
step_d_explain_cmdline_opts()
{
    :
}

########
step_d_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # Get absolute name of FIFO
    local abs_fifoname=`get_absolute_fifoname "step_d_fifo"`

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
step_d()
{
    # Initialize variables
    local fifo=`read_opt_value_from_line "$*" "-fifo"`

    # Write string to FIFO
    echo "Hello World" > "${fifo}"

    # sleep some time
    sleep 10
}

########
step_e_document()
{
    step_description "Reads a string from a FIFO."
}

########
step_e_explain_cmdline_opts()
{
    :
}

########
step_e_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # Get absolute name of FIFO
    local abs_fifoname=`get_absolute_fifoname "step_d_fifo"`

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
step_e()
{
    # Initialize variables
    local fifo=`read_opt_value_from_line "$*" "-fifo"`

    # Read strings from FIFO
    cat < "${fifo}"

    # sleep some time
    sleep 10
}

########
step_f_document()
{
    step_description "Prints Python version to file \`python_ver.txt\`."
}

########
step_f_explain_cmdline_opts()
{
    :
}

########
step_f_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # Save option list
    save_opt_list optlist
}

########
step_f()
{
    # Activate conda environment
    conda activate py27 || return 1

    # Write python version to file
    python --version > "${PANPIPE_STEP_OUTDIR}"/python_ver.txt 2>&1 || return 1

    # Deactivate conda environment
    conda deactivate

    # sleep some time
    sleep 10
}

########
step_f_conda_envs()
{
    define_conda_env py27 py27.yml
}

########
step_g_document()
{
    step_description "Executes an array of 4 tasks. Each task creates an empty file named with the task index."
}

########
step_g_explain_cmdline_opts()
{
    :
}

########
step_g_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # Save option list so as to execute step four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
step_g()
{
    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    touch "${PANPIPE_STEP_OUTDIR}"/${id}_aux

    # sleep some time
    sleep 10

    # create file
    touch "${PANPIPE_STEP_OUTDIR}"/$id
}

########
step_g_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # Remove auxiliary file
    rm "${PANPIPE_STEP_OUTDIR}"/${id}_aux

    logmsg "Cleaning finished"
}

########
step_h_document()
{
    step_description "Writes a given value to the file \`step_h.out\` in data directory."
}

########
step_h_explain_cmdline_opts()
{
    # -b option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-h" "<int>" "$description"
}

########
step_h_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local stepspec=$2
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=`get_absolute_shdirname "data"`

    # Define name of output file
    local outf="${abs_shrdir}/step_h.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
step_h()
{
    # Initialize variables
    local value=`read_opt_value_from_line "$*" "-h"`
    local outf=`read_opt_value_from_line "$*" "-outf"`

    # sleep some time
    sleep 10

    # Write value to file
    echo "$value" > "${outf}"
}
