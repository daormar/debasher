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

# INCLUDE BASH LIBRARY
. "${panpipe_bindir}"/panpipe_lib || exit 1

########
print_desc()
{
    echo "pipe_stop stops program execution"
    echo "type \"pipe_stop --help\" to get usage information"
}

########
usage()
{
    echo "panpipe_stop              -d <string> [-s <string>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-s <string>               Process name whose status should be determined"
    echo "-i                        Show scheduler ids for program processes"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    s_given=0
    i_given=0
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
            "-s") shift
                  if [ $# -ne 0 ]; then
                      given_processname=$1
                      s_given=1
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
        set_panpipe_scheduler ${sched} || return 1
    fi
}

########
process_status_for_pfile()
{
    local dirname=$1
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

    # Load panpipe modules
    load_panpipe_module "$pfile" || return 1

    # Configure scheduler
    configure_scheduler $sched || return 1

    # Read information about the processes to be executed
    local num_processes=0
    local num_finished=0
    local num_inprogress=0
    local num_unfinished=0
    local num_unfinished_but_runnable=0
    local num_todo=0
    while read process_spec; do
        # Increase number of processes
        num_processes=$((num_processes + 1))

        # Extract process information
        local processname=`extract_processname_from_process_spec "$process_spec"`

        # If s option was given, continue to next iteration if process
        # name does not match with the given one
        if [ ${s_given} -eq 1 -a "${given_processname}" != $processname ]; then
            continue
        fi

        # Check process status
        local status=`get_process_status "${absdirname}" ${processname}`

        # Obtain ids
        local ids_info
        ids_info=`read_ids_from_files "${absdirname}" ${processname}`

        # Print status
        echo "PROCESS: $processname ; STATUS: $status ; SCHED_IDS: ${ids_info} (Stopping...)"
        stop_process "${ids_info}"

        # Increase lineno
    done < <(exec_program_func_for_module "${pfile}")
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

process_status_for_pfile "${pdir}" "${pfile}"

exit $?
