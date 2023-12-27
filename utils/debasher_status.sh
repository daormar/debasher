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
    echo "debasher_status gets status of program processes"
    echo "type \"debasher_status --help\" to get usage information"
}

########
usage()
{
    echo "debasher_status           -d <string> [-s <string>] [-i]"
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
            "-i") if [ $# -ne 0 ]; then
                      i_given=1
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

    # Load debasher modules
    load_debasher_module "$pfile" || return 1

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

        # Obtain ids if requested
        local ids_info
        if [ ${i_given} -eq 1 ]; then
            ids_info=`read_ids_from_files "${absdirname}" ${processname}`
        fi

        # Print status
        if [ ${i_given} -eq 0 ]; then
            echo "PROCESS: $processname ; STATUS: $status"
        else
            echo "PROCESS: $processname ; STATUS: $status ; SCHED_IDS: ${ids_info}"
        fi

        # Treat process status
        case $status in
            ${FINISHED_PROCESS_STATUS}) num_finished=$((num_finished + 1))
                                        ;;
            ${INPROGRESS_PROCESS_STATUS}) num_inprogress=$((num_inprogress + 1))
                                          ;;
            ${UNFINISHED_PROCESS_STATUS}) num_unfinished=$((num_unfinished + 1))
                                          ;;
            ${UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}) num_unfinished_but_runnable=$((num_unfinished_but_runnable + 1))
                                                       ;;
            ${TODO_PROCESS_STATUS}) num_todo=$((num_todo + 1))
                                    ;;
        esac
    done < <(exec_program_func_for_module "${pfile}")

    # Print summary
    echo "* SUMMARY: num_processes= ${num_processes} ; finished= ${num_finished} ; inprogress= ${num_inprogress} ; unfinished= ${num_unfinished} ; unfinished_but_runnable= ${num_unfinished_but_runnable} ; todo= ${num_todo}" >&2

    # Return error if program is not finished
    if [ ${num_finished} -eq ${num_processes} ]; then
        return ${PROGRAM_FINISHED_EXIT_CODE}
    else
        if [ ${num_inprogress} -gt 0 ]; then
            return ${PROGRAM_IN_PROGRESS_EXIT_CODE}
        else
            return ${PROGRAM_UNFINISHED_EXIT_CODE}
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

process_status_for_pfile "${pdir}" "${pfile}"

exit $?
