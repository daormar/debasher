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

#############################
# PROGRAM-RELATED FUNCTIONS #
#############################

########
debasher::get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 ${command_line_file} | "$AWK" '{print $2}'` ; debasher::pipe_fail || return 1
    echo $workdir
}

########
debasher::get_quoted_cmdline_from_command_line_file()
{
    local command_line_file=$1
    "$TAIL" -1 "${command_line_file}"
}

########
debasher::get_orig_outdir_from_command_line_file()
{
    # initialize variables
    local command_line_file=$1

    # Extract information from command line file
    local workdir
    workdir=`debasher::get_orig_workdir "${command_line_file}"` || return 1
    local cmdline
    qcmdline=`debasher::get_quoted_cmdline_from_command_line_file "${command_line_file}"` || return 1
    local outdir=`debasher::get_opt_value_from_quoted_cmd "$qcmdline" "--outdir"`

    # Retrieve original output directory
    if debasher::is_absolute_path "$outdir"; then
        echo "$outdir"
    else
        echo "${workdir}/${outdir}"
    fi
}

########
debasher::get_pfile_from_command_line_file()
{
    local command_line_file=$1
    local qcmdline=`debasher::get_quoted_cmdline_from_command_line_file "${command_line_file}"`
    local pfile=`debasher::get_opt_value_from_quoted_cmd "$qcmdline" "--pfile"` || return 1
    echo "${pfile}"
}

########
debasher::get_currdir_from_command_line_file()
{
    local command_line_file=$1
    local currdir=`"${HEAD}" -1 "${command_line_file}" | "${AWK}" '{print $2}'`
    echo "${currdir}"
}

########
debasher::get_sched_from_command_line_file()
{
    local command_line_file=$1
    local qcmdline=`debasher::get_quoted_cmdline_from_command_line_file "${command_line_file}"`
    local sched=`debasher::get_opt_value_from_quoted_cmd "${qcmdline}" "--sched"` || return 1
    echo "${sched}"
}

########
debasher::get_abspfile_from_command_line_file()
{
    # Initialize variables
    local command_line_file=$1

    # Obtain program file and current dir
    local cmdline_pfile
    cmdline_pfile=`debasher::get_pfile_from_command_line_file "${command_line_file}"` || return 1
    local cmdline_currdir
    cmdline_currdir=`debasher::get_currdir_from_command_line_file "${command_line_file}"` || return 1

    # Obtain absolute program file name
    local abspfile
    pushd "${cmdline_currdir}" > /dev/null
    abspfile=`debasher::get_absolute_path "${cmdline_pfile}"`
    popd > /dev/null

    # Check if resulting program file exists
    if [ -f "${abspfile}" ]; then
        echo "${abspfile}"
        return 0
    else
        echo "Error: unable to find program file (${abspfile})" >&2
        return 1
    fi
}

########
debasher::exec_program_func_for_module()
{
    local pfile=$1

    local program_funcname
    program_funcname=`debasher::get_program_funcname "${pfile}"`

    # Add program file to stack
    DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK+=("${pfile}")

    ${program_funcname} || return 1

    # Remove program file from stack
    unset 'DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK[-1]'
}

########
debasher::get_prg_exec_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_DEBASHER_EXEC_DIRNAME}"
}

########
debasher::get_prg_exec_dir()
{
    debasher::get_prg_exec_dir_given_basedir "${DEBASHER_PROGRAM_OUTDIR}"
}

########
debasher::get_prg_graphs_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_DEBASHER_GRAPHS_DIRNAME}"
}

########
debasher::get_prg_graphs_dir()
{
    debasher::get_prg_graphs_dir_given_basedir "${DEBASHER_PROGRAM_OUTDIR}"
}

########
debasher::processname_contains_invalid_characters()
{
    local processname="$1"

    # Check characters
    if [[ "$processname" =~ ^[a-zA-Z_][a-zA-Z_0-9]*$ ]]; then
        return 1
    else
        return 0
    fi
}

########
debasher::processname_contains_reserved_suffixes()
{
    local processname="$1"

    # Check process methods
    for method in "${DEBASHER_PROCESS_METHODS[@]}"; do
        if [[ "$processname" == "$method" || "$processname" == *_"$method" ]]; then
            return 0
        fi
    done

    # Check HereDoc suffixes
    for suffix in "${DEBASHER_HEREDOC_SUFFIXES[@]}"; do
        if [[ "$processname" == "$suffix" || "$processname" == *_"$suffix" ]]; then
            return 0
        fi
    done

    return 1
}

########
debasher::is_valid_processname()
{
    local processname="$1"

    # Check characters
    if debasher::processname_contains_invalid_characters "${processname}"; then
        echo "Process name ${processname} contains invalid characters. The name should only contain letters, digits or the underscore character" >&2
        return 1
    fi

    # Check suffixes
    if debasher::processname_contains_reserved_suffixes "${processname}"; then
        echo "Process name '${processname}' collides with method '${method}'" >&2
        return 1
    fi

    return 0
}

########
debasher::is_heredoc_process()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`debasher::get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        echo "${pyexec_varname}"
        return 0
    fi

    # Try with R
    local rexec_varname=`debasher::get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        echo "${rexec_varname}"
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`debasher::get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        echo "${perlexec_varname}"
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`debasher::get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        echo "${groovyexec_varname}"
        return 0
    fi

    return 1
}

########
debasher::create_heredoc_func_body()
{
    local processname=$1
    local escaped_interpreter

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`debasher::get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        printf -v escaped_interpreter '%q' "${PYTHON}"
        echo "${escaped_interpreter} -c \"\${${pyexec_varname}}\" ${DEBASHER_PY_END_OF_OPTIONS_MARKER} \"\$@\""
        return 0
    fi

    # Try with R
    local rexec_varname=`debasher::get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        printf -v escaped_interpreter '%q' "${RSCRIPT}"
        echo "${escaped_interpreter} -e \"\${${rexec_varname}}\" ${DEBASHER_R_END_OF_OPTIONS_MARKER} \"\$@\""
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`debasher::get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        printf -v escaped_interpreter '%q' "${PERL}"
        echo "${escaped_interpreter} -e \"\${${perlexec_varname}}\" ${DEBASHER_PL_END_OF_OPTIONS_MARKER} \"\$@\""
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`debasher::get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
        printf -v escaped_interpreter '%q' "${GROOVY}"
        echo "${escaped_interpreter} -e \"\${${groovyexec_varname}}\" ${DEBASHER_GROOVY_END_OF_OPTIONS_MARKER} \"\$@\""
        return 0
    fi

    return 1
}

########
debasher::create_process_func_heredoc()
{
    local processname=$1
    local funcbody
    funcbody=$(debasher::create_heredoc_func_body "${processname}") || return 1
    eval "$processname() { ${funcbody}; }"
}

########
debasher::add_debasher_process_heredoc()
{
    local processname=$1

    # Heredoc code was provided for process
    debasher::create_process_func_heredoc "${processname}" || return 1

    # Store process name in associative array (the variable name
    # containing the heredoc is also stored)
    DEBASHER_PROGRAM_PROCESSES["${processname}"]="${comm_varname}"
}

########
debasher::add_debasher_process_func()
{
    local processname=$1

    # Store process name in associative array
    DEBASHER_PROGRAM_PROCESSES["${processname}"]=1
}

########
debasher::create_process_func_alias()
{
    local processname=$1
    local process_alias=$2

    eval "$processname() { ${process_alias} \"\$@\"; }"
}

########
debasher::add_debasher_process_alias()
{
    local processname=$1
    local process_alias=$2

    # Obtain expanded process alias
    local expanded_process_alias

    if debasher::is_valid_processname "${process_alias}" 2>/dev/null; then
        expanded_process_alias="${process_alias}"
    else
        echo "Error: alias ${process_alias} for process ${processname} has not a valid name. Aborting execution..." >&2
        return 1
    fi

    # Create process function
    debasher::create_process_func_alias "${processname}" "${process_alias}"

    # Store process name in associative array (alias information is also
    # stored)
    DEBASHER_PROGRAM_PROCESSES["${processname}"]="alias=${process_alias}"
}

########
debasher::get_interpreter_for_file()
{
    local file=$1
    local bfname=$("${BASENAME}" "${file}")

    # Extract the part after the last dot
    local extension="${bfname##*.}"

    case "$extension" in
        "${DEBASHER_BASH_FEXT}")
            echo "${BASH}"
            return 0
            ;;
        "${DEBASHER_PYTHON_FEXT}")
            echo "${PYTHON}"
            return 0
            ;;
        "${DEBASHER_R_FEXT}")
            echo "${RSCRIPT}"
            return 0
            ;;
        "${DEBASHER_PERL_FEXT}")
            echo "${PERL}"
            return 0
            ;;
        "${DEBASHER_GROOVY_FEXT}")
            echo "${GROOVY}"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
debasher::create_process_func_ext_alias()
{
    local processname=$1
    local process_ext_alias=$2
    local interpreter_for_file=$(debasher::get_interpreter_for_file "${process_ext_alias}")

    if [ -n "${interpreter_for_file}" ]; then
        local escaped_interpreter
        printf -v escaped_interpreter '%q' "${interpreter_for_file}"
        local escaped_alias
        printf -v escaped_alias '%q' "${process_ext_alias}"
        eval "$processname() { ${escaped_interpreter} ${escaped_alias} \"\$@\"; }"
    else
        echo "Error: external alias ${process_ext_alias} for process ${processname} is not valid: no suitable interpreter was found. Aborting execution..." >&2
        return 1
    fi
}

########
debasher::get_external_file_for_process_alias()
{
    local current_pfile_dir=$1
    local process_alias=$2

    echo "${current_pfile_dir}/${process_alias}"
}

########
debasher::add_debasher_process_ext_alias()
{
    local processname=$1
    local process_ext_alias=$2
    local current_pfile_dir=$("${DIRNAME}" "${DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK[-1]}")

    # Check if alias corresponds to an external file

    # Get tentative name of external file
    local external_file
    if debasher::is_absolute_path "${process_ext_alias}"; then
        external_file="${process_ext_alias}"
        echo "Warning: external alias for process ${processname} uses an absolute path (${external_file}). This workflow is not portable across machines." >&2
    else
        external_file="$(debasher::get_external_file_for_process_alias "${current_pfile_dir}" "${process_ext_alias}")"
    fi

    # Check if file exists
    if [ ! -f "${external_file}" ]; then
        echo "Error: external alias ${process_ext_alias} for process ${processname} is not valid. Aborting execution..." >&2
        return 1
    fi

    # Create process function
    debasher::create_process_func_ext_alias "${processname}" "${external_file}" || return 1

    # Store process name in associative array (alias information is also
    # stored)
    DEBASHER_PROGRAM_PROCESSES["${processname}"]="ext_alias=${external_file}"
}

########
debasher::get_alias_related_funcs()
{
    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        if [[ "${DEBASHER_PROGRAM_PROCESSES[${processname}]}" == *"alias="* ]]; then
            declare -f "${processname}"
        fi
    done
}

########
# Public: Adds a process to a DeBasher program.
#
# $1 - Name of the process to add into the program.
# $2 - Computational specifications.
# $3 - Additional specifications for the process.
#
# Examples
#
#    debasher::add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
#
# The function prints the process definition to the standard output.
# This process definition is later used debasher_exec to execute
# the program.
# Additionally, the function registers the process in a variable used
# by the DeBasher library, and creates a wrapper function when an
# alias or heredoc code is provided.
debasher::add_debasher_process()
{
    # Initialize variables
    local processname=$1
    local process_computational_specs=$2
    local process_additional_specs=$3

    # Check correctness of process name and abort execution if necessary
    if ! debasher::is_valid_processname "${processname}"; then
        echo "Error: process name ${processname} not valid. Aborting execution..." >&2
        exit 1
    fi

    # Check if process has already been defined
    if [[ -v 'DEBASHER_PROGRAM_PROCESSES["${processname}"]' ]]; then
        echo "Error: process name ${processname} has already been defined. Aborting execution..." >&2
        exit 1
    fi

    # Treat heredoc code if provided
    if debasher::is_heredoc_process "${processname}" >/dev/null; then
        debasher::add_debasher_process_heredoc "${processname}" || exit 1
    else
        # Treat process alias if provided
        local process_alias=$(debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "alias")
        if [ "${process_alias}" != "${DEBASHER_ATTR_NOT_FOUND}" ]; then
            # A process alias was given
            debasher::add_debasher_process_alias "${processname}" "${process_alias}" || exit 1
        else
            local process_ext_alias=$(debasher::extract_attr_from_process_additional_specs "${process_additional_specs}" "ext_alias")
            if [ "${process_ext_alias}" != "${DEBASHER_ATTR_NOT_FOUND}" ]; then
                # A process external alias was given
                debasher::add_debasher_process_ext_alias "${processname}" "${process_ext_alias}" || exit 1
            else
                # No heredoc nor aliases were given
                debasher::add_debasher_process_func "${processname}"
            fi
        fi
    fi

    # Print process program line
    echo "${processname}" "${process_computational_specs}" "${DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP}" "${process_additional_specs}"
}

########
# Public: Adds a process to a DeBasher program.
#
# $1 - Name of the process to add into the program.
# $2 - Computational specifications.
# $3 - Additional specifications for the process.
#
# Examples
#
#    add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
#
# The function prints the process definition to the standard output.
# This process definition is later used debasher_exec to execute
# the program.
# Additionally, the function registers the process in a variable used
# by the DeBasher library, and creates a wrapper function when an
# alias or heredoc code is provided.
add_debasher_process() { debasher::add_debasher_process "$@"; }

########
debasher::add_debasher_program()
{
    # Initialize variables
    local modname=$1
    local pfile=$(debasher::determine_full_module_name "${modname}")

    # Execute program function for module and store output entries in a
    # temporary file (the purpose is to enable function execution
    # without using any sub-shell)
    debasher::exec_program_func_for_module "${pfile}"
}

add_debasher_program() { debasher::add_debasher_program "$@"; }

########
debasher::program_uses_fifos()
{
    if [ "${#DEBASHER_PROGRAM_FIFOS[@]}" -eq 0 ]; then
        return 1
    else
        return 0
    fi
}

########
debasher::get_number_of_program_fifos()
{
    echo "${#DEBASHER_PROGRAM_FIFOS[@]}"
}
