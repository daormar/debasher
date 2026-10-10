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

###############################
# OPTION DEFINITION FUNCTIONS #
###############################

########
debasher::_esc_dq()
{
    local escaped_str=${1//\"/\\\"};
    echo "${escaped_str}"
}

########
debasher::_serialize_args()
{
    local serial_args=""
    for arg in "$@"; do
        if [ -z "$serial_args" ]; then
            serial_args=${arg}
        else
            serial_args=${serial_args}${DEBASHER_ARG_SEP}${arg}
        fi
    done
    echo "${serial_args}"
}

########
debasher::_serialize_args_nameref()
{
    local -n var_ref=$1;
    shift
    local serial_args=""
    for arg in "$@"; do
        if [ -z "$serial_args" ]; then
            serial_args=${arg}
        else
            serial_args=${serial_args}${DEBASHER_ARG_SEP}${arg}
        fi
    done
    var_ref="${serial_args}"
}

########
debasher::_deserialize_args_given_sep()
{
    local serial_args=$1
    local sep=$2

    if [ -z "${serial_args}" ]; then
        unset DEBASHER_DESERIALIZED_ARGS
        declare -ga DEBASHER_DESERIALIZED_ARGS
    else
        local new_sep=$'\n'
        local preproc_sargs="${serial_args//${sep}/$new_sep}"
        unset DEBASHER_DESERIALIZED_ARGS
        declare -ga DEBASHER_DESERIALIZED_ARGS
        while IFS=${new_sep} read -r; do DEBASHER_DESERIALIZED_ARGS+=( "${REPLY}" ); done <<< "${preproc_sargs}"
    fi
}

########
debasher::_deserialize_args()
{
    local serial_args=$1

    debasher::_deserialize_args_given_sep "${serial_args}" "${DEBASHER_ARG_SEP}"
}

########
debasher::_serialize_cmd_as_qstr()
{
    printf '%q ' "$@"
    printf '\n'
}

########
# Print a resolved options array (flag, value, flag, value, ... with a
# value-less flag simply not followed by one, see
# debasher::_dedup_resolved_opts) one option per line, each flag paired
# with its value (if any) on the same line, printf '%q'-escaped (used
# to dump a process's resolved command-line options to its ".opts"
# file for the webui's "See options" inspect action).
debasher::_print_opts_as_qstrings()
{
    local -a args=("$@")
    local n=${#args[@]}
    local i=0
    while [ $i -lt $n ]; do
        local opt=${args[$i]}
        i=$((i + 1))
        if [ $i -lt $n ] && ! debasher::_str_is_option "${args[$i]}"; then
            printf '%q %q\n' "${opt}" "${args[$i]}"
            i=$((i + 1))
        else
            printf '%q\n' "${opt}"
        fi
    done
}

########
# Convert a string serialized with a custom separator to a printf '%q'
# escaped string. The separator is passed as a parameter.
debasher::_sep_serialized_to_qstr()
{
    local sep=$1
    local sargs=$2
    local preproc_sargs
    preproc_sargs="${sargs//${sep}/$'\n'}"
    local array=()
    if [ -n "${sargs}" ]; then
        # An empty element is an option given an empty value, printed as ''
        while IFS= read -r; do
            array+=("${REPLY}")
        done <<< "${preproc_sargs}"
        printf '%q ' "${array[@]}"
    fi
}

########
debasher::_replace_blank_with_word()
{
    local str=$1
    local word=$2
    echo ${str// /$word}
}

########
debasher::_replace_word_with_blank()
{
    local str=$1
    local word=$2
    echo ${str//$word/ }
}

########
debasher::_memoize_opts()
{
    local cmdline=$1

    debasher::_deserialize_args "${cmdline}"

    # memoize_opts receives the full command line, so
    # DEBASHER_DESERIALIZED_ARGS[0] is the command name itself and must
    # be skipped before scanning for options.
    local cmdname="${DEBASHER_DESERIALIZED_ARGS[0]}"
    set -- "${DEBASHER_DESERIALIZED_ARGS[@]:1}"

    while [ $# -gt 0 ]; do
        if ! debasher::_str_is_option "$1"; then
            echo "Warning: unexpected value ($1), skipping..." >&2
            shift
            continue
        fi

        local opt="$1"
        shift

        if [ $# -eq 0 ]; then
            DEBASHER_MEMOIZED_OPTS[$opt]=${DEBASHER_VOID_VALUE}
            continue
        fi

        if debasher::_str_is_option "$1"; then
            DEBASHER_MEMOIZED_OPTS[$opt]=${DEBASHER_VOID_VALUE}
            continue
        fi

        DEBASHER_MEMOIZED_OPTS[$opt]="$1"
        shift
    done
}

########
debasher::_check_opt_given()
{
    local cmdline=$1
    local opt=$2

    # Convert string to array (result is placed into the
    # DEBASHER_DESERIALIZED_ARGS variable)
    debasher::_deserialize_args "${cmdline}"

    # Scan DEBASHER_DESERIALIZED_ARGS
    i=0
    while [ $i -lt ${#DEBASHER_DESERIALIZED_ARGS[@]} ]; do
        if [ ${DEBASHER_DESERIALIZED_ARGS[$i]} = "${opt}" ]; then
            return 0
        fi
        i=$((i+1))
    done

    # Option not given
    return 1
}

########
debasher::_check_memoized_opt()
{
    local opt=$1

    # Check if option was not given
    if [ -z "${DEBASHER_MEMOIZED_OPTS[$opt]}" ]; then
        return 1
    else
        return 0
    fi
}

########
debasher::_check_opt_given_memoiz()
{
    local cmdline=$1
    local opt=$2

    if [ "${DEBASHER_LAST_PROC_LINE_MEMOPTS}" = "$cmdline" ]; then
        # Given line was previously processed, return memoized result
        debasher::_check_memoized_opt $opt || return 1
    else
        # Process not memoized line
        debasher::_memoize_opts "$cmdline"

        # Store processed line
        DEBASHER_LAST_PROC_LINE_MEMOPTS="$cmdline"

        # Return result
        debasher::_check_memoized_opt $opt || return 1
    fi
}

########
# Get option value from a command string escaped with printf '%q'.
# The use of eval to parse the command string is safe because printf '%q'
# guarantees that all special characters are escaped, preventing code injection.
# Returns 1 if option not found.
debasher::_get_opt_value_from_quoted_cmd()
{
    local cmd_str=$1
    local opt=$2
    local -a cmd

    eval "cmd=(${cmd_str})"

    local i
    for (( i=0; i<${#cmd[@]}; i++ )); do
        if [[ "${cmd[$i]}" == "$opt" ]]; then
            echo "${cmd[$i+1]}"
            return 0
        fi
    done

    # Option not found
    echo "${DEBASHER_OPT_NOT_FOUND}"
    return 1
}

########
debasher::_get_opt_value_from_func_args()
{
    local opt=$1
    shift

    while [ $# -gt 0 ]; do
        if [ "$1" != "${opt}" ]; then
            shift
            continue
        fi

        shift

        # No token left after this option: no value present
        if [ $# -eq 0 ]; then
            echo "${DEBASHER_VOID_VALUE}"
            return 1
        fi

        # If the next token is itself an option, this option has no value
        if debasher::_str_is_option "$1"; then
            echo "${DEBASHER_VOID_VALUE}"
            return 1
        fi

        echo "$1"
        return 0
    done

    # Option not found
    echo "${DEBASHER_OPT_NOT_FOUND}"
    return 1
}

########
# Public: Reads the value of a given option from function arguments.
#
# $1 - Option name whose value we want to obtain.
# $2,$3,...,$n - List of function arguments (typically they are provided
#                by the caller using the special parameter "$@").
#
# Examples
#
#   local str=$(debasher::read_opt_value_from_func_args "-s" "$@")
#
# The function prints the value of the option if it was given, or the "DEBASHER_OPT_NOT_FOUND" constant otherwise.
debasher::read_opt_value_from_func_args()
{
    local opt=$1

    # Get value for option
    local value=$(debasher::_get_opt_value_from_func_args "$@")

    # If the value is a descriptor and opt is not an output option, then
    # we should read the descriptor
    if debasher::_str_is_val_descriptor "${value}" && ! debasher::_str_is_output_option "${opt}"; then
        debasher::_read_value_from_desc "${value}" || return 1
    else
        echo "${value}"
    fi
}

########
# Public: Reads the value of a given option from function arguments.
#
# $1 - Option name whose value we want to obtain.
# $2,$3,...,$n - List of function arguments (typically they are provided
#                by the caller using the special parameter "$@").
#
# Examples
#
#   local str=$(read_opt_value_from_func_args "-s" "$@")
#
# The function prints the value of the option if it was given, or the "DEBASHER_OPT_NOT_FOUND" constant otherwise.
read_opt_value_from_func_args() { debasher::read_opt_value_from_func_args "$@"; }

########
# Public: Reads whether a given flag was provided in function arguments.
#
# $1 - Flag name to check for.
# $2,$3,...,$n - List of function arguments (typically they are provided
#                by the caller using the special parameter "$@").
#
# Examples
#
#   if debasher::read_flag_from_func_args "-m" "$@"; then
#
# The function returns 0 if the flag was given, 1 otherwise.
debasher::read_flag_from_func_args()
{
    local flag=$1
    shift

    while [ $# -gt 0 ]; do
        if [ "$1" = "${flag}" ]; then
            return 0
        fi
        shift
    done

    return 1
}

########
# Public: Reads whether a given flag was provided in function arguments.
#
# $1 - Flag name to check for.
# $2,$3,...,$n - List of function arguments (typically they are provided
#                by the caller using the special parameter "$@").
#
# Examples
#
#   if read_flag_from_func_args "-m" "$@"; then
#
# The function returns 0 if the flag was given, 1 otherwise.
read_flag_from_func_args() { debasher::read_flag_from_func_args "$@"; }

########
# Public: Reads the value of a given option from a serialized command
# line.
#
# $1 - Serialized command line (as stored in a process's "cmdline"
#      variable, typically received as an argument to an option
#      definition function).
# $2 - Option name whose value we want to obtain.
#
# Examples
#
#   local n=$(debasher::read_opt_value_from_line "${cmdline}" "-n")
#
# The function prints the value of the option if it was given, or the "DEBASHER_OPT_NOT_FOUND" constant otherwise.
debasher::read_opt_value_from_line()
{
    local cmdline=$1
    local opt=$2

    # Convert string to array (result is placed into the
    # DEBASHER_DESERIALIZED_ARGS variable)
    debasher::_deserialize_args "${cmdline}"

    # Get opt value
    debasher::_get_opt_value_from_func_args "${opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
}

########
# Public: Reads the value of a given option from a serialized command
# line.
#
# $1 - Serialized command line (as stored in a process's "cmdline"
#      variable, typically received as an argument to an option
#      definition function).
# $2 - Option name whose value we want to obtain.
#
# Examples
#
#   local n=$(read_opt_value_from_line "${cmdline}" "-n")
#
# The function prints the value of the option if it was given, or the "DEBASHER_OPT_NOT_FOUND" constant otherwise.
read_opt_value_from_line() { debasher::read_opt_value_from_line "$@"; }

########
# Public: Reads whether a given flag was provided in a serialized
# command line.
#
# $1 - Serialized command line (as stored in a process's "cmdline"
#      variable, typically received as an argument to an option
#      definition function).
# $2 - Flag name to check for.
#
# Examples
#
#   if debasher::read_flag_from_line "${cmdline}" "-m"; then
#
# The function returns 0 if the flag was given, 1 otherwise.
debasher::read_flag_from_line()
{
    local cmdline=$1
    local flag=$2

    # Convert string to array (result is placed into the
    # DEBASHER_DESERIALIZED_ARGS variable)
    debasher::_deserialize_args "${cmdline}"

    # Check for flag
    debasher::read_flag_from_func_args "${flag}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
}

########
# Public: Reads whether a given flag was provided in a serialized
# command line.
#
# $1 - Serialized command line (as stored in a process's "cmdline"
#      variable, typically received as an argument to an option
#      definition function).
# $2 - Flag name to check for.
#
# Examples
#
#   if read_flag_from_line "${cmdline}" "-m"; then
#
# The function returns 0 if the flag was given, 1 otherwise.
read_flag_from_line() { debasher::read_flag_from_line "$@"; }

########
debasher::_read_memoized_opt_value()
{
    local opt=$1

    # Check if option was not given or it had void value
    if [ -z "${DEBASHER_MEMOIZED_OPTS[$opt]}" -o "${DEBASHER_MEMOIZED_OPTS[$opt]}" = ${DEBASHER_VOID_VALUE} ]; then
        echo ${DEBASHER_OPT_NOT_FOUND}
        return 1
    else
        echo "${DEBASHER_MEMOIZED_OPTS[$opt]}"
        return 0
    fi
}

########
debasher::_read_opt_value_from_line_memoiz()
{
    local cmdline=$1
    local opt=$2

    if [ "${DEBASHER_LAST_PROC_LINE_MEMOPTS}" = "$cmdline" ]; then
        # Given line was previously processed, return memoized result
        _OPT_VALUE_=$(debasher::_read_memoized_opt_value $opt) || return 1
    else
        # Process not memoized line
        debasher::_memoize_opts "$cmdline"

        # Store processed line
        DEBASHER_LAST_PROC_LINE_MEMOPTS="$cmdline"

        # Return result
        _OPT_VALUE_=$(debasher::_read_memoized_opt_value $opt) || return 1
    fi
}

########
# Public: Explains command-line option.
#
# WARNING: This function is deprecated.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   debasher::explain_cmdline_opt "-s" "<string>" "String to be displayed"
#
# The function does not return any value.
debasher::explain_cmdline_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}")
    if [ -z "${proc_name}" ]; then
        proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}")
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_TASK_OPT[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_IS_CMDLINE[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_IS_MANDATORY[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_TYPE[$proc_opt]=$type
    DEBASHER_PROGRAM_OPT_DESC[$proc_opt]=$desc
    DEBASHER_PROGRAM_OPT_CATEG[$proc_opt]=$categ
    DEBASHER_PROGRAM_CATEG_MAP[$categ]=1
}

########
# Public: Explains command-line option.
#
# WARNING: This function is deprecated.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   explain_cmdline_opt "-s" "<string>" "String to be displayed"
#
# The function does not return any value.
explain_cmdline_opt() { debasher::explain_cmdline_opt "$@"; }

########
# Public: Explains option.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   debasher::explain_opt "-s" "<string>" "String to be displayed"
#
# The function does not return any value.
debasher::explain_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}")
    if [ -z "${proc_name}" ]; then
        proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}")
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_TASK_OPT[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_TYPE[$proc_opt]=$type
    DEBASHER_PROGRAM_OPT_DESC[$proc_opt]=$desc
    DEBASHER_PROGRAM_OPT_CATEG[$proc_opt]=$categ
    DEBASHER_PROGRAM_CATEG_MAP[$categ]=1
}

########
# Public: Explains option.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   explain_opt "-s" "<string>" "String to be displayed"
#
# The function does not return any value.
explain_opt() { debasher::explain_opt "$@"; }

########
# Public: Explains flag.
#
# $1 - Flag name.
# $2 - Flag description.
# $3 - Flag category ("GENERAL" category by default).
#
# Examples
#
#   debasher::explain_flag "-m" "Show output in markdown format"
#
# The function does not return any value.
debasher::explain_flag()
{
    local opt=$1
    local desc=$2
    local categ=$3

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}")
    if [ -z "${proc_name}" ]; then
        proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}")
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_TASK_OPT[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_TYPE[$proc_opt]=""
    DEBASHER_PROGRAM_OPT_DESC[$proc_opt]=$desc
    DEBASHER_PROGRAM_OPT_CATEG[$proc_opt]=$categ
    DEBASHER_PROGRAM_CATEG_MAP[$categ]=1
}

########
# Public: Explains flag.
#
# $1 - Flag name.
# $2 - Flag description.
# $3 - Flag category ("GENERAL" category by default).
#
# Examples
#
#   explain_flag "-m" "Show output in markdown format"
#
# The function does not return any value.
explain_flag() { debasher::explain_flag "$@"; }

########
# Public: Explains task shaping option, an option given on the command
# line that only the methods that define the options of the process
# (define_opts, or generate_opts_size and generate_opts) read, to
# decide how many tasks the process has and what each one gets, and
# that no task of the process receives. A task shaping option is
# always a command-line option and always mandatory: the process does
# not mark it in its identify_cmdline_opts method.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   debasher::explain_task_shaping_opt "-w" "<int>" "Number of workers"
#
# The function does not return any value.
debasher::explain_task_shaping_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_TASK_SHAPING_OPTS}")

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays. The option is not marked as a
    # command-line option here, so that a mark that identify_cmdline_opts
    # puts on it can be told apart (see
    # debasher::_check_opt_names_vs_explain)
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_TASK_SHAPING[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_IS_MANDATORY[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_TYPE[$proc_opt]=$type
    DEBASHER_PROGRAM_OPT_DESC[$proc_opt]=$desc
    DEBASHER_PROGRAM_OPT_CATEG[$proc_opt]=$categ
    DEBASHER_PROGRAM_CATEG_MAP[$categ]=1
}

########
# Public: Explains task shaping option.
#
# $1 - Option name.
# $2 - Data type of option value.
# $3 - Option description.
# $4 - Option category ("GENERAL" category by default).
#
# Examples
#
#   explain_task_shaping_opt "-w" "<int>" "Number of workers"
#
# The function does not return any value.
explain_task_shaping_opt() { debasher::explain_task_shaping_opt "$@"; }

########
# Public: Identify option/flag as a command-line option.
#
# $1 - Option name.
#
# Examples
#
#   debasher::opt_is_cmdline "-s"
#
# The function does not return any value.
debasher::opt_is_cmdline()
{
    local opt=$1

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}")

    # Define option as a command-line options
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_CMDLINE[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_IS_MANDATORY[$proc_opt]=1
}

########
# Public: Identify option/flag as a command-line option.
#
# $1 - Option name.
#
# Examples
#
#   opt_is_cmdline "-s"
#
# The function does not return any value.
opt_is_cmdline() { debasher::opt_is_cmdline "$@"; }

########
# Public: Identify option/flag as a non-mandatory command-line option.
#
# $1 - Option name.
#
# Examples
#
#   debasher::opt_is_non_mandatory_cmdline "-s"
#
# The function does not return any value.
debasher::opt_is_non_mandatory_cmdline()
{
    local opt=$1

    # Obtain caller process name
    local proc_name=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}")

    # Define option as a command-line options
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_CMDLINE[$proc_opt]=1
    DEBASHER_PROGRAM_OPT_IS_MANDATORY[$proc_opt]=0
}

########
# Public: Identify option/flag as a non-mandatory command-line option.
#
# $1 - Option name.
#
# Examples
#
#   opt_is_non_mandatory_cmdline "-s"
#
# The function does not return any value.
opt_is_non_mandatory_cmdline() { debasher::opt_is_non_mandatory_cmdline "$@"; }

########
debasher::_print_program_opts()
{
    local only_cmdline_opts=$1
    local lineno=0
    # Iterate over option categories
    local categ
    for categ in ${!DEBASHER_PROGRAM_CATEG_MAP[@]}; do
        if [ ${lineno} -gt 0 ]; then
            echo ""
        fi
        echo "CATEGORY: ${categ}"
        # Iterate over processname plus options
        local key
        for key in ${!DEBASHER_PROGRAM_OPT_TYPE[@]}; do
            local processname
            local opt
            processname="${key%%"${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"*}"
            opt="${key#*"${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"}"
            # An option is a command-line option only when the process's
            # identify_cmdline_opts (or the legacy explain_cmdline_opt)
            # marked it so: explaining it leaves the mark unset. A task
            # shaping option is always one
            local is_task_shaping=0
            if [ "${DEBASHER_PROGRAM_OPT_IS_TASK_SHAPING[${key}]}" = 1 ]; then
                is_task_shaping=1
            fi
            if [ "${only_cmdline_opts}" -eq 1 ] && [ "${DEBASHER_PROGRAM_OPT_IS_CMDLINE[${key}]}" != 1 ] && [ "${is_task_shaping}" -eq 0 ]; then
                continue
            fi

            # Check if option belongs to current category
            if [ ${DEBASHER_PROGRAM_OPT_CATEG[${key}]} = $categ ]; then
                # Print option, telling a task shaping option apart,
                # since the process function never receives it
                local proc_info="[${processname}]"
                if [ "${is_task_shaping}" -eq 1 ]; then
                    proc_info="[${processname}, task shaping]"
                fi
                if [ -z "${DEBASHER_PROGRAM_OPT_TYPE[$key]}" ]; then
                    echo "${opt} ${DEBASHER_PROGRAM_OPT_DESC[$key]} ${proc_info}"
                else
                    echo "${opt} ${DEBASHER_PROGRAM_OPT_TYPE[$key]} ${DEBASHER_PROGRAM_OPT_DESC[$key]} ${proc_info}"
                fi
            fi
        done

        lineno=$((lineno + 1))
    done
}

########
debasher::_print_program_cmdline_opts()
{
    local only_cmdline_opts=1
    debasher::_print_program_opts ${only_cmdline_opts}
}

########
debasher::_define_fifo_task_idx()
{
    local fifoname=$1
    local processname=$2
    local task_idx=$3
    local mirrored=$4
    local kind=$5
    local opt=$6

    # Get augmented fifo name
    local augm_fifoname="${processname}/${fifoname}"

    # A fifo is named after its owner process, not after the task of it
    # that defines it, so two tasks of an array that define fifos with the
    # same name would define the same fifo. Defining it again from the
    # same task is not an error: an option generator runs several times
    # for the same task
    local owner_task="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}"
    if [[ -v DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"] ]] && [ "${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}" != "${owner_task}" ]; then
        local prev_task="${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
        echo "Error: fifo ${fifoname} of process ${processname} is defined by task ${prev_task} and by task ${task_idx}; each task needs a fifo name of its own" >&2
        return 1
    fi

    # A mirror tap is set on the value of an output option (see
    # debasher::_start_fifo_mirror_taps_for_process), so a mirrored fifo
    # has to be defined through one
    if [ "${mirrored}" = "1" ] && ! debasher::_str_is_output_option "${opt}"; then
        echo "Error: fifo ${fifoname} of process ${processname} is mirrored, but its option ${opt} is not an output option (-out* or --out*)" >&2
        return 1
    fi

    # Store name of FIFO in associative arrays
    DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]=${owner_task}

    # Register FIFO reader as external initially (this registration will
    # be corrected later when analyzing the FIFOs read by each process)
    DEBASHER_FIFO_READERS["${augm_fifoname}"]=${DEBASHER_EXTERNAL_FIFO_END}

    # Flag fifo as mirrored if requested (see
    # debasher::_start_fifo_mirror_taps_for_process)
    if [ "${mirrored}" = "1" ]; then
        DEBASHER_FIFO_MIRRORED["${augm_fifoname}"]=1
    fi

    # Record the fifo's tag, if it has one (see DEBASHER_FIFO_KINDS)
    if [ -n "${kind}" ]; then
        DEBASHER_FIFO_KINDS["${augm_fifoname}"]=${kind}
    fi

    # Record the option through which the owner defines the fifo
    DEBASHER_FIFO_OWNER_OPTS["${augm_fifoname}"]=${opt}
}

########
# Reads the optional flags of define_fifo_opt and define_fifo_opt_generator:
# --mirror, and at most one of --control and --external (the fifo's tag, see
# DEBASHER_FIFO_KINDS). Whether a tag is allowed in the program is checked
# once the program is loaded (see debasher::_validate_program_fifo_kinds),
# not here: an option generator also runs again inside the script of each of
# its tasks, where the program type is not known.
#
# $1 - Name of the public function, for the error messages.
# $2 - Name of the variable that receives 1 if --mirror was given, 0 if not.
# $3 - Name of the variable that receives the tag, or the empty string.
# $4... - The flags.
#
# Returns 0 if every flag is valid; otherwise prints an error and returns 1.
# Gets the process and the task whose options are being defined, into the
# variables named $1 and $2: the process of the _define_opts method or
# option generator in the call stack, and the task index that the engine
# keeps while it calls the option generator (see
# debasher::_call_generate_opts), or else the number of option lists that
# _define_opts has registered so far for the process.
debasher::_get_defining_task()
{
    local -n defining_task_proc_ref=$1
    local -n defining_task_idx_ref=$2

    # Not finding a method of a kind in the call stack is not an error here
    defining_task_proc_ref=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}") || true
    if [ -n "${defining_task_proc_ref}" ]; then
        defining_task_idx_ref=${DEBASHER_GENERATING_TASK_IDX:-0}
    else
        defining_task_proc_ref=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}") || true
        defining_task_idx_ref=${DEBASHER_PROCESS_OPT_LIST_LEN["${defining_task_proc_ref}"]:-0}
    fi
}

########
# Calls the option generator $1 with the arguments that follow it, the
# fifth of them being the task index, and keeps that index while the
# generator runs, so that the define_* functions that it calls know the
# task whose options they define (see debasher::_get_defining_task).
debasher::_call_generate_opts()
{
    local generate_opts_funcname=$1
    shift
    local DEBASHER_GENERATING_TASK_IDX=$5
    "${generate_opts_funcname}" "$@"
}

########
debasher::_read_fifo_opt_flags()
{
    local funcname=$1
    local -n fifo_flags_mirrored_ref=$2
    local -n fifo_flags_kind_ref=$3
    shift 3

    fifo_flags_mirrored_ref=0
    fifo_flags_kind_ref=""
    local flag
    for flag in "$@"; do
        case "${flag}" in
            "--mirror")
                debasher::_check_fifo_mirror_allowed "${funcname}" || return 1
                fifo_flags_mirrored_ref=1
                ;;
            "--control"|"--external")
                if [ -n "${fifo_flags_kind_ref}" ]; then
                    echo "${funcname}: Error, a fifo takes at most one of --control and --external" >&2
                    return 1
                fi
                fifo_flags_kind_ref="${flag#--}"
                ;;
            *)
                echo "${funcname}: Error, unknown flag ${flag}" >&2
                return 1
                ;;
        esac
    done
}

########
# Public: Defines fifo option for process.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
# $4 - (optional) "--mirror": also duplicate everything this process
#      writes to the fifo into a separate, non-destructively readable
#      mirror log file (see debasher::_start_fifo_mirror_taps_for_process).
#      Only allowed on an output option (-out* or --out*), through
#      which the process writes to the fifo. Not allowed in a resident
#      program (the program aborts when loaded).
#      In a resident program, at most one of these tags may be given as
#      well (refused in a general program when it is loaded):
#      "--control": the reader's end of the fifo is a control port;
#      "--external": the reader's end is an external port, fed from
#      outside the program. A fifo whose writer is outside the program is
#      defined by its reader, and has to carry one of the two tags (see
#      the design doc's "Channel kinds declared with the fifo").
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option,
# except for a tagged fifo whose writer is outside the program.
#
# Examples
#
#   debasher::define_fifo_opt "-outf" "${fifoname}" "optlist"
#   debasher::define_fifo_opt "-outf" "${fifoname}" "optlist" --mirror
#   debasher::define_fifo_opt "-trigger" "${fifoname}" "optlist" --control
#
# The function does not return any value
debasher::define_fifo_opt()
{
    local opt=$1
    local fifoname=$2
    local varname=$3
    local mirrored kind
    debasher::_read_fifo_opt_flags "define_fifo_opt" mirrored kind "${@:4}" || exit 1

    # Get the process and the task whose options are being defined, by
    # _define_opts or by an option generator
    local processname task_idx
    debasher::_get_defining_task processname task_idx

    # Define FIFO
    debasher::_define_fifo_task_idx "${fifoname}" "${processname}" "${task_idx}" "${mirrored}" "${kind}" "${opt}" || exit 1

    # Get absolute name of FIFO
    local abs_fifoname=$(debasher::_get_absolute_fifoname "${processname}" "${fifoname}")

    # Define option for FIFO
    debasher::define_opt "${opt}" "${abs_fifoname}" "${varname}" || return 1
}

########
# Public: Defines fifo option for process.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
# $4... - (optional) "--mirror", and "--control" or "--external" (see
#      debasher::define_fifo_opt).
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option,
# except for a tagged fifo whose writer is outside the program.
#
# Examples
#
#   define_fifo_opt "-outf" "${fifoname}" "optlist"
#
# The function does not return any value
define_fifo_opt() { debasher::define_fifo_opt "$@"; }

########
# Public: Defines a fifo option generator.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Index of the task whose options the generator is producing.
# $4 - Name of variable that will store the information about the option to be added.
# $5... - (optional) "--mirror", and "--control" or "--external" (see
#      debasher::define_fifo_opt).
#
# The same function as debasher::define_fifo_opt, which an option
# generator may call too: it is kept for the modules that call it, and
# ignores the task index it is given, since the engine knows the task
# whose options are being defined.
#
# Examples
#
#   debasher::define_fifo_opt_generator "-outf" "${fifoname}" "${task_idx}" "optlist"
#
# The function does not return any value
debasher::define_fifo_opt_generator()
{
    debasher::define_fifo_opt "$1" "$2" "$4" "${@:5}"
}

########
# Public: Defines a fifo option generator.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Index of the task whose options the generator is producing.
# $4 - Name of variable that will store the information about the option to be added.
# $5... - (optional) "--mirror", and "--control" or "--external" (see
#      debasher::define_fifo_opt).
#
# The same function as define_fifo_opt, kept for the modules that call
# it; it ignores the task index it is given (see
# debasher::define_fifo_opt_generator).
#
# Examples
#
#   define_fifo_opt_generator "-outf" "${fifoname}" "${task_idx}" "optlist"
#
# The function does not return any value
define_fifo_opt_generator() { debasher::define_fifo_opt_generator "$@"; }

########
# Public: Defines a shared directory owned by a module.
#
# $1 - Name of the shared directory.
#
# This function should only be called from a module's shared_dirs
# function (see load_debasher_module). The directory is created once,
# before any process in the program is executed, and its absolute path
# can be retrieved from any process by means of get_absolute_shdirname.
#
# Examples
#
#   debasher::define_shared_dir "data"
#
# The function does not return any value
debasher::define_shared_dir()
{
    local shared_dir=$1

    # Check that the call is not being made from a process' define_opts
    # or generate_opts method, since shared directories can only be
    # owned by a module
    local processname=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}")
    if [ -z "${processname}" ]; then
        processname=$(debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}")
    fi
    if [ -n "${processname}" ]; then
        echo "define_shared_dir: Error, this function should only be called from a module's shared_dirs function" >&2
        exit 1
    fi

    # Register shared directory as owned by the module
    DEBASHER_PROGRAM_SHDIRS["${shared_dir}"]=${DEBASHER_SHDIR_MODULE_OWNER}
}

########
# Public: Defines a shared directory owned by a module.
#
# $1 - Name of the shared directory.
#
# This function should only be called from a module's shared_dirs
# function (see load_debasher_module). The directory is created once,
# before any process in the program is executed, and its absolute path
# can be retrieved from any process by means of get_absolute_shdirname.
#
# Examples
#
#   define_shared_dir "data"
#
# The function does not return any value
define_shared_dir() { debasher::define_shared_dir "$@"; }

########
debasher::get_cmdline_opt()
{
    local cmdline=$1
    local opt=$2

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value="${_OPT_VALUE_}"

    # Return option
    echo "${value}"
}

get_cmdline_opt() { debasher::get_cmdline_opt "$@"; }

########
# Public: Defines process option from command-line option.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_opt "${cmdline}" "-o" "optlist"
#
# The function does not return any value
debasher::define_cmdline_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt" || { debasher::errmsg "$opt option not found" ; return 1; }
    local value="${_OPT_VALUE_}"

    # Add option
    debasher::define_opt $opt "$value" $varname
}

########
# Public: Defines process option from command-line option.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_opt "${cmdline}" "-o" "optlist"
#
# The function does not return any value
define_cmdline_opt() { debasher::define_cmdline_opt "$@"; }

########
# Public: Defines process option from a process specification attribute
# (computational or additional). The attribute is searched for first
# among the process's computational specs (cpus, mem, time, nodes,
# account, partition, throttle) and, if not found there, among its
# additional specs (processdeps, force, alias, ext_alias); aborts if
# found in neither.
#
# $1 - Process specification, as given to the `define_opts` method.
# $2 - Name of the option to be added.
# $3 - Name of the process specification attribute (e.g. "cpus", "mem").
# $4 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_procspec_opt "${process_spec}" "-cpus" "cpus" "optlist"
#
# The function does not return any value
debasher::define_procspec_opt()
{
    local process_spec=$1
    local opt=$2
    local specname=$3
    local varname=$4

    # Look for the attribute among computational specs
    local comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    local value=$(debasher::extract_attr_from_process_comp_specs "${comp_specs}" "${specname}")

    # Fall back to additional specs if not found
    if [ "${value}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        local additional_specs=$(debasher::extract_process_additional_specs "${process_spec}")
        value=$(debasher::extract_attr_from_process_additional_specs "${additional_specs}" "${specname}")
    fi

    if [ "${value}" = "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        debasher::errmsg "${specname} attribute not found in process spec (option: $opt)"
        return 1
    fi

    # Add option
    debasher::define_opt "$opt" "$value" "$varname"
}

########
# Public: Defines process option from a process specification attribute
# (computational or additional). The attribute is searched for first
# among the process's computational specs (cpus, mem, time, nodes,
# account, partition, throttle) and, if not found there, among its
# additional specs (processdeps, force, alias, ext_alias); aborts if
# found in neither.
#
# $1 - Process specification, as given to the `define_opts` method.
# $2 - Name of the option to be added.
# $3 - Name of the process specification attribute (e.g. "cpus", "mem").
# $4 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_procspec_opt "${process_spec}" "-cpus" "cpus" "optlist"
#
# The function does not return any value
define_procspec_opt() { debasher::define_procspec_opt "$@"; }

########
# Public: Defines process option only if it was given through the command-line.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_opt_if_given "${cmdline}" "-o" "optlist"
#
# The function does not return any value
debasher::define_cmdline_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value=${_OPT_VALUE_}

    if [ "$value" != ${DEBASHER_OPT_NOT_FOUND} ]; then
        # Add option
        debasher::define_opt "$opt" "$value" "$varname"
    fi
}

########
# Public: Defines process option only if it was given through the command-line.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_opt_if_given "${cmdline}" "-o" "optlist"
#
# The function does not return any value
define_cmdline_opt_if_given() { debasher::define_cmdline_opt_if_given "$@"; }

########
# Public: Defines process option from a command-line option, verifying
# that it names an existing file and normalizing it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_infile_opt "${cmdline}" "-f" "optlist"
#
# The function does not return any value
debasher::define_cmdline_infile_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt" || { debasher::errmsg "$opt option not found" ; return 1; }
    local value="${_OPT_VALUE_}"

    # Verify file exists and normalize to an absolute path
    debasher::_file_exists "$value" || { debasher::errmsg "file $value does not exist ($opt option)" ; return 1; }
    value=$(debasher::_get_absolute_path "$value")

    # Add option
    debasher::define_opt "$opt" "$value" "$varname"
}

########
# Public: Defines process option from a command-line option, verifying
# that it names an existing file and normalizing it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_infile_opt "${cmdline}" "-f" "optlist"
#
# The function does not return any value
define_cmdline_infile_opt() { debasher::define_cmdline_infile_opt "$@"; }

########
# Public: Defines process option from a command-line option that names
# an existing file, only if the option was given through the command
# line; verifies the file exists and normalizes it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_infile_opt_if_given "${cmdline}" "-f" "optlist"
#
# The function does not return any value
debasher::define_cmdline_infile_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value=${_OPT_VALUE_}

    if [ "$value" != ${DEBASHER_OPT_NOT_FOUND} ]; then
        # Verify file exists and normalize to an absolute path
        debasher::_file_exists "$value" || { debasher::errmsg "file $value does not exist ($opt option)" ; return 1; }
        value=$(debasher::_get_absolute_path "$value")

        # Add option
        debasher::define_opt "$opt" "$value" "$varname"
    fi
}

########
# Public: Defines process option from a command-line option that names
# an existing file, only if the option was given through the command
# line; verifies the file exists and normalizes it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_infile_opt_if_given "${cmdline}" "-f" "optlist"
#
# The function does not return any value
define_cmdline_infile_opt_if_given() { debasher::define_cmdline_infile_opt_if_given "$@"; }

########
# Public: Defines flag only if it was given through the command-line.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_flag_if_given "${cmdline}" "-o" "optlist"
#
# The function does not return any value
debasher::define_cmdline_flag_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    if debasher::_check_opt_given "$cmdline" "$opt"; then
        # Add option
        debasher::define_flag "$opt" "$varname"
    fi
}

########
# Public: Defines process flag only if it was given through the command-line.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_flag_if_given "${cmdline}" "-o" "optlist"
#
# The function does not return any value
define_cmdline_flag_if_given() { debasher::define_cmdline_flag_if_given "$@"; }

########
# Public: Defines process option from the output of another process.
#
# $1 - Option name.
# $2 - Name of process that will be connected with current one.
# $3 - Name of output option belonging to the the process to be connected.
# $4 - Name of the variable to store the new option.
#
# Examples
#
#   debasher::define_opt_from_proc_out "-in" "process_to_be_connected" "-out" optlist
#
# The function does not return any value
debasher::define_opt_from_proc_out()
{
    local opt=$1
    local proc=$2
    local out_opt=$3
    local varname=$4

    local task_idx=0
    debasher::define_opt_from_proc_task_out "${opt}" "${proc}" "${task_idx}" "${out_opt}" "${varname}"
}

########
# Public: Defines process option from the output of another process.
#
# $1 - Option name.
# $2 - Name of process that will be connected with current one.
# $3 - Name of output option belonging to the the process to be connected.
# $4 - Name of the variable to store the new option.
#
# Examples
#
#   define_opt_from_proc_out "-in" "process_to_be_connected" "-out" optlist
#
# The function does not return any value
define_opt_from_proc_out() { debasher::define_opt_from_proc_out "$@"; }

########
# Public: Defines process option from the output of another process.
#
# $1 - Option name.
# $2 - Name of process that will be connected with current one.
# $3 - Task index of the process to be connected.
# $4 - Name of output option belonging to the the process to be connected.
# $5 - Name of the variable to store the new option.
#
# Examples
#
#   debasher::define_opt_from_proc_task_out "-in" "process_to_be_connected" "process_task_index_to_be_connected" "-out" optlist
#
# The function does not return any value
debasher::define_opt_from_proc_task_out()
{
    local opt=$1
    local proc=$2
    local task_idx=$3
    local out_opt=$4
    local varname=$5

    # Check parameters
    if [[ "${opt}" == "-out"* || "${opt}" == "--out"* ]]; then
        debasher::errmsg "define_opt_from_proc_task_out: wrong input parameters, process option cannot start with ${opt} (it should not be an output option)"
        return 1
    else
        if [[ "${out_opt}" != "-out"* && "${out_opt}" != "--out"* ]]; then
            debasher::errmsg "define_opt_from_proc_task_out: wrong input parameters, connected process option should start with -out or --out"
            return 1
        fi
    fi

    # Generate process info
    local process_opt_info="${proc}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${out_opt}"

    # Generate value
    local value=${DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}${process_opt_info}

    # Add option
    debasher::define_opt "$opt" "$value" "$varname"
}

########
# Public: Defines process option from the output of another process.
#
# $1 - Option name.
# $2 - Name of process that will be connected with current one.
# $3 - Task index of the process to be connected.
# $4 - Name of output option belonging to the the process to be connected.
# $5 - Name of the variable to store the new option.
#
# Examples
#
#   define_opt_from_proc_task_out "-in" "process_to_be_connected" "process_task_index_to_be_connected" "-out" optlist
#
# The function does not return any value
define_opt_from_proc_task_out() { debasher::define_opt_from_proc_task_out "$@"; }

########
# Public: Gets the number of tasks of a process of the program.
#
# $1 - Name of the process.
#
# A process whose number of tasks is that of another process, or whose
# task reads every task of another process, asks for it instead of
# computing it again. The options of the processes without an option
# generator are defined before those of the processes with one, so an
# option generator can ask for the number of tasks of any process, and a
# process without one only for that of an option generator. When the
# answer is not known yet, the _generate_opts_size method of the process
# gives it, so its task shaping options have to be given. The number of
# tasks is usually read in a command substitution, whose failure has to
# stop the method that reads it.
#
# Examples
#
#   debasher::get_process_num_tasks "producer"
#
#   local n
#   n=$(debasher::get_process_num_tasks "worker") || return 1
#
# The function prints the number of tasks of the process, or nothing,
# returning 1, if it cannot be known.
debasher::get_process_num_tasks()
{
    local processname=$1

    if [[ ! -v DEBASHER_PROGRAM_PROCESSES["${processname}"] ]]; then
        echo "Error: get_process_num_tasks: ${processname} is not a process of the program" >&2
        return 1
    fi

    if ! debasher::_uses_option_generator "${processname}"; then
        # Decided by whether the process has an option generator, not by
        # whether its options happen to be defined already, which depends on
        # the order in which the processes are defined
        if [ "${DEBASHER_DEFINING_NON_GENERATOR_OPTS:-0}" -eq 1 ]; then
            echo "Error: get_process_num_tasks: process ${processname} has no option generator, so its number of tasks is only known once its options are defined, and only a process with an option generator can ask for it" >&2
            return 1
        fi
        echo "${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]:-0}"
        return 0
    fi

    if [[ -v DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"] ]]; then
        echo "${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}"
        return 0
    fi

    # An option generator whose options are not defined yet, which only
    # happens while the run is prepared
    if [ -z "${DEBASHER_DEFINING_OPTS_CMDLINE+x}" ]; then
        echo "Error: get_process_num_tasks: the number of tasks of process ${processname} is not known yet" >&2
        return 1
    fi
    local cmdline=${DEBASHER_DEFINING_OPTS_CMDLINE}
    debasher::_check_task_shaping_opts_given "${cmdline}" "${processname}" || return 1
    debasher::_compute_generator_num_tasks "${cmdline}" "${DEBASHER_INITIAL_PROCESS_SPEC["${processname}"]}" "${processname}"
}

########
# Public: Gets the number of tasks of a process of the program.
#
# $1 - Name of the process.
#
# A process whose number of tasks is that of another process, or whose
# task reads every task of another process, asks for it instead of
# computing it again. The options of the processes without an option
# generator are defined before those of the processes with one, so an
# option generator can ask for the number of tasks of any process, and a
# process without one only for that of an option generator. When the
# answer is not known yet, the _generate_opts_size method of the process
# gives it, so its task shaping options have to be given. The number of
# tasks is usually read in a command substitution, whose failure has to
# stop the method that reads it.
#
# Examples
#
#   get_process_num_tasks "producer"
#
#   local n
#   n=$(get_process_num_tasks "worker") || return 1
#
# The function prints the number of tasks of the process, or nothing,
# returning 1, if it cannot be known.
get_process_num_tasks() { debasher::get_process_num_tasks "$@"; }

########
debasher::_optname_is_correct()
{
    local funcname=$1
    local opt=$2

    if [ "${opt}" = "" ]; then
        debasher::errmsg "$funcname: option name could not be the empty string"
        return 1
    else
        if ! debasher::_str_is_option "${opt}"; then
            debasher::errmsg "$funcname: option name should be '-' or '--' followed by a letter or an underscore (${opt})"
            return 1
        fi
    fi

    return 0
}

########
debasher::_optlist_varname_is_correct()
{
    local funcname=$1
    local varname=$2

    if [ -z "${varname}" ]; then
        debasher::errmsg "$funcname: name of option list variable should not be empty"
        return 1
    else
        if [[ "${varname}" == *"${DEBASHER_OPTLIST_VARNAME_SUFFIX}" ]]; then
            return 0
        else
            debasher::errmsg "$funcname: name of option list variable should end with the suffix ${DEBASHER_OPTLIST_VARNAME_SUFFIX}"
            return 1
        fi
    fi
}

########
# Public: Defines process flag.
#
# $1 - Name of flag given in the command line.
# $2 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_flag "-o" "optlist"
#
# The function does not return any value
debasher::define_flag()
{
    local flag=$1
    local varname=$2
    local -n var_ref=$2

    # Check parameters
    debasher::_optname_is_correct "${FUNCNAME}" "$flag" || return 1
    debasher::_optlist_varname_is_correct "${FUNCNAME}" "$varname" || return 1

    if [ -z "${var_ref}" ]; then
        var_ref="${flag}"
    else
        var_ref="${var_ref}${DEBASHER_ARG_SEP}${flag}"
    fi
}

########
# Public: Defines process flag.
#
# $1 - Name of flag given in the command line.
# $2 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_flag "${cmdline}" "-o" "optlist"
#
# The function does not return any value
define_flag() { debasher::define_flag "$@"; }

########
# Public: Defines process option.
#
# $1 - Option name.
# $2 - Value associated to the option being defined.
# $3 - Name of variable that will store the information about the option to be added.
#
# Examples
#
#   debasher::define_opt "-o" "${value}" "optlist"
#
# The function does not return any value
debasher::define_opt()
{
    local opt=$1
    local value=$2
    local varname=$3
    local -n var_ref=$3

    # Check parameters
    debasher::_optname_is_correct "${FUNCNAME}" "$opt" || return 1
    debasher::_optlist_varname_is_correct "${FUNCNAME}" "$varname" || return 1

    if [ -z "${var_ref}" ]; then
        var_ref="${opt}${DEBASHER_ARG_SEP}${value}"
    else
        var_ref="${var_ref}${DEBASHER_ARG_SEP}${opt}${DEBASHER_ARG_SEP}${value}"
    fi
}

########
# Public: Defines process option.
#
# $1 - Option name.
# $2 - Value associated to the option being defined.
# $3 - Name of variable that will store the information about the option to be added.
#
# Examples
#
#   define_opt "-o" "${value}" "optlist"
#
# The function does not return any value
define_opt() { debasher::define_opt "$@"; }

########
# Defines process option whose value is a file path, resolving it
# relative to the directory of the .sh that defines the process if
# it's relative (or verifying it as an absolute path otherwise):
# same resolution debasher::_add_debasher_ext_alias_process uses for
# an external alias script, so a "file" option's value can likewise
# point at a file shipped alongside the program (e.g. via the
# webui's program-files browser) using a portable, relative path.
#
# Looks up DEBASHER_PROCESS_PFILE_DIR[process_name] rather than
# DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK directly: unlike
# ext_alias resolution (which runs synchronously inside
# add_debasher_process, while that stack still holds the right entry),
# a process's _define_opts function -- where this is called from --
# runs later, once the program/module function that registered the
# process has already returned and popped its stack entry. See
# DEBASHER_PROCESS_PFILE_DIR's declaration in debasher_lib.sh.
#
# $1 - Option name.
# $2 - File path associated to the option being defined (relative or
#      absolute).
# $3 - Name of variable that will store the information about the option to be added.
# $4 - Name of the process this option is being defined for.
debasher::define_infile_opt()
{
    local opt=$1
    local value=$2
    local varname=$3
    local process_name=$4
    local pfile_dir="${DEBASHER_PROCESS_PFILE_DIR[${process_name}]}"

    local resolved
    if ! resolved=$(debasher::_resolve_path_relative_to_pfile_dir "${value}" "${pfile_dir}" "value for option ${opt}"); then
        debasher::errmsg "file ${value} does not exist (${opt} option)"
        return 1
    fi

    debasher::define_opt "$opt" "${resolved}" "$varname"
}

########
# Public: Defines process option whose value is a file path, resolved
# relative to the .sh defining the process.
#
# $1 - Option name.
# $2 - File path associated to the option being defined (relative or
#      absolute).
# $3 - Name of variable that will store the information about the option to be added.
# $4 - Name of the process this option is being defined for.
#
# Examples
#
#   define_infile_opt "-f" "config/settings.txt" "optlist" "${process_name}"
#
# The function does not return any value
define_infile_opt() { debasher::define_infile_opt "$@"; }

########
debasher::_get_value_descriptor_name()
{
    local process_name=$1
    local opt=$2
    local task_idx=$3

    # Obtain output directory for process
    local process_outdir=$(debasher::_get_process_outdir "${process_name}")

    # Obtain value descriptor name, named after the task too, so that the
    # tasks of an array never share one
    local val_desc="${process_outdir}/${DEBASHER_VALUE_DESCRIPTOR_NAME_PREFIX}${opt}_${task_idx}"

    echo "${val_desc}"
}

########
# Public: Defines process option storing a value descriptor.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
#
# The process writes its value with write_value_to_desc. A process that
# reads it, through an option defined with define_opt_from_proc_out,
# gets the value itself from read_opt_value_from_func_args, which reads
# the descriptor on its own.
#
# Examples
#
#   debasher::define_value_desc_opt "-o" "optlist"
#
# The function does not return any value
debasher::define_value_desc_opt()
{
    local opt=$1
    local varname=$2

    # Get the process and the task whose options are being defined
    local proc_name task_idx
    debasher::_get_defining_task proc_name task_idx

    # Get name of value descriptor
    local val_desc=$(debasher::_get_value_descriptor_name "${proc_name}" "${opt}" "${task_idx}")

    # Define option
    debasher::define_opt "${opt}" "${val_desc}" "${varname}"
}

########
# Public: Defines process option storing a value descriptor.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
#
# The process writes its value with write_value_to_desc. A process that
# reads it, through an option defined with define_opt_from_proc_out,
# gets the value itself from read_opt_value_from_func_args, which reads
# the descriptor on its own.
#
# Examples
#
#   define_value_desc_opt "-o" "optlist"
#
# The function does not return any value
define_value_desc_opt() { debasher::define_value_desc_opt "$@"; }

########
debasher::_show_program_shdirs()
{
    local dirname
    for dirname in "${!DEBASHER_PROGRAM_SHDIRS[@]}"; do
        local absdir=$(debasher::get_absolute_shdirname "$dirname")
        echo "${absdir}"
    done
}

########
debasher::_register_module_program_shdirs()
{
    # Populate associative array of shared directories for the loaded
    # modules
    local absmodname
    for absmodname in "${DEBASHER_PROGRAM_MODULES[@]}"; do
        local shrdirs_funcname=$(debasher::_get_shrdirs_funcname ${absmodname})
        if debasher::_func_exists "${shrdirs_funcname}"; then
            ${shrdirs_funcname} || exit 1
        fi
    done
}

########
debasher::_show_all_program_shared_dirs()
{
    # Unlike debasher::_show_module_shared_dirs (scoped to the single
    # module named after -m), this reports every shared directory
    # reachable from the whole program: the named module plus every
    # module it load_debasher_module's, transitively (DEBASHER_PROGRAM_MODULES
    # holds all of them by the time this runs, see
    # debasher::load_debasher_module).
    DEBASHER_PROGRAM_SHDIRS=()
    debasher::_register_module_program_shdirs

    local dirname
    for dirname in "${!DEBASHER_PROGRAM_SHDIRS[@]}"; do
        echo "- \`${dirname}\`"
    done
}

########
debasher::_create_mod_shdirs()
{
    # Create shared directories for modules
    local dirname
    for dirname in "${!DEBASHER_PROGRAM_SHDIRS[@]}"; do
        local owner=${DEBASHER_PROGRAM_SHDIRS["${dirname}"]}
        if [ "${owner}" = "${DEBASHER_SHDIR_MODULE_OWNER}" ]; then
            local absdir=$(debasher::get_absolute_shdirname "$dirname")
            if [ ! -d "${absdir}" ]; then
                "${MKDIR}" -p "${absdir}" || exit 1
            fi
        fi
    done
}

########
debasher::_show_program_fifos()
{
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        echo "${augm_fifoname}" ${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]} ${DEBASHER_FIFO_READERS["${augm_fifoname}"]}
    done
}

########
debasher::_prepare_fifos_owned_by_process()
{
    local processname=$1

    # Obtain name of directory for FIFOS
    local fifodir=$(debasher::_get_absolute_fifodir)

    # Create FIFOS
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        local proc_plus_idx=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
        local proc="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
        if [ "${proc}" = "${processname}" ]; then
            local dirname=$("${DIRNAME}" "${augm_fifoname}")
            if [ ! -d "${fifodir}/${dirname}" ]; then
                "${MKDIR}" -p "${fifodir}/${dirname}"
            fi
            if [ -p "${fifodir}/${augm_fifoname}" ]; then
                "${RM}" -f "${fifodir}/${augm_fifoname}" || exit 1
            fi
            "${MKFIFO}" "${fifodir}/${augm_fifoname}" || exit 1

            # Re-create the shim fifo and truncate the mirror log for a
            # mirrored fifo, tied to the same recreate-on-rerun event as
            # the real fifo above (see
            # debasher::_start_fifo_mirror_taps_for_process).
            if [ -n "${DEBASHER_FIFO_MIRRORED["${augm_fifoname}"]+_}" ]; then
                local mirrordir=$(debasher::_get_fifo_mirror_dir)
                local shimfifo=$(debasher::_get_fifo_shim_name "${augm_fifoname}")
                local mirrorfile=$(debasher::_get_fifo_mirror_filename "${augm_fifoname}")

                if [ ! -d "${mirrordir}/${dirname}" ]; then
                    "${MKDIR}" -p "${mirrordir}/${dirname}"
                fi
                if [ -p "${shimfifo}" ]; then
                    "${RM}" -f "${shimfifo}" || exit 1
                fi
                "${MKFIFO}" "${shimfifo}" || exit 1
                : > "${mirrorfile}"
            fi
        fi
    done
}

########
# Public: Obtains the absolute path of a shared directory.
#
# $1 - Name of the shared directory (as given to define_shared_dir).
#
# Examples
#
#   local abs_shrdir=$(debasher::get_absolute_shdirname "data")
#
# The function prints the absolute path of the shared directory to the
# standard output.
debasher::get_absolute_shdirname()
{
    local shdirname=$1

    # Output absolute shared directory name
    echo "${DEBASHER_PROGRAM_OUTDIR}/${shdirname}"
}

########
# Public: Obtains the absolute path of a shared directory.
#
# $1 - Name of the shared directory (as given to define_shared_dir).
#
# Examples
#
#   local abs_shrdir=$(get_absolute_shdirname "data")
#
# The function prints the absolute path of the shared directory to the
# standard output.
get_absolute_shdirname() { debasher::get_absolute_shdirname "$@"; }

########
# Checks that a subpath given with --subdir to the function $1 stays below
# its directory: it is not empty, does not start with "/", and has no
# empty component and no component "." or "..".
debasher::_check_subpath()
{
    local funcname=$1
    local subpath=$2

    if [ -z "${subpath}" ]; then
        echo "${funcname}: Error, --subdir takes a non-empty subpath" >&2
        return 1
    fi

    if [ "${subpath:0:1}" = "/" ]; then
        echo "${funcname}: Error, the subpath ${subpath} given with --subdir is absolute" >&2
        return 1
    fi

    local -a components
    IFS='/' read -r -a components <<< "${subpath}"
    # A trailing "/" leaves no component after it, so it is checked apart
    if [ "${subpath: -1}" = "/" ]; then
        components+=("")
    fi
    local component
    for component in "${components[@]}"; do
        if [ -z "${component}" ] || [ "${component}" = "." ] || [ "${component}" = ".." ]; then
            echo "${funcname}: Error, the subpath ${subpath} given with --subdir has an empty, \".\" or \"..\" component" >&2
            return 1
        fi
    done
}

########
# Reads the flags of define_opt_from_shared_dir and
# define_opt_from_process_outdir (named $1, for the messages), from the
# arguments after $2, into the variable named $2: the subpath given with
# --subdir, or nothing.
debasher::_read_subdir_opt_flags()
{
    local funcname=$1
    local -n subdir_flags_subpath_ref=$2
    shift 2

    subdir_flags_subpath_ref=""
    while [ $# -gt 0 ]; do
        case "$1" in
            "--subdir")
                if [ $# -lt 2 ]; then
                    echo "${funcname}: Error, --subdir takes a subpath" >&2
                    return 1
                fi
                debasher::_check_subpath "${funcname}" "$2" || return 1
                subdir_flags_subpath_ref=$2
                shift 2
                ;;
            *)
                echo "${funcname}: Error, unknown flag $1" >&2
                return 1
                ;;
        esac
    done
}

########
# Public: Defines process option whose value is the absolute path of a
# shared directory, or of a shared subdirectory of it.
#
# $1 - Option name.
# $2 - Name of the shared directory (as given to define_shared_dir).
# $3 - Name of variable that will store the information about the option to be added.
# $4... - (optional) "--subdir <subpath>": the option gets the absolute
#      path of the shared subdirectory <subpath> instead, a directory
#      below the shared directory that debasher_exec creates before any
#      process runs. The subpath is relative, such as "${task_idx}" or
#      "${sample}/bam", with no empty component and no component "." or
#      "..". A shared directory for which some option asks for a shared
#      subdirectory belongs to its shared subdirectories: debasher_exec
#      removes from it every entry that is neither a shared subdirectory
#      that an option of the run asks for nor a directory on the way to
#      one, so a task writes only into its own shared subdirectory (see
#      debasher::_prepare_shared_subdirs).
#
# Examples
#
#   debasher::define_opt_from_shared_dir "-datadir" "data" "optlist"
#   debasher::define_opt_from_shared_dir "-outd" "data" "optlist" --subdir "${task_idx}"
#
# The function does not return any value
debasher::define_opt_from_shared_dir()
{
    local opt=$1
    local shdirname=$2
    local varname=$3
    local subpath
    debasher::_read_subdir_opt_flags "define_opt_from_shared_dir" subpath "${@:4}" || exit 1

    local abs_shdirname=$(debasher::get_absolute_shdirname "${shdirname}")
    if [ -z "${subpath}" ]; then
        debasher::define_opt "${opt}" "${abs_shdirname}" "${varname}"
        return
    fi

    # Register the shared subdirectory, which is only created when a run
    # is prepared, since the options of a process are also defined when
    # nothing is executed
    DEBASHER_PROGRAM_SHSUBDIRS["${shdirname}/${subpath}"]=${shdirname}

    debasher::define_opt "${opt}" "${abs_shdirname}/${subpath}" "${varname}"
}

########
# Public: Defines process option whose value is the absolute path of a
# shared directory, or of a shared subdirectory of it.
#
# $1 - Option name.
# $2 - Name of the shared directory (as given to define_shared_dir).
# $3 - Name of variable that will store the information about the option to be added.
# $4... - (optional) "--subdir <subpath>" (see
#      debasher::define_opt_from_shared_dir).
#
# Examples
#
#   define_opt_from_shared_dir "-datadir" "data" "optlist"
#   define_opt_from_shared_dir "-outd" "data" "optlist" --subdir "${task_idx}"
#
# The function does not return any value
define_opt_from_shared_dir() { debasher::define_opt_from_shared_dir "$@"; }

########
# Fails when an output option of some task holds the path of a
# subdivided shared directory, a shared directory for which some option
# of the run asks for a shared subdirectory: a task writes only into its
# own shared subdirectory, since everything else in a subdivided shared
# directory is removed when a run is prepared.
debasher::_check_no_output_opt_holds_subdivided_shdir()
{
    local -n subdivided_ref=$1

    local shdirname
    for shdirname in "${!subdivided_ref[@]}"; do
        local absdir=$(debasher::get_absolute_shdirname "${shdirname}")
        local value
        for value in "${absdir}" "${absdir}/"; do
            if [[ -v DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"] ]]; then
                local processes=${DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"]}
                processes=${processes//${DEBASHER_ASSOC_ARRAY_PROC_SEP}/ }
                processes=${processes//${DEBASHER_ASSOC_ARRAY_ELEM_SEP}/:}
                echo "Error: an output option of ${processes} holds the shared directory ${shdirname}, which has shared subdirectories; a task writes only into its own shared subdirectory (define_opt_from_shared_dir --subdir)" >&2
                return 1
            fi
        done
    done
}

########
# Fails when a process that the program no longer has, but whose exec
# directory an earlier run left, is still running: it might be writing
# into a subdivided shared directory, which is about to be pruned (the
# processes of the program were already checked before their options
# were defined).
debasher::_check_left_processes_not_running()
{
    local execdir=$(debasher::get_prg_exec_dir_given_basedir "${DEBASHER_PROGRAM_OUTDIR}")
    [ -d "${execdir}" ] || return 0

    local procdir
    for procdir in "${execdir}"/*; do
        [ -d "${procdir}" ] || continue
        local processname=$("${BASENAME}" "${procdir}")
        [[ -v DEBASHER_PROGRAM_PROCESSES["${processname}"] ]] && continue
        if debasher::_process_is_in_progress "${DEBASHER_PROGRAM_OUTDIR}" "${processname}"; then
            echo "Error: process ${processname}, which the program no longer has, is still running from an earlier run, and might be writing into a shared directory with shared subdirectories" >&2
            return 1
        fi
    done
}

########
# Fails when a component of the subpath $2 below the directory $1, the
# last one included, is a symbolic link, so that creating or emptying it
# never leaves that directory. $3 names the subdirectory for the message.
debasher::_check_subpath_has_no_link()
{
    local absroot=$1
    local subpath=$2
    local what=$3

    local path=${absroot}
    local -a components
    IFS='/' read -r -a components <<< "${subpath}"
    local component
    for component in "${components[@]}"; do
        path="${path}/${component}"
        if [ -L "${path}" ]; then
            echo "Error: ${what} goes through the symbolic link ${path}" >&2
            return 1
        fi
    done
}

########
# Adds to the associative array named $2 the paths below the directory $1,
# relative to it, that an output option of the run names, without their
# trailing "/".
debasher::_add_output_named_paths()
{
    local absroot=$1
    local -n output_named_ref=$2

    local value
    for value in "${!DEBASHER_OUT_VALUE_TO_PROCESSES[@]}"; do
        [[ "${value}" == "${absroot}/"* ]] || continue
        local relpath=${value#"${absroot}/"}
        while [ "${relpath: -1}" = "/" ]; do
            relpath=${relpath%/}
        done
        [ -n "${relpath}" ] && output_named_ref["${relpath}"]=1
    done
}

########
# Adds to the associative array named $2 every directory on the way to a
# path of the associative array named $1 (all of them relative to the same
# directory): "a" and "a/b" for "a/b/c".
debasher::_add_ways_to_paths()
{
    local -n ways_paths_ref=$1
    local -n ways_ref=$2

    local relpath
    for relpath in "${!ways_paths_ref[@]}"; do
        local parent=${relpath}
        while [[ "${parent}" == */* ]]; do
            parent=${parent%/*}
            ways_ref["${parent}"]=1
        done
    done
}

########
# Removes, from the directory $4 of a subdivided directory, whose path
# relative to that subdivided directory is $3 (empty for the subdivided
# directory itself), every entry that is neither kept whole (a key of the
# associative array named $5) nor a directory on the way to one (a key of
# the associative array named $6), looking inside the directories on the
# way. Both arrays hold paths relative to the subdivided directory, which
# $2 names for the messages. Nothing is removed when $1 is 1, and each
# entry is only named. A symbolic link is never followed: removing it
# removes the link (the subdivided directory itself may be one, which
# find -H follows).
debasher::_prune_subdivided_dir()
{
    local only_report=$1
    local what=$2
    local reldir=$3
    local absdir=$4
    local -n prune_kept_ref=$5
    local -n prune_ways_ref=$6

    local entry
    while IFS= read -r -d '' entry; do
        local relpath=${entry##*/}
        [ -n "${reldir}" ] && relpath="${reldir}/${relpath}"

        # What is kept whole is not looked inside
        [[ -v prune_kept_ref["${relpath}"] ]] && continue

        # A directory on the way to what is kept is looked inside
        if [[ -v prune_ways_ref["${relpath}"] ]] && [ -d "${entry}" ] && [ ! -L "${entry}" ]; then
            debasher::_prune_subdivided_dir "${only_report}" "${what}" "${relpath}" "${entry}" "$5" "$6" || return 1
            continue
        fi

        if [ "${only_report}" -eq 1 ]; then
            echo "A run would remove ${entry}, which no option asks for, from ${what}" >&2
        else
            echo "Removing ${entry}, which no option asks for, from ${what}" >&2
            "${RM}" -rf -- "${entry}" || { echo "Error: cannot remove ${entry}" >&2; return 1; }
        fi
    done < <("${FIND}" -H "${absdir}" -mindepth 1 -maxdepth 1 -print0)
}

########
# Prepares the shared subdirectories that the options of the run ask
# for (see debasher::define_opt_from_shared_dir): refuses an output
# option that holds a subdivided shared directory, checks that no process
# that the program no longer has is still running, creates every shared
# subdirectory, and removes from every subdivided shared directory each
# entry that is neither a shared subdirectory of the run, nor a path that
# an output option of the run names, nor a directory on the way to one of
# them. When $1 is 1, as in a validation, nothing is created or removed,
# and the entries that a run would remove are only named.
#
# Must be called once the options of every process are defined and the
# shared directories created.
debasher::_prepare_shared_subdirs()
{
    local only_report=$1

    [ ${#DEBASHER_PROGRAM_SHSUBDIRS[@]} -eq 0 ] && return 0

    # Collect the subdivided shared directories
    local -A subdivided
    local relpath
    for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
        local shdirname=${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}
        if [[ ! -v DEBASHER_PROGRAM_SHDIRS["${shdirname}"] ]]; then
            echo "Error: an option asks for the shared subdirectory ${relpath} of ${shdirname}, which no module declares as a shared directory" >&2
            return 1
        fi
        subdivided["${shdirname}"]=1
    done

    debasher::_check_no_output_opt_holds_subdivided_shdir subdivided || return 1

    if [ "${only_report}" -ne 1 ]; then
        debasher::_check_left_processes_not_running || return 1
    fi

    for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
        local shdirname=${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}
        local absdir=$(debasher::get_absolute_shdirname "${shdirname}")
        local subpath=${relpath#"${shdirname}/"}
        debasher::_check_subpath_has_no_link "${absdir}" "${subpath}" "the shared subdirectory ${relpath}" || return 1
        if [ "${only_report}" -ne 1 ]; then
            "${MKDIR}" -p "${absdir}/${subpath}" || { echo "Error: cannot create the shared subdirectory ${relpath}" >&2; return 1; }
        fi
    done

    local shdirname
    for shdirname in "${!subdivided[@]}"; do
        local absdir=$(debasher::get_absolute_shdirname "${shdirname}")
        [ -d "${absdir}" ] || continue

        # What the shared directory keeps: its shared subdirectories and
        # the paths that output options name, relative to it
        local -A kept=()
        local -A ways=()
        for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
            [ "${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}" = "${shdirname}" ] && kept["${relpath#"${shdirname}/"}"]=1
        done
        debasher::_add_output_named_paths "${absdir}" kept
        debasher::_add_ways_to_paths kept ways

        debasher::_prune_subdivided_dir "${only_report}" "the shared directory ${shdirname}" "" "${absdir}" kept ways || return 1
    done
}

########
# Public: Defines process option whose value is the absolute path of the
# process output directory, or of a task subdirectory below it.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
# $3... - (optional) "--subdir <subpath>": the option gets the absolute
#      path of the task subdirectory <subpath> instead, a directory below
#      the process output directory that the engine creates when the
#      process is prepared and that the task empties before it runs, as
#      the process output directory of a process with a single task is
#      emptied, so that the process function finds it there and empty
#      whatever the number of tasks of its process. The subpath follows
#      the rules of debasher::define_opt_from_shared_dir --subdir. Two
#      tasks may not ask for the same task subdirectory, and no task
#      subdirectory may be below another one of the same process. A
#      process output directory for which some task asks for a task
#      subdirectory belongs to its task subdirectories: when the process
#      is prepared, every entry that is neither a task subdirectory of the
#      run, nor a path that an output option of the run names, nor a
#      directory on the way to one of them is removed from it (see
#      debasher::_prepare_task_subdirs_for_process).
#
# Examples
#
#   debasher::define_opt_from_process_outdir "-outd" "optlist"
#   debasher::define_opt_from_process_outdir "-outd" "optlist" --subdir "${task_idx}"
#
# The function does not return any value
debasher::define_opt_from_process_outdir()
{
    local opt=$1
    local varname=$2
    local subpath
    debasher::_read_subdir_opt_flags "define_opt_from_process_outdir" subpath "${@:3}" || exit 1

    local processname task_idx
    debasher::_get_defining_task processname task_idx
    local process_outdir=$(debasher::_get_process_outdir "${processname}")

    if [ -z "${subpath}" ]; then
        debasher::define_opt "${opt}" "${process_outdir}" "${varname}"
        return
    fi

    # Record the task subdirectory under its task; the execution context
    # carries the record to every task, which empties its own
    local key="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}"
    local recorded=${DEBASHER_PROCESS_TASK_SUBDIRS["${key}"]:-}
    if [ -z "${recorded}" ]; then
        DEBASHER_PROCESS_TASK_SUBDIRS["${key}"]=${subpath}
    elif ! "${GREP}" -qxF -- "${subpath}" <<< "${recorded}"; then
        DEBASHER_PROCESS_TASK_SUBDIRS["${key}"]="${recorded}"$'\n'"${subpath}"
    fi

    debasher::define_opt "${opt}" "${process_outdir}/${subpath}" "${varname}"
}

########
# Public: Defines process option whose value is the absolute path of the
# process output directory, or of a task subdirectory below it.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
# $3... - (optional) "--subdir <subpath>" (see
#      debasher::define_opt_from_process_outdir).
#
# Examples
#
#   define_opt_from_process_outdir "-outd" "optlist"
#   define_opt_from_process_outdir "-outd" "optlist" --subdir "${task_idx}"
#
# The function does not return any value
define_opt_from_process_outdir() { debasher::define_opt_from_process_outdir "$@"; }

########
# Prints the task subdirectories that the tasks of the process $1 ask for,
# one subpath per line, each with the index of its task before it and a
# tab between them.
debasher::_list_task_subdirs_of_process()
{
    local processname=$1

    local prefix="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    local key
    for key in "${!DEBASHER_PROCESS_TASK_SUBDIRS[@]}"; do
        [[ "${key}" == "${prefix}"* ]] || continue
        local task_idx=${key#"${prefix}"}
        local subpath
        while IFS= read -r subpath; do
            printf '%s\t%s\n' "${task_idx}" "${subpath}"
        done <<< "${DEBASHER_PROCESS_TASK_SUBDIRS["${key}"]}"
    done
}

########
# Checks the task subdirectories of the run, once the options of every
# task are defined: two tasks may not ask for the same one, no task
# subdirectory may be below another one of the same process, since each
# one is emptied on its own, and no output option may hold the path of a
# subdivided process output directory, since it would name the whole
# directory as something that a task produces.
debasher::_check_task_subdirs()
{
    [ ${#DEBASHER_PROCESS_TASK_SUBDIRS[@]} -eq 0 ] && return 0

    # Collect the processes that ask for task subdirectories
    local -A processes
    local key
    for key in "${!DEBASHER_PROCESS_TASK_SUBDIRS[@]}"; do
        processes["${key%"${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"*}"]=1
    done

    local processname
    for processname in "${!processes[@]}"; do
        local -A owner=()
        local task_idx subpath
        while IFS=$'\t' read -r task_idx subpath; do
            if [[ -v owner["${subpath}"] ]] && [ "${owner["${subpath}"]}" != "${task_idx}" ]; then
                echo "Error: tasks ${owner["${subpath}"]} and ${task_idx} of process ${processname} ask for the same task subdirectory ${subpath}" >&2
                return 1
            fi
            owner["${subpath}"]=${task_idx}
        done < <(debasher::_list_task_subdirs_of_process "${processname}")

        for subpath in "${!owner[@]}"; do
            local parent=${subpath}
            while [[ "${parent}" == */* ]]; do
                parent=${parent%/*}
                if [[ -v owner["${parent}"] ]]; then
                    echo "Error: the task subdirectory ${subpath} of process ${processname} is below another one, ${parent}" >&2
                    return 1
                fi
            done
        done

        local outd=$(debasher::_get_process_outdir "${processname}")
        local value
        for value in "${outd}" "${outd}/"; do
            if [[ -v DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"] ]]; then
                echo "Error: an output option holds the output directory of process ${processname}, which has task subdirectories; a task writes only into its own task subdirectories (define_opt_from_process_outdir --subdir)" >&2
                return 1
            fi
        done
    done
}

########
# Prepares the task subdirectories of the process $2 in the output
# directory $1, when the process is prepared: unless the process has a
# _reset_outfiles method or belongs to a resident program, removes from
# its subdivided process output directory every entry that is neither a
# task subdirectory of the run, nor a path that an output option of the
# run names, nor a directory on the way to one of them; then creates the
# task subdirectories that do not exist, refusing one whose subpath goes
# through a symbolic link.
debasher::_prepare_task_subdirs_for_process()
{
    local dirname=$1
    local processname=$2

    local -A kept=()
    local task_idx subpath
    while IFS=$'\t' read -r task_idx subpath; do
        kept["${subpath}"]=1
    done < <(debasher::_list_task_subdirs_of_process "${processname}")
    [ ${#kept[@]} -eq 0 ] && return 0

    local outd=$(debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}")
    local -a subpaths=("${!kept[@]}")

    # A symbolic link is refused before anything is removed, since removal
    # would take the link for an entry to remove
    for subpath in "${subpaths[@]}"; do
        debasher::_check_subpath_has_no_link "${outd}" "${subpath}" "the task subdirectory ${subpath} of process ${processname}" || return 1
    done

    local reset_funct=$(debasher::_get_reset_funcname "${processname}")
    if [ "${reset_funct}" = "${DEBASHER_FUNCT_NOT_FOUND}" ] && [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ] && [ -d "${outd}" ]; then
        local -A ways=()
        debasher::_add_output_named_paths "${outd}" kept
        debasher::_add_ways_to_paths kept ways
        debasher::_prune_subdivided_dir 0 "the output directory of process ${processname}" "" "${outd}" kept ways || return 1
    fi

    for subpath in "${subpaths[@]}"; do
        "${MKDIR}" -p "${outd}/${subpath}" || { echo "Error: cannot create the task subdirectory ${subpath} of process ${processname}" >&2; return 1; }
    done
}

########
# Empties, before the task $3 of the process $2 runs, the task
# subdirectories that it asks for, in the output directory $1: removes
# each of them with everything in it and creates it again.
debasher::_reset_task_subdirs()
{
    local dirname=$1
    local processname=$2
    local task_idx=$3

    local key="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}"
    [[ -v DEBASHER_PROCESS_TASK_SUBDIRS["${key}"] ]] || return 0

    local outd=$(debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}")
    local subpath
    while IFS= read -r subpath; do
        debasher::_check_subpath_has_no_link "${outd}" "${subpath}" "the task subdirectory ${subpath} of process ${processname}" || return 1
        "${RM}" -rf -- "${outd}/${subpath}" || { echo "Error: cannot empty the task subdirectory ${subpath} of process ${processname}" >&2; return 1; }
        "${MKDIR}" -p "${outd}/${subpath}" || { echo "Error: cannot create the task subdirectory ${subpath} of process ${processname}" >&2; return 1; }
    done <<< "${DEBASHER_PROCESS_TASK_SUBDIRS["${key}"]}"
}

########
debasher::_get_absolute_fifodir()
{
    echo "${DEBASHER_PROGRAM_OUTDIR}/${DEBASHER_FIFOS_DIRNAME}"
}

########
debasher::_get_absolute_fifoname()
{
    local owner_process=$1
    local fifoname=$2
    local augm_fifoname="${owner_process}/${fifoname}"
    local fifodir=$(debasher::_get_absolute_fifodir)

    echo "${fifodir}/${augm_fifoname}"
}

########
debasher::_get_augm_fifoname_from_absname()
{
    local absname=$1

    # basename: strip everything up to and including the last '/'
    local fifoname="${absname##*/}"

    # dirname: strip the last '/' and everything after it
    local dirpart="${absname%/*}"

    # basename of dirpart: the owner process directory name
    local owner_process="${dirpart##*/}"

    echo "${owner_process}/${fifoname}"
}

########
debasher::_get_absolute_condadir()
{
    echo "${DEBASHER_CONDA_DIR:-${DEBASHER_PROGRAM_OUTDIR}/${DEBASHER_CONDA_DIRNAME}}"
}

########
debasher::_clear_curr_opt_list_array()
{
    unset DEBASHER_CURRENT_PROCESS_OPT_LIST
    declare -ga DEBASHER_CURRENT_PROCESS_OPT_LIST
}

########
debasher::_get_opt_list_name()
{
    local processname=$1
    local task_idx=$2

    # A namespaced process name (e.g. "ns.name") is not a valid Bash
    # identifier, so the namespace separator is replaced here (with a
    # marker unlikely to appear in an ordinary process name) to build
    # a safe variable name.
    local safe_processname="${processname//./${DEBASHER_PROCESSNAME_NS_SEP_MANGLED}}"

    echo "DEBASHER_OPT_LIST_${safe_processname}_${task_idx}"
}

########
# Splits a raw option value that may encode several pending candidate
# values (see debasher::_merge_opt_value) into DEBASHER_DESERIALIZED_ARGS.
debasher::_split_opt_multival()
{
    local raw=$1

    if [[ "${raw}" == *"${DEBASHER_OPT_MULTIVAL_SEP}"* ]]; then
        debasher::_deserialize_args_given_sep "${raw}" "${DEBASHER_OPT_MULTIVAL_SEP}"
    else
        unset DEBASHER_DESERIALIZED_ARGS
        declare -ga DEBASHER_DESERIALIZED_ARGS
        DEBASHER_DESERIALIZED_ARGS=("${raw}")
    fi
}

########
# Records a raw option value for an option, keeping every distinct
# value seen so far instead of silently overwriting a previous one.
# Resolution/comparison of the resulting candidates happens later, in
# debasher::_load_curr_opt_list_loop, once process-output descriptors
# have been resolved to actual values.
#
# $1 - Name of the associative array storing the option list.
# $2 - Option name.
# $3 - Raw value to record (a literal, possibly empty,
#      DEBASHER_VOID_VALUE for a flag, or a process-output descriptor).
debasher::_merge_opt_value()
{
    local -n ref=$1
    local opt=$2
    local value=$3

    if [[ ! -v ref[${opt}] ]]; then
        ref["${opt}"]="${value}"
        return 0
    fi

    debasher::_split_opt_multival "${ref[${opt}]}"

    local candidate
    for candidate in "${DEBASHER_DESERIALIZED_ARGS[@]}"; do
        [ "${candidate}" = "${value}" ] && return 0
    done

    ref["${opt}"]="${ref[${opt}]}${DEBASHER_OPT_MULTIVAL_SEP}${value}"
}

########
# Public: Saves option list for a given process.
#
# $1 - Name of variable storing the option list.
#
# Examples
#
#   debasher::save_opt_list optlist
#
# The function does not return any value
debasher::save_opt_list()
{
    debasher::_generate_opt_list()
    {
        local processname=$1
        local task_idx=$2
        local opts=$3

        # Reference to the (dynamically named) associative array storing
        # the option list.
        local opt_list_name
        opt_list_name=$(debasher::_get_opt_list_name "${processname}" "${task_idx}")
        declare -gA "${opt_list_name}"

        debasher::_deserialize_args "${opts}"

        # Copy the deserialized args into the positional parameters so we
        # can use shift instead of a manually managed index counter
        set -- "${DEBASHER_DESERIALIZED_ARGS[@]}"

        while [ $# -gt 0 ]; do
            local token="$1"

            if ! debasher::_str_is_option "${token}"; then
                echo "Warning: unexpected value (${token}), skipping..." >&2
                shift
                continue
            fi

            local opt="${token}"
            shift

            # An option followed by nothing, or by another option, is a
            # flag, recorded as DEBASHER_VOID_VALUE so that it is told
            # apart from an option given an empty value; the next option
            # is not shifted, so it's picked up next iteration
            if [ $# -eq 0 ] || debasher::_str_is_option "$1"; then
                debasher::_merge_opt_value "${opt_list_name}" "${opt}" "${DEBASHER_VOID_VALUE}"
                continue
            fi

            debasher::_merge_opt_value "${opt_list_name}" "${opt}" "$1"
            shift
        done
    }

    debasher::_get_output_opts_info()
    {
        local processname=$1
        local task_idx=$2
        shift 2

        while [ $# -gt 0 ]; do
            local opt="$1"

            if ! debasher::_str_is_option "${opt}"; then
                echo "Warning: unexpected value (${opt}), skipping..." >&2
                shift
                continue
            fi

            shift

            # No token left after this option: nothing more to process
            [ $# -eq 0 ] && continue

            # If the next token is itself an option, this option has no value;
            # don't shift, so it's picked up as a new option next iteration
            debasher::_str_is_option "$1" && continue

            local value="$1"
            shift

            if debasher::_is_absolute_path "${value}" && debasher::_str_is_output_option "${opt}"; then
                local process_info="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}"
                if [[ -v DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"] ]]; then
                    DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"]="${DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"]}${DEBASHER_ASSOC_ARRAY_PROC_SEP}${process_info}"
                else
                    DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"]=${process_info}
                fi
            fi
        done
    }

    debasher::_get_output_opts_info_given_opts()
    {
        local processname=$1
        local task_idx=$2
        local opts=$3

        debasher::_deserialize_args "${opts}"
        debasher::_get_output_opts_info "${processname}" "${task_idx}" "${DEBASHER_DESERIALIZED_ARGS[@]}"
    }

    debasher::_save_opt_list_loop()
    {
        # Initialize variables
        local processname=$1
        local opts=$2

        # Obtain task index and update list length for process
        local task_idx
        if [ -z "${DEBASHER_PROCESS_OPT_LIST_LEN[${processname}]}" ]; then
            task_idx=0
            DEBASHER_PROCESS_OPT_LIST_LEN[${processname}]=1
        else
            task_idx=${DEBASHER_PROCESS_OPT_LIST_LEN[${processname}]}
            ((DEBASHER_PROCESS_OPT_LIST_LEN[${processname}]++))
        fi

        # Generate option list for process
        debasher::_generate_opt_list "${processname}" "${task_idx}" "${opts}"

        # Update variables storing output option information
        debasher::_get_output_opts_info_given_opts "${processname}" "${task_idx}" "${opts}"
    }

    debasher::_save_opt_list_generator()
    {
        # Initialize variables
        local opts=$1

        # Put options in DEBASHER_DESERIALIZED_ARGS (this is the only thing that
        # should be done by the generator here)
        debasher::_deserialize_args "${opts}"
    }

    # Initialize variables
    local -n opts=$1
    local save_opt_list_proc

    # Try to extract process name from generate_opts function
    debasher::_get_processname_from_caller_nameref "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}" save_opt_list_proc
    if [ -n "${save_opt_list_proc}" ]; then
        debasher::_save_opt_list_generator "${opts}"
        return 0
    fi

    # Try to extract process name from define_opts function
    debasher::_get_processname_from_caller_nameref "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}" save_opt_list_proc
    if [ -n "${save_opt_list_proc}" ]; then
        debasher::_save_opt_list_loop "${save_opt_list_proc}" "${opts}"
        return 0
    fi

    # If no process name was found, abort execution
    echo "save_opts: critical error, process name could not be determined!" >&2
    exit 1
}

########
# Public: Saves option list for a given process.
#
# $1 - Name of variable storing the option list.
#
# Examples
#
#   save_opt_list optlist
#
# The function does not return any value
save_opt_list() { debasher::save_opt_list "$@"; }

########
debasher::_load_curr_opt_list_loop()
{
    # WARNING: The debasher::_resolve_proc_output_desc function should be
    # called in a subshell, otherwise it may clash with the caller due
    # to its use of the DESERIALIZE_ARGS variable
    debasher::_resolve_proc_output_desc()
    {
        local cmdline=$1
        local value=$2

        # Extract information of connected process
        local connected_proc_info="${value#$DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        debasher::_deserialize_args_given_sep "${connected_proc_info}" "${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
        local connected_proc=${DEBASHER_DESERIALIZED_ARGS[0]}
        local connected_proc_task_idx=${DEBASHER_DESERIALIZED_ARGS[1]}
        local connected_proc_opt=${DEBASHER_DESERIALIZED_ARGS[2]}

        # If connected process uses a generator, the treatment should be
        # different
        if debasher::_uses_option_generator "${connected_proc}"; then
            # Obtain name of options generator
            local generate_opts_funcname=$(debasher::_get_generate_opts_funcname ${connected_proc})

            # Call options generator (output stored into DEBASHER_DESERIALIZED_ARGS)
            local connected_proc_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${connected_proc}"]}
            local connected_proc_outdir=$(debasher::_get_process_outdir "${connected_proc}")
            debasher::_call_generate_opts "${generate_opts_funcname}" "${cmdline}" "${connected_proc_spec}" "${connected_proc}" "${connected_proc_outdir}" "${connected_proc_task_idx}" || return 1

            # Get option value from function arguments
            value=$(debasher::_get_opt_value_from_func_args "${connected_proc_opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}")

            # Obtain value from list
            echo ${value}
        else
            # Obtain reference to option list of connected process
            local connected_proc_opt_list_name=$(debasher::_get_opt_list_name ${connected_proc} ${connected_proc_task_idx})
            declare -n connected_proc_opt_list=${connected_proc_opt_list_name}

            # Obtain value from list
            value=${connected_proc_opt_list[$connected_proc_opt]}
            echo ${value}
        fi
    }

    debasher::extract_processname_from_proc_output_desc()
    {
        local proc_output_desc=$1

        local connected_proc_info="${proc_output_desc#$DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        echo "${connected_proc_info}" | awk -F "${DEBASHER_ASSOC_ARRAY_ELEM_SEP}" '{print $1}'
    }

    debasher::_resolve_opt_candidate()
    {
        local cmdline=$1
        local processname=$2
        local opt=$3
        local candidate=$4

        if debasher::_str_is_proc_out_opt_descriptor "${candidate}"; then
            local resolved
            resolved=$(debasher::_resolve_proc_output_desc "${cmdline}" "${candidate}")
            if [ -z "${resolved}" ]; then
                local conn_proc=$(debasher::extract_processname_from_proc_output_desc "${candidate}")
                echo "Error: value of option ${opt} for process ${processname} could not be determined. Check if connected process ${conn_proc} does exist" >&2
                return 1
            fi
            echo "${resolved}"
        else
            echo "${candidate}"
        fi
    }

    local cmdline=$1
    local processname=$2

    # Clear array
    debasher::_clear_curr_opt_list_array

    # Iterate over process options
    local task_idx
    for (( task_idx=0; task_idx<${DEBASHER_PROCESS_OPT_LIST_LEN[${processname}]}; task_idx++ )); do
        # Initialize variables
        local opt_list_name=$(debasher::_get_opt_list_name ${processname} ${task_idx})
        declare -n opt_list=${opt_list_name}
        local _load_curr_opt_list_loop_optlist=""

        # Process options for task
        local opt
        for opt in "${!opt_list[@]}"; do
            debasher::_split_opt_multival "${opt_list[$opt]}"
            local -a opt_candidates=("${DEBASHER_DESERIALIZED_ARGS[@]}")

            local value
            value=$(debasher::_resolve_opt_candidate "${cmdline}" "${processname}" "${opt}" "${opt_candidates[0]}") || exit 1

            # If the option was given multiple times, every occurrence must
            # resolve to the same value; otherwise report the conflict
            local i
            for (( i=1; i<${#opt_candidates[@]}; i++ )); do
                local other_value
                other_value=$(debasher::_resolve_opt_candidate "${cmdline}" "${processname}" "${opt}" "${opt_candidates[$i]}") || exit 1
                if [ "${other_value}" != "${value}" ]; then
                    echo "Error: option ${opt} for process ${processname} was given multiple, conflicting values (${value} vs ${other_value})" >&2
                    exit 1
                fi
            done

            # Define option
            if [ "${value}" = "${DEBASHER_VOID_VALUE}" ]; then
                debasher::define_flag "${opt}" "_load_curr_opt_list_loop_optlist"
            else
                debasher::define_opt "${opt}" "${value}" "_load_curr_opt_list_loop_optlist"
            fi
        done
        DEBASHER_CURRENT_PROCESS_OPT_LIST+=("${_load_curr_opt_list_loop_optlist}")
    done
}

########
debasher::_show_curr_opt_list()
{
    local cmdline=$1
    local processname=$2

    # Show array length
    local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
    echo "${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${DEBASHER_ASSOC_ARRAY_KEY_LEN} -> ${num_tasks}"

    # Show options
    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        local opts=$(debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}")
        echo "${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx} -> ${opts}"
    done
}

########
debasher::_get_serial_process_opts()
{
    local cmdline=$1
    local processname=$2
    local max_num_proc_opts_to_display=$3

    # Store options in array
    local process_opts_array=()
    local ellipsis=""
    local num_tasks=$(debasher::_get_numtasks_for_process "${processname}")

    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        # Obtain process options
        local process_opts=$(debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}")

        # Obtain human-readable representation of process options
        hr_process_opts=$(debasher::_sep_serialized_to_qstr "${DEBASHER_ARG_SEP}" "$process_opts")
        process_opts_array+=("${hr_process_opts}")

        # Exit loop if maximum number of options is exceeded
        if [ "${#process_opts_array[@]}" -ge "${max_num_proc_opts_to_display}" ]; then
            ellipsis="..."
            break
        fi
    done

    # Serialize array
    local serial_process_opts=$(debasher::_serialize_string_array "process_opts_array" "${DEBASHER_ARRAY_TASK_SEP}")

    # Return result
    echo "${serial_process_opts} ${ellipsis}"
}

########
# Public: Writes value to value descriptor.
#
# $1 - Value to be written in the descriptor.
# $2 - Name of value descriptor.
#
# Examples
#
#   debasher::write_value_to_desc 42 ${value_desc_name}
#
# The function does not return any value
debasher::write_value_to_desc()
{
    local value=$1
    local value_descriptor=$2

    echo "${value}" > "${value_descriptor}"
}

########
# Public: Writes value to value descriptor.
#
# $1 - Value to be written in the descriptor.
# $2 - Name of value descriptor.
#
# Examples
#
#   write_value_to_desc 42 ${value_desc_name}
#
# The function does not return any value
write_value_to_desc() { debasher::write_value_to_desc "$@"; }

########
debasher::_read_value_from_desc()
{
    local value_descriptor=$1

    cat "${value_descriptor}"
}


########
# The directory with the options of every task of the processes: the
# .sched_opts directory of the output directory, or
# DEBASHER_SCHED_OPTS_DIR when set, as debasher_exec --check-proc-opts
# does so as to leave the output directory of a run untouched.
debasher::_get_sched_opts_dir()
{
    if [ -n "${DEBASHER_SCHED_OPTS_DIR}" ]; then
        echo "${DEBASHER_SCHED_OPTS_DIR}"
    else
        echo "${DEBASHER_PROGRAM_OUTDIR}/${DEBASHER_SCHED_OPTS_DIRNAME}"
    fi
}

########
debasher::_get_sched_opts_fname_for_process()
{
    local processname=$1

    local sched_opts_dir=$(debasher::_get_sched_opts_dir)
    echo "${sched_opts_dir}/${DEBASHER_SCHED_OPTS_FNAME_FOR_PROCESS_PREFIX}${processname}"
}
