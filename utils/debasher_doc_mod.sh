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
    echo "debasher_doc_mod generates documentation about a given module"
    echo "type \"debasher_mod_info --help\" to get usage information"
}

########
usage()
{
    echo "debasher_doc_mod          -m <string> [-s <string>]"
    echo "                          [--show-cmdline-opts] [--help]"
    echo ""
    echo "-m <string>               Module file name"
    echo "-s <string>               Process name whose information should be obtained"
    echo "--show-cmdline-opts       Show option information"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    m_given=0
    s_given=0
    showopts_given=0
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
            "--show-cmdline-opts") showopts_given=1
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
get_process_doc_funcnames()
{
    declare -F | "$AWK" -v method_doc="${PROCESS_METHOD_NAME_DOCUMENT}" '{start=index($3,method_doc); if(start!=0 && start-1+length(method_doc)==length($3)) printf"%s\n",$3}'
}

########
obtain_info_for_module()
{
    # Load module
    source "${module_fname}"

    # Document module
    document_module "${module_fname}"

    # Get module name from file name
    local modname=`get_modname_from_absmodname "${module_fname}"`

    # Iterate over process documentation functions
    while read process_doc_func; do
        local processname=${process_doc_func%"${PROCESS_METHOD_NAME_DOCUMENT}"}
        if [  "${processname}" != "${modname}" ]; then
            document_process "${processname}" "${showopts_given}"
        fi
    done < <(get_process_doc_funcnames)
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
