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
    local process_name=$3
    local process_outdir=$4
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
    local sleep_time=$(read_opt_value_from_line "$*" "-a")

    # sleep some time
    sleep ${sleep_time}
}

########
process_a_should_execute()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2

    # Read sleep time
    local sleep_time=$(read_opt_value_from_line "${cmdline}" "-a")

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
    process_description "Writes a given value to a file in data directory."
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-b" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Define name of output file
    local outf="${abs_shrdir}/${process_name}.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_b()
{
    # Initialize variables
    local value=$(read_opt_value_from_line "$*" "-b")
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # sleep some time
    sleep 10

    # Write value to file
    echo "$value" > "${outf}"
}

########
process_c_document()
{
    process_description "Executes an array of 4 tasks. Each task creates a file containing the task index."
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -c option
    define_cmdline_opt "$cmdline" "-c" optlist || return 1

    # Save option list so as to execute process four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        define_opt "-outf" "${process_outdir}/${id}" specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
process_c()
{
    # Initialize variables
    local sleep_time=$(read_opt_value_from_line "$*" "-c")
    local id=$(read_opt_value_from_line "$*" "-id")
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # sleep some time
    sleep ${sleep_time}

    # create file
    echo $id > "${outf}"
}

########
process_c_reset_outdir()
{
    # Initialize variables
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # create auxiliary file
    rm "${outf}"
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define FIFO
    local fifoname="fifo"
    define_fifo "${fifoname}"

    # Get absolute name of FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_d()
{
    # Initialize variables
    local fifo=$(read_opt_value_from_line "$*" "-fifo")

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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Get absolute name of FIFO
    local process_d=$(get_adaptive_processname "process_d")
    local fifoname="fifo"
    local abs_fifoname=$(get_absolute_fifoname "${process_d}" "${fifoname}")

    # Define option for FIFO
    define_opt "-fifo" "${abs_fifoname}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_e_define_opt_deps()
{
    # Initialize variables
    local opt=$1
    local producer_process=$2

    case ${opt} in
        "-fifo")
            echo "after"
            ;;
        *)
            echo ""
            ;;
    esac
}

########
process_e()
{
    # Initialize variables
    local fifo=$(read_opt_value_from_line "$*" "-fifo")

    # Read strings from FIFO
    cat < "${fifo}"
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Define name of output file
    define_opt "-outf" "${process_outdir}/python_ver.txt" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_f()
{
    # Initialize variables
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # Activate conda environment
    conda activate py27 || return 1

    # Write python version to file
    python --version > "${outf}" 2>&1 || return 1

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
    process_description "Executes an array of 4 tasks. Each task takes an input file and prints its content to an output file."
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # Obtain output directory for process_c
    local proc_c_outdir=`get_process_outdir_adaptive "process_c"`

    # Save option list so as to execute process four times
    for id in 1 2 3 4; do
        local specific_optlist=${optlist}
        define_opt "-id" $id specific_optlist || return 1
        define_opt "-infile" "${proc_c_outdir}/${id}" specific_optlist || return 1
        define_opt "-outdir" "${process_outdir}" specific_optlist || return 1
        save_opt_list specific_optlist
    done
}

########
process_g()
{
    # Initialize variables
    local id=$(read_opt_value_from_line "$*" "-id")
    local infile=$(read_opt_value_from_line "$*" "-infile")
    local outd=$(read_opt_value_from_line "$*" "-outdir")

    # Copy content of infile to auxiliary file
    cat "${infile}" > "${outd}"/${id}_aux

    # Copy content of infile to final file
    cat "${outd}"/${id}_aux > "${outd}"/${id}
}

########
process_g_post()
{
    logmsg "Cleaning directory..."

    # Initialize variables
    local id=$(read_opt_value_from_line "$*" "-id")
    local outd=$(read_opt_value_from_line "$*" "-outdir")

    # Remove auxiliary file
    rm "${outd}"/${id}_aux
    rm "${outd}"/${id}

    logmsg "Cleaning finished"
}

########
process_h_document()
{
    process_description "Writes a given value to a file in data directory."
}

########
process_h_explain_cmdline_opts()
{
    # -h option
    local description="Value to write to file in data directory"
    explain_cmdline_req_opt "-h" "<int>" "$description"
}

########
process_h_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local process_spec=$2
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -b option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Define name of output file
    local outf="${abs_shrdir}/${process_name}.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_h()
{
    # Initialize variables
    local value=$(read_opt_value_from_line "$*" "-h")
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # sleep some time
    sleep 10

    # Write value to file
    echo "$value" > "${outf}"
}

########
process_i_document()
{
    process_description "Get a value written by another process, increases it in one unit and writes it in own directory."
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
    local process_name=$3
    local process_outdir=$4
    local optlist=""

    # -h option
    define_cmdline_opt "$cmdline" "-h" optlist || return 1

    # Get absolute name of shared directory
    local abs_shrdir=$(get_absolute_shdirname "data")

    # Get name of file containing the value to be read
    local process_b=$(get_adaptive_processname "process_b")
    local valfile="${abs_shrdir}/${process_b}.out"
    define_opt "-valfile" "${valfile}" optlist || return 1

    # Define name of output file
    local outf="${process_outdir}/${process_name}.out"
    define_opt "-outf" "${outf}" optlist || return 1

    # Save option list
    save_opt_list optlist
}

########
process_i()
{
    # Initialize variables
    local valfile=$(read_opt_value_from_line "$*" "-valfile")
    local outf=$(read_opt_value_from_line "$*" "-outf")

    # Read value from file
    value=$(cat "${valfile}")

    # Increment value by 1
    ((value++))

    # Write value to file
    echo "$value" > "${outf}"
}

##################################
# PIPELINE DEFINED BY THE MODULE #
##################################

########
panpipe_software_test_pipeline()
{
    add_panpipe_process "process_a" "cpus=1 mem=32 time=00:01:00,00:02:00,00:03:00"
    add_panpipe_process "process_b" "cpus=1 mem=32 time=00:01:00"
    add_panpipe_process "process_c" "cpus=1 mem=32 time=00:01:00,00:02:00 throttle=2"
    add_panpipe_process "process_d" "cpus=1 mem=32 time=00:01:00"
    add_panpipe_process "process_e" "cpus=1 mem=32 time=00:01:00"
    add_panpipe_process "process_f" "cpus=1 mem=32 time=00:01:00"
    add_panpipe_process "process_g" "cpus=1 mem=32 time=00:01:00 throttle=4"
    add_panpipe_process "process_h" "cpus=1 mem=32 time=00:01:00"
    add_panpipe_process "process_i" "cpus=1 mem=32 time=00:01:00"
}
