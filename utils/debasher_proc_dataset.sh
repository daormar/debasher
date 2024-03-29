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
    echo "debasher_proc_dataset process samples of a given dataset"
    echo "type \"debasher_proc_dataset --help\" to get usage information"
}

########
usage()
{
    echo "debasher_proc_dataset  --pfile <string>"
    echo "                       --sched <string> [--dflt-nodes <string>]"
    echo "                       --prg-sopts <string> [--prg-opts <string>]"
    echo "                       [--help]"
    echo ""
    echo "--pfile <string>       File with program processes to be executed"
    echo "--sched <string>       Scheduler used to execute the programs"
    echo "--dflt-nodes <string>  Default set of nodes used to execute the program"
    echo "--prg-sopts <string>   File containing a string with program options per"
    echo "                       sample"
    echo "--prg-opts <string>    File containing a string with program options"
    echo "--help                 Display this help and exit"
}

########
read_pars()
{
    pfile_given=0
    sched_given=0
    dflt_nodes_given=0
    prg_sopts_given=0
    prg_opts_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "--pfile") shift
                  if [ $# -ne 0 ]; then
                      pfile=$1
                      pfile_given=1
                  fi
                  ;;
            "--sched") shift
                  if [ $# -ne 0 ]; then
                      sched=$1
                      sched_given=1
                  fi
                  ;;
            "--dflt-nodes") shift
                  if [ $# -ne 0 ]; then
                      dflt_nodes=$1
                      dflt_nodes_given=1
                  fi
                  ;;
            "--prg-sopts") shift
                  if [ $# -ne 0 ]; then
                      prg_sopts=$1
                      prg_sopts_given=1
                  fi
                  ;;
            "--prg-opts") shift
                  if [ $# -ne 0 ]; then
                      prg_opts=$1
                      prg_opts_given=1
                  fi
                  ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${pfile_given} -eq 0 ]; then
        echo "Error! --pfile parameter not given!" >&2
        exit 1
    else
        if [ ! -f "${pfile}" ]; then
            echo "Warning! file ${pfile} does not exist" >&2
        fi
    fi

    if [ ${sched_given} -eq 0 ]; then
        echo "Error, --sched option should be given" >&2
        exit 1
    fi

    if [ ${prg_sopts_given} -eq 0 ]; then
        echo "Error, --prg-sopts option should be given" >&2
        exit 1
    fi

    if [ ${prg_sopts_given} -eq 1 ]; then
        if [ ! -f "${prg_sopts}" ]; then
            echo "Error! file ${prg_sopts} does not exist" >&2
            exit 1
        fi
    fi

    if [ ${prg_opts_given} -eq 1 ]; then
        if [ ! -f "${prg_opts}" ]; then
            echo "Error! file ${prg_opts} does not exist" >&2
            exit 1
        fi
    fi
}

########
absolutize_file_paths()
{
    if [ ${pfile_given} -eq 1 ]; then
        pfile=`get_absolute_path "${pfile}"`
    fi

    if [ ${prg_sopts_given} -eq 1 ]; then
        prg_sopts=`get_absolute_path "${prg_sopts}"`
    fi

    if [ ${prg_opts_given} -eq 1 ]; then
        prg_opts=`get_absolute_path "${prg_opts}"`
    fi
}

########
print_pars()
{
    if [ ${pfile_given} -eq 1 ]; then
        echo "--pfile is ${pfile}" >&2
    fi

    if [ ${sched_given} -eq 1 ]; then
        echo "--sched is ${sched}" >&2
    fi

    if [ ${prg_sopts_given} -eq 1 ]; then
        echo "--prg-sopts is ${prg_sopts}" >&2
    fi

    if [ ${dflt_nodes_given} -eq 1 ]; then
        echo "--dflt-nodes is ${dflt_nodes}" >&2
    fi

    if [ ${prg_opts_given} -eq 1 ]; then
        echo "--prg-opts is ${prg_opts}" >&2
    fi
}

########
get_dflt_nodes_opt()
{
    if [ ${dflt_nodes_given} -eq 1 ]; then
        echo "--dflt-nodes ${dflt_nodes}"
    else
        echo ""
    fi
}

########
get_prg_opts_str()
{
    "${CAT}" "${prg_opts}"
}

########
esc_dq()
{
    "$SED" 's/"/\\\"/g' <<< "$1"
}

########
process_pars()
{
    # Set options
    local prg_opts_str
    if [ ${prg_opts_given} -eq 1 ]; then
        prg_opts_str=`get_prg_opts_str`
    else
        prg_opts_str=""
    fi

    # Get pipe_exec path
    local pipe_exec_path
    debasher_exec_path=`get_debasher_exec_path`

    # Read metadata file
    local entry_num=1
    entry_num=1
    local prg_sopts_str
    while read prg_sopts_str; do

        # Obtain --dflt-nodes option
        dflt_nodes_opt=`get_dflt_nodes_opt`

        # Print command to execute program
        normalize_cmd "\"$(esc_dq "${debasher_exec_path}")\" --pfile \"$(esc_dq "${pfile}")\" --sched ${sched} ${dflt_nodes_opt} ${prg_sopts_str} ${prg_opts_str}"

        entry_num=$((entry_num + 1))

    done < "${prg_sopts}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

absolutize_file_paths || exit 1

print_pars || exit 1

process_pars || exit 1
