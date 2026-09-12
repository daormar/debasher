# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
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
. "${debasher_pkglibdir}"/debasher_lib || exit 1

########
print_desc()
{
    echo "debasher_get_fifo_mirror gets the mirrored output of a process's fifo"
    echo "type \"debasher_get_fifo_mirror --help\" to get usage information"
}

########
usage()
{
    echo "debasher_get_fifo_mirror -d <string> -p <string> -f <string> [-t <int>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for program processes"
    echo "-p <string>               Process name owning the mirrored fifo"
    echo "-f <string>               Name of fifo (as given to define_fifo_opt)"
    echo "-t <int>                  Index of task array for process"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    p_given=0
    f_given=0
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
                      process=$1
                      p_given=1
                  fi
                  ;;
            "-f") shift
                  if [ $# -ne 0 ]; then
                      fifoname=$1
                      f_given=1
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

        if [ ! -f "${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}" ]; then
            echo "Error! ${pdir}/${DEBASHER_PRG_COMMAND_LINE_BASENAME} file is missing" >&2
            exit 1
        fi

        if [ ${p_given} -eq 0 ]; then
            echo "Error! -p parameter not given" >&2
            exit 1
        fi

        if [ ${f_given} -eq 0 ]; then
            echo "Error! -f parameter not given" >&2
            exit 1
        fi
    fi
}

########
configure_scheduler()
{
    local sched=$1
    if [ ${sched} != ${DEBASHER_OPT_NOT_FOUND} ]; then
        debasher::_set_debasher_scheduler ${sched} || return 1
    fi
}

########
get_mirror()
{
    local dirname=$1
    local process=$2
    local absdirname=$(debasher::_get_absolute_path "${dirname}")
    local command_line_file="${absdirname}/${DEBASHER_PRG_COMMAND_LINE_BASENAME}"

    # Extract information from DEBASHER_PRG_COMMAND_LINE_BASENAME file
    local pfile
    pfile=$(debasher::_get_abspfile_from_command_line_file "${command_line_file}") || return 1
    local sched
    sched=$(debasher::_get_sched_from_command_line_file "${command_line_file}") || return 1

    # Get original output directory
    local orig_outdir
    orig_outdir=$(debasher::_get_orig_outdir_from_command_line_file "${command_line_file}") || return 1

    # Show warning if directory provided as option is different than the
    # original working directory
    if debasher::_dirnames_are_equal "${orig_outdir}" "${absdirname}"; then
        local moved_outdir="no"
    else
        echo "Warning: program output directory was moved (original directory: ${orig_outdir})" >&2
        local moved_outdir="yes"
    fi

    # Configure scheduler
    configure_scheduler $sched || return 1

    # debasher::_get_fifo_mirror_filename resolves the mirror path via
    # DEBASHER_PROGRAM_OUTDIR (same as every other fifo path helper in
    # engine/debasher_lib_opts.sh), which is only set as a side effect of
    # a full program execution — set it explicitly here since this is a
    # standalone CLI invocation.
    debasher::_set_debasher_outdir "${absdirname}"

    # Augmented fifo name matches DEBASHER_PROGRAM_FIFOS's own key
    # convention ("<processname>/<fifoname>", see
    # debasher::_define_fifo_task_idx); task index doesn't participate
    # in it, mirroring how per-task fifo names are already
    # distinguished by the process author's own generator.
    local augm_fifoname="${process}/${fifoname}"
    local mirror_fname=$(debasher::_get_fifo_mirror_filename "${augm_fifoname}")

    if [ -f "${mirror_fname}" ]; then
        cat "${mirror_fname}"
    else
        echo "Error: mirror file for fifo \"${fifoname}\" of process ${process} could not be found (the fifo may not be mirrored, or the process has not run yet)!" >&2
        return 1
    fi
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

get_mirror "${pdir}" "${process}"

exit $?
