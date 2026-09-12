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
    echo "                          [--show-shdirs] [--show-all-shdirs] [--show-all-envvars]"
    echo "                          [--show-meths] [--show-meths-with-code]"
    echo "                          [--show-vars] [--show-vars-with-values]"
    echo "                          [--show-opts] [--show-opthnd]"
    echo "                          [--show-impl] [--show-specs]"
    echo "                          [--resolve-var <string>]... [--help]"
    echo ""
    echo "-m <string>               Module file name"
    echo "-s <string>               Process name whose information should be obtained"
    echo "--show-shdirs             Show shared directories defined directly by the module"
    echo "--show-all-shdirs         Show every shared directory reachable from the program"
    echo "                          (the module plus every module it loads, transitively)"
    echo "--show-all-envvars        Show every variable newly bound while loading the module"
    echo "                          (the module plus every module it loads, transitively),"
    echo "                          excluding names already set beforehand and the engine's"
    echo "                          own internal bookkeeping"
    echo "--resolve-var <string>    Show the value of a variable already set after loading"
    echo "                          the module (may be given multiple times); this is a"
    echo "                          plain variable read, not a function call"
    echo "--show-meths              Show process methods information"
    echo "--show-meths-with-code    Show process methods information, including the full"
    echo "                          code of every method the process defines"
    echo "--show-vars               Show process variables information"
    echo "--show-vars-with-values   Show process variables information, including the"
    echo "                          value of every variable the process defines"
    echo "--show-opts               Show process options information"
    echo "--show-opthnd             Show process option handler information"
    echo "--show-impl               Show process implementation information"
    echo "--show-specs              Show process computational and additional specifications"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    m_given=0
    s_given=0
    showshdirs_given=0
    showallshdirs_given=0
    showallenvvars_given=0
    showmeths_given=0
    showmethswithcode_given=0
    showvars_given=0
    showvarswithvalues_given=0
    showopts_given=0
    showopthnd_given=0
    showimpl_given=0
    showspecs_given=0
    resolvevars=()
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
            "--show-shdirs") showshdirs_given=1
                          ;;
            "--show-all-shdirs") showallshdirs_given=1
                          ;;
            "--show-all-envvars") showallenvvars_given=1
                          ;;
            "--show-meths") showmeths_given=1
                          ;;
            "--show-meths-with-code") showmethswithcode_given=1
                          ;;
            "--show-vars") showvars_given=1
                          ;;
            "--show-vars-with-values") showvarswithvalues_given=1
                          ;;
            "--show-opts") showopts_given=1
                          ;;
            "--show-opthnd") showopthnd_given=1
                          ;;
            "--show-impl") showimpl_given=1
                          ;;
            "--show-specs") showspecs_given=1
                          ;;
            "--resolve-var") shift
                          if [ $# -ne 0 ]; then
                              resolvevars+=("$1")
                          fi
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
    # Capture every variable name already bound before the module (and
    # everything it loads) is sourced, so --show-all-envvars can report
    # only what loading actually added. Must happen before the load
    # below, and is skipped entirely when not requested.
    local envvars_before=""
    local envvars_after=""
    if [ "${showallenvvars_given}" -eq 1 ]; then
        envvars_before=$(compgen -v)
    fi

    # Load debasher module
    debasher::load_debasher_module "$module_fname" || return 1

    # Snapshot right after loading (sourcing) the module — where a real
    # module's own variables are actually defined — rather than after
    # the next step below, which only registers processes and, in
    # doing so, leaks a few of the engine's own loop variables (see
    # debasher::_show_all_program_envvars).
    if [ "${showallenvvars_given}" -eq 1 ]; then
        envvars_after=$(compgen -v)
    fi

    # Execute program function for module
    debasher::_exec_program_func_for_module "${module_fname}"

    # Show module documentation
    debasher::_show_module_documentation "${module_fname}" "${showshdirs_given}"

    # Show every shared directory reachable from the program (own,
    # plus every module it loads transitively) — distinct from
    # --show-shdirs, which is scoped to the module named after -m
    if [ "${showallshdirs_given}" -eq 1 ]; then
        echo "## All Shared Directories"
        echo ""
        debasher::_show_all_program_shared_dirs
        echo ""
    fi

    # Show every variable newly bound by loading the module — distinct
    # from --resolve-var, which requires already knowing the name to
    # look up
    if [ "${showallenvvars_given}" -eq 1 ]; then
        echo "## All Module Variables"
        echo ""
        debasher::_show_all_program_envvars "${envvars_before}" "${envvars_after}"
        echo ""
    fi

    # Show the current value of every variable requested via
    # --resolve-var, once the module (and everything it loads) has
    # been sourced. This is a plain bash indirect-expansion read
    # (${!varname}), not a function call, so it carries no more
    # execution risk than the module load debasher_doc_mod already
    # performs for every other --show-* section.
    if [ ${#resolvevars[@]} -gt 0 ]; then
        echo "## Resolved Variables"
        echo ""
        local varname
        for varname in "${resolvevars[@]}"; do
            echo "- \`${varname}\`: \`${!varname}\`"
        done
        echo ""
    fi

    # Iterate over the program processes
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        if [ "${s_given}" -eq 0 ] || [ "${processname}" = "${given_processname}" ]; then
            debasher::_show_process_documentation "${processname}" "${showmeths_given}" "${showmethswithcode_given}" "${showvars_given}" "${showvarswithvalues_given}" "${showopts_given}" "${showopthnd_given}" "${showimpl_given}" "${showspecs_given}"
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
