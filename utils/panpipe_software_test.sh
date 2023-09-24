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
    define_fifo "process_d_fifo" process_d
}

#######################################
# PIPELINE SOFTWARE TESTING PROCESSES #
#######################################

########
process_a_document()
{
    process_description "Sleeps a given number of seconds and exits."
}

########
process_a_explain_cmdline_opts()
{
    # -a option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-a" "<int>" "$description"
}

########
process_a_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # -a option
    define_cmdline_opt "$cmdline" "-a" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_a()
{
    # Initialize variables
    local sleep_time=`read_opt_value_from_line "$*" "-a"`

    # sleep some time
    sleep ${sleep_time}
}

########
process_a_execute()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2

    # Read sleep time
    local sleep_time=`read_opt_value_from_line "${cmdline}" "-a"`

    # Do not execute if sleep time is above 10 seconds
    if [ "${sleep_time}" -gt 10 ]; then
        return 1
    else
        return 0
    fi
}

########
process_b_document()
{
    process_description "Writes a given value to the file \`process_b.out\` in data directory."
}

########
process_b_explain_cmdline_opts()
{
    # -b option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-b" "<int>" "$description"
}

########
process_b_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-b" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=`get_absolute_shdirname "data"`

    # Define name of output file
    local outf="${abs_shrdir}/process_b.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_b()
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
process_c_document()
{
    process_description "Executes an array of 4 tasks. Each task creates an empty file named with the task index."
}

########
process_c_explain_cmdline_opts()
{
    # -c option
    local description="Sleep time in seconds"
    explain_cmdline_req_opt "-c" "<int>" "$description"
}

########
process_c_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Save option list so as to execute process four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
process_c()
{
    # Initialize variables
    local sleep_time=`read_opt_value_from_line "$*" "-c"`
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    touch "${PANPIPE_PROCESS_OUTDIR}"/${id}_aux

    # sleep some time
    sleep ${sleep_time}

    # create file
    touch "${PANPIPE_PROCESS_OUTDIR}"/$id
}

########
process_c_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # Remove auxiliary file
    rm "${PANPIPE_PROCESS_OUTDIR}"/${id}_aux

    logmsg "Cleaning finished"
}

########
process_c_reset_outdir()
{
    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    rm -f "${PANPIPE_PROCESS_OUTDIR}"/${id}*
}

########
process_d_document()
{
    process_description "Prints a string to a FIFO."
}

########
process_d_explain_cmdline_opts()
{
    :
}

########
process_d_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # Get absolute name of FIFO
    local abs_fifoname=`get_absolute_fifoname "process_d_fifo"`

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_d()
{
    # Initialize variables
    local fifo=`read_opt_value_from_line "$*" "-fifo"`

    # Write string to FIFO
    echo "Hello World" > "${fifo}"

    # sleep some time
    sleep 10
}

########
process_e_document()
{
    process_description "Reads a string from a FIFO."
}

########
process_e_explain_cmdline_opts()
{
    :
}

########
process_e_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # Get absolute name of FIFO
    local abs_fifoname=`get_absolute_fifoname "process_d_fifo"`

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_e()
{
    # Initialize variables
    local fifo=`read_opt_value_from_line "$*" "-fifo"`

    # Read strings from FIFO
    cat < "${fifo}"

    # sleep some time
    sleep 10
}

########
process_f_document()
{
    process_description "Prints Python version to file \`python_ver.txt\`."
}

########
process_f_explain_cmdline_opts()
{
    :
}

########
process_f_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # Save option list
    save_opt_list optlist
}

########
process_f()
{
    # Activate conda environment
    conda activate py27 || return 1

    # Write python version to file
    python --version > "${PANPIPE_PROCESS_OUTDIR}"/python_ver.txt 2>&1 || return 1

    # Deactivate conda environment
    conda deactivate

    # sleep some time
    sleep 10
}

########
process_f_conda_envs()
{
    define_conda_env py27 py27.yml
}

########
process_g_document()
{
    process_description "Executes an array of 4 tasks. Each task creates an empty file named with the task index."
}

########
process_g_explain_cmdline_opts()
{
    :
}

########
process_g_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # Save option list so as to execute process four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
process_g()
{
    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # create auxiliary file
    touch "${PANPIPE_PROCESS_OUTDIR}"/${id}_aux

    # sleep some time
    sleep 10

    # create file
    touch "${PANPIPE_PROCESS_OUTDIR}"/$id
}

########
process_g_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=`read_opt_value_from_line "$*" "-id"`

    # Remove auxiliary file
    rm "${PANPIPE_PROCESS_OUTDIR}"/${id}_aux

    logmsg "Cleaning finished"
}

########
process_h_document()
{
    process_description "Writes a given value to the file \`process_h.out\` in data directory."
}

########
process_h_explain_cmdline_opts()
{
    # -b option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-h" "<int>" "$description"
}

########
process_h_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=`get_absolute_shdirname "data"`

    # Define name of output file
    local outf="${abs_shrdir}/process_h.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_h()
{
    # Initialize variables
    local value=`read_opt_value_from_line "$*" "-h"`
    local outf=`read_opt_value_from_line "$*" "-outf"`

    # sleep some time
    sleep 10

    # Write value to file
    echo "$value" > "${outf}"
}

########
process_i_document()
{
    process_description "Get a value written by another process, increases it in one unit and writes it in data directory."
}

########
process_i_explain_cmdline_opts()
{
    :
}

########
process_i_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=`get_absolute_shdirname "data"`

    # Get name of file containing the value to be read
    local description="Value generated by b process"
    local valfile="${abs_shrdir}/process_b.out"
    define_opt "-valfile" "${valfile}" optlist || return 1

    # Define name of output file
    local process_outdir=`get_process_outdir process_i`
    local outf="${process_outdir}/process_i.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_i()
{
    # Initialize variables
    local valfile=`read_opt_value_from_line "$*" "-valfile"`
    local outf=`read_opt_value_from_line "$*" "-outf"`

    # Read value from file
    value=`cat "${valfile}"`

    # Increment value by 1
    ((value++))

    # Write value to file
    echo "$value" > "${outf}"
}
