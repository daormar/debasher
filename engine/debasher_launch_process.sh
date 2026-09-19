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

# INCLUDE BASH LIBRARIES
. "${debasher_pkglibdir}"/debasher_lib || exit 1
. "${debasher_pkglibdir}"/debasher_builtin_sched_lib || exit 1

########
print_desc()
{
    echo "debasher_launch_process launches (or relaunches) one process of a program, or one task of an array process, using the built-in scheduler's own launch mechanism"
    echo "type \"debasher_launch_process --help\" to get usage information"
}

########
usage()
{
    echo "debasher_launch_process   -d <string> -p <string> [-t <int>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory of the program (not of the process)"
    echo "-p <string>               Name of the process to be launched"
    echo "-t <int>                  Task index, if the process is an array of tasks"
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
                      exit 0
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-p") shift
                  if [ $# -ne 0 ]; then
                      processname=$1
                      p_given=1
                  fi
                  ;;
            "-t") shift
                  if [ $# -ne 0 ]; then
                      taskidx=$1
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
    fi

    if [ ${p_given} -eq 0 ]; then
        echo "Error! -p parameter not given!" >&2
        exit 1
    fi

    if [ ${t_given} -eq 1 ]; then
        if ! debasher::_str_is_natural_number "${taskidx}"; then
            echo "Error! -t parameter must be a natural number" >&2
            exit 1
        fi
    fi
}

########
launch_process()
{
    local absdirname=$(debasher::_get_absolute_path "${pdir}")

    # If no task index was given, the process is not an array
    local task_idx=${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}
    if [ ${t_given} -eq 1 ]; then
        task_idx=${taskidx}
    fi

    debasher_builtin_sched::_launch "${absdirname}" "${processname}" "${task_idx}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

launch_process

exit $?
