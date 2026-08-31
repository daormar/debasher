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
    echo "debasher_doc_mod generates documentation about a given module"
    echo "type \"debasher_mod_info --help\" to get usage information"
}

########
usage()
{
    echo "debasher_doc_mod          -m <string> [-s <string>]"
    echo "                          [--show-opts] [--help]"
    echo ""
    echo "-m <string>               Module file name"
    echo "-s <string>               Process name whose information should be obtained"
    echo "--show-opts               Show process options information"
    echo "--show-meths              Show process methods information"
    echo "--show-vars               Show process variables information"
    echo "--show-impl               Show process implementation information"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    m_given=0
    s_given=0
    showopts_given=0
    showmeths_given=0
    showvars_given=0
    showimpl_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "-m") shift
                  if [ $# -ne 0 ]; then
                      module_fname=$1
                      m_given=1
                  fi
                  ;;
            "-s") shift
                  if [ $# -ne 0 ]; then
                      given_processname=$1
                      s_given=1
                  fi
                  ;;
            "--show-opts") showopts_given=1
                          ;;
            "--show-meths") showmeths_given=1
                          ;;
            "--show-vars") showvars_given=1
                          ;;
            "--show-impl") showimpl_given=1
                          ;;
        esac
        shift
    done
}

########
check_pars()
{
    if [ ${m_given} -eq 0 ]; then
        echo "Error! -m parameter not given!" >&2
        exit 1
    else
        if [ ! -f "${module_fname}" ]; then
            echo "Error! module file does not exist" >&2
            exit 1
        fi
    fi
}

########
obtain_info_for_module()
{
    # Load debasher module
    debasher::load_debasher_module "$module_fname" || return 1

    # Execute program function for module
    debasher::_exec_program_func_for_module "${module_fname}"

    # Show module documentation
    debasher::_show_module_documentation "${module_fname}"

    # Iterate over the program processes
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        if [ "${s_given}" -eq 0 ] || [ "${processname}" = "${given_processname}" ]; then
            debasher::_show_process_documentation "${processname}" "${showopts_given}" "${showmeths_given}" "${showvars_given}" "${showimpl_given}"
        fi
    done
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

obtain_info_for_module

exit $?
