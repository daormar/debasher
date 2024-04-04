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

# INCLUDE BASH LIBRARY
. "${debasher_bindir}"/debasher_lib || exit 1

########
print_desc()
{
    echo "debasher_get_stdout gets stdout for a given process"
    echo "type \"debasher_get_stdout --help\" to get usage information"
}

########
usage()
{
    echo "debasher_get_stdout       -d <string> [-p <string>] [-t <int>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name whose stdout should be displayed"
    echo "-t <int>                  Index of task array for process"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    p_given=0
    t_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-p") shift
                  if [ $# -ne 0 ]; then
                      given_processname=$1
                      p_given=1
                  fi
                  ;;
            "-t") shift
                  if [ $# -ne 0 ]; then
                      task_idx=$1
                      t_given=1
                  fi
                  ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${d_given} -eq 0 ]; then
        echo "Error! -d parameter not given!" >&2
        exit 1
    else
        if [ ! -d "${pdir}" ]; then
            echo "Error! program directory does not exist" >&2
            exit 1
        fi

        if [ ! -f "${pdir}/${PRG_COMMAND_LINE_BASENAME}" ]; then
            echo "Error! ${pdir}/${PRG_COMMAND_LINE_BASENAME} file is missing" >&2
            exit 1
        fi
    fi
}

########
configure_scheduler()
{
    local sched=$1
    if [ ${sched} != ${OPT_NOT_FOUND} ]; then
        set_debasher_scheduler ${sched} || return 1
    fi
}

########
get_out()
{
    local dirname=$1
    local process=$2
    local absdirname=`get_absolute_path "${dirname}"`
    local command_line_file="${absdirname}/${PRG_COMMAND_LINE_BASENAME}"

    # Extract information from PRG_COMMAND_LINE_BASENAME file
    local pfile
    pfile=`get_abspfile_from_command_line_file "${command_line_file}"` || return 1
    local sched
    sched=`get_sched_from_command_line_file "${command_line_file}"` || return 1

    # Get original output directory
    local orig_outdir
    orig_outdir=`get_orig_outdir_from_command_line_file "${command_line_file}"` || return 1

    # Show warning if directory provided as option is different than the
    # original working directory
    if dirnames_are_equal "${orig_outdir}" "${absdirname}"; then
        local moved_outdir="no"
    else
        echo "Warning: program output directory was moved (original directory: ${orig_outdir})" >&2
        cmdline=`replace_outdir_in_cmdline "${cmdline}" "${absdirname}"`
        local moved_outdir="yes"
    fi

    # Configure scheduler
    configure_scheduler $sched || return 1

    # Get output
    if [ "${t_given}" -eq 0 ]; then
        local stdout_fname=`get_process_stdout_filename "${absdirname}" ${given_processname} 1`
        if [ -f "${stdout_fname}" ]; then
            cat "${stdout_fname}"
        else
            echo "Error: output file could not be found!" >&2
        fi
    else
        local stdout_fname=`get_process_stdout_filename "${absdirname}" ${given_processname} 2 "${task_idx}"`
        if [ -f "${stdout_fname}" ]; then
            cat "${stdout_fname}"
        else
            echo "Error: output file could not be found!" >&2
        fi
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

get_out "${pdir}" "${process}"

exit $?
