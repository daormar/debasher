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

##############################
# PROGRAM-RELATED FUNCTIONS #
##############################

########
get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 ${command_line_file} | "$AWK" '{print $2}'` ; pipe_fail || return 1
    echo $workdir
}

########
get_quoted_cmdline_from_command_line_file()
{
    local command_line_file=$1
    "$TAIL" -1 "${command_line_file}"
}

########
get_orig_outdir_from_command_line_file()
{
    # initialize variables
    local command_line_file=$1

    # Extract information from command line file
    local workdir
    workdir=`get_orig_workdir "${command_line_file}"` || return 1
    local cmdline
    qcmdline=`get_quoted_cmdline_from_command_line_file "${command_line_file}"` || return 1
    local outdir=`get_opt_value_from_quoted_cmd "$qcmdline" "--outdir"`

    # Retrieve original output directory
    if is_absolute_path "$outdir"; then
        echo "$outdir"
    else
        echo "${workdir}/${outdir}"
    fi
}

########
get_pfile_from_command_line_file()
{
    local command_line_file=$1
    local qcmdline=`get_quoted_cmdline_from_command_line_file "${command_line_file}"`
    local pfile=`get_opt_value_from_quoted_cmd "$qcmdline" "--pfile"` || return 1
    echo "${pfile}"
}

########
get_currdir_from_command_line_file()
{
    local command_line_file=$1
    local currdir=`"${HEAD}" -1 "${command_line_file}" | "${AWK}" '{print $2}'`
    echo "${currdir}"
}

########
get_sched_from_command_line_file()
{
    local command_line_file=$1
    local qcmdline=`get_quoted_cmdline_from_command_line_file "${command_line_file}"`
    local sched=`get_opt_value_from_quoted_cmd "${qcmdline}" "--sched"` || return 1
    echo "${sched}"
}

########
get_abspfile_from_command_line_file()
{
    # Initialize variables
    local command_line_file=$1

    # Obtain program file and current dir
    local cmdline_pfile
    cmdline_pfile=`get_pfile_from_command_line_file "${command_line_file}"` || return 1
    local cmdline_currdir
    cmdline_currdir=`get_currdir_from_command_line_file "${command_line_file}"` || return 1

    # Obtain absolute program file name
    local abspfile
    pushd "${cmdline_currdir}" > /dev/null
    abspfile=`get_absolute_path "${cmdline_pfile}"`
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
exec_program_func_for_module()
{
    local pfile=$1

    local program_funcname
    program_funcname=`get_program_funcname "${pfile}"`

    # Add program file to stack
    PROGRAM_FUNC_FOR_MODULE_PFILE_STACK+=("${pfile}")

    ${program_funcname} || return 1

    # Remove program file from stack
    unset 'PROGRAM_FUNC_FOR_MODULE_PFILE_STACK[-1]'
}

########
get_prg_exec_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_EXEC_DIRNAME}"
}

########
get_prg_exec_dir()
{
    get_prg_exec_dir_given_basedir "${PROGRAM_OUTDIR}"
}

########
get_prg_graphs_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_GRAPHS_DIRNAME}"
}

########
get_prg_graphs_dir()
{
    get_prg_graphs_dir_given_basedir "${PROGRAM_OUTDIR}"
}

########
is_valid_processname()
{
    local input="$1"
    if [[ "$input" =~ ^[a-zA-Z_][a-zA-Z_0-9]*$ ]]; then
        return 0  # True
    else
        return 1  # False
    fi
}

########
get_alias_related_funcs()
{
    for processname in "${!PROGRAM_PROCESSES[@]}"; do
        if [ "${PROGRAM_PROCESSES[${processname}]}" != "1" ]; then
            declare -f "${processname}"
        fi
    done
}

########
get_external_file_for_process_alias()
{
    local current_pfile_dir=$1
    local process_alias=$2

    echo "${current_pfile_dir}/${process_alias}"
}

########
get_interpreter_for_file()
{
    local file=$1
    local bfname=$("${BASENAME}" "${file}")

    # Extract the part after the last dot
    local extension="${bfname##*.}"

    case "$extension" in
        "${BASH_FEXT}")
            echo "${BASH}"
            return 0
            ;;
        "${PYTHON_FEXT}")
            echo "${PYTHON}"
            return 0
            ;;
        "${R_FEXT}")
            echo "${RSCRIPT}"
            return 0
            ;;
        "${PERL_FEXT}")
            echo "${PERL}"
            return 0
            ;;
        "${GROOVY_FEXT}")
            echo "${GROOVY}"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
get_pyexec_command()
{
    if [ -z "${PYTHON}" ]; then
        echo "Error: no Python interpreter was found!" >&2
        return 1
    fi

    echo "${PYTHON} -c"
}

########
get_rexec_command()
{
    if [ -z "${RSCRIPT}" ]; then
        echo "Error: no R script interpreter was found!" >&2
        return 1
    fi

    echo "${RSCRIPT} -e"
}

########
get_perlexec_command()
{
    if [ -z "${PERL}" ]; then
        echo "Error: no Perl interpreter was found!" >&2
        return 1
    fi

    echo "${PERL} -e"
}

########
get_groovyexec_command()
{
    if [ -z "${GROOVY}" ]; then
        echo "Error: no Groovy interpreter was found!" >&2
        return 1
    fi

    echo "${GROOVY} -e"
}

########
get_exec_command_for_heredoc_process()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_pyexec_command "${pyexec_varname}" || return 1
        return 0
    fi

    # Try with R
    local rexec_varname=`get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_rexec_command "${rexec_varname}" || return 1
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_perlexec_command "${perlexec_varname}" || return 1
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        get_groovyexec_command "${groovyexec_varname}" || return 1
        return 0
    fi
}

########
get_exec_commvar()
{
    local processname=$1

    # Search for a suitable function or command to execute the process

    # Try with Python
    local pyexec_varname=`get_pyexec_varname "${processname}"`
    if [ "${pyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${pyexec_varname}"
        return 0
    fi

    # Try with R
    local rexec_varname=`get_rexec_varname "${processname}"`
    if [ "${rexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${rexec_varname}"
        return 0
    fi

    # Try with Perl
    local perlexec_varname=`get_perlexec_varname "${processname}"`
    if [ "${perlexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${perlexec_varname}"
        return 0
    fi

    # Try with Groovy
    local groovyexec_varname=`get_groovyexec_varname "${processname}"`
    if [ "${groovyexec_varname}" != "${VAR_NOT_FOUND}" ]; then
        echo "${groovyexec_varname}"
        return 0
    fi
}

########
get_end_of_options_marker_given_var()
{
    local varname=$1

    # Extract the part after the last underscore
    local suffix="${varname##*_}"

    case "$suffix" in
        "${PY_VARNAME_SUFFIX}")
            echo "${PY_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "${R_VARNAME_SUFFIX}")
            echo "${R_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "${PL_VARNAME_SUFFIX}")
            echo "${PL_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        "${GROOVY_VARNAME_SUFFIX}")
            echo "${GROOVY_END_OF_OPTIONS_MARKER}"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

########
create_process_func_alias()
{
    local processname=$1
    local expanded_process_alias=$2
    local interpreter_for_file=$(get_interpreter_for_file "${expanded_process_alias}")

    if [ -n "${interpreter_for_file}" ]; then
        printf -v escaped_interpreter '%q' "${interpreter_for_file}"
        printf -v escaped_alias '%q' "${expanded_process_alias}"
        eval "$processname() { ${escaped_interpreter} ${escaped_alias} \"\$@\"; }"
    else
        eval "$processname() { ${expanded_process_alias} \"\$@\"; }"
    fi
}

########
create_process_func_heredoc()
{
    local processname=$1
    local comm_heredoc=$2
    local comm_varname=$3
    local end_of_opts_marker=$4

    eval "$processname() { ${comm_heredoc} \"\${${comm_varname}}\" ${end_of_opts_marker} \"\$@\"; }"
}

########
add_debasher_process_heredoc()
{
    local processname=$1
    local comm_heredoc=$(get_exec_command_for_heredoc_process "${processname}")
    local comm_varname=`get_exec_commvar ${processname}`
    local end_of_opts_marker=`get_end_of_options_marker_given_var ${comm_varname}`

    # Heredoc code was provided for process
    create_process_func_heredoc "${processname}" "${comm_heredoc}" "${comm_varname}" "${end_of_opts_marker}"

    # Store process name in associative array. For each process, the
    # program file of the program that adds it is registered
    PROGRAM_PROCESSES["${processname}"]="${comm_varname}"
}

########
add_debasher_process_func()
{
    local processname=$1

    # Store process name in associative array. For each process, the
    # program file of the program that adds it is registered
    PROGRAM_PROCESSES["${processname}"]=1
}

########
add_debasher_process_alias()
{
    local processname=$1
    local process_alias=$2

    # Obtain expanded process alias
    local expanded_process_alias

    if is_valid_processname "${process_alias}"; then
        expanded_process_alias="${process_alias}"
    else
        # Check if alias corresponds to an external file

        # Get tentative name of external file
        local external_file
        external_file="$(get_external_file_for_process_alias "${current_pfile_dir}" "${process_alias}")"

        # Check if file exists
        if [ ! -f "${external_file}" ]; then
            echo "Error: alias ${process_alias} for process ${processname} is not valid. Aborting execution..." >&2
            return 1
        fi

        expanded_process_alias="${external_file}"
    fi

    # Create process function
    create_process_func_alias "${processname}" "${expanded_process_alias}"

    # Store process name in associative array. For each process, the
    # program file of the program that adds it is registered
    PROGRAM_PROCESSES["${processname}"]="${expanded_process_alias}"
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
# Additionally, it registers the process in a variable used by the
# DeBasher library.
add_debasher_process()
{
    # Initialize variables
    local processname=$1
    local process_computational_specs=$2
    local process_additional_specs=$3
    local current_pfile_dir=$("${DIRNAME}" "${PROGRAM_FUNC_FOR_MODULE_PFILE_STACK[-1]}")

    # Check correctness of process name and abort execution if necessary
    if ! is_valid_processname "${processname}"; then
        echo "Error: process name ${processname} not valid. It should contain letters, digits or the underscore character. Aborting execution..." >&2
        exit 1
    fi

    # Check if process has already been defined
    if [[ -v 'PROGRAM_PROCESSES["${processname}"]' ]]; then
        echo "Error: process name ${processname} has already been defined. Aborting execution..." >&2
        exit 1
    fi

    # Treat heredoc code if provided
    local comm_heredoc=$(get_exec_command_for_heredoc_process "${processname}")
    if [ -n "${comm_heredoc}" ]; then
        add_debasher_process_heredoc "${processname}"
    else
        # Treat process alias if provided
        local process_alias=$(extract_alias_from_process_spec "${process_additional_specs}")
        if [ "${process_alias}" = "${ATTR_NOT_FOUND}" ]; then
            # No heredoc nor alias were given
            add_debasher_process_func "${processname}"
        else
            # A process alias was given
            add_debasher_process_alias "${processname}" "${process_alias}" || exit 1
        fi
    fi

    # Print process program line
    echo "${processname}" "${process_computational_specs}" "${process_additional_specs}"
}

########
add_debasher_program()
{
    # Initialize variables
    local modname=$1
    local pfile=$(determine_full_module_name "${modname}")

    # Execute program function for module and store output entries in a
    # temporary file (the purpose is to enable function execution
    # without using any sub-shell)
    exec_program_func_for_module "${pfile}"
}

########
program_uses_fifos()
{
    if [ "${#PROGRAM_FIFOS[@]}" -eq 0 ]; then
        return 1
    else
        return 0
    fi
}

########
get_number_of_program_fifos()
{
    echo "${#PROGRAM_FIFOS[@]}"
}
