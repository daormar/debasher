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

#######################################################
# ARGUMENT SERIALIZATION AND OPTION READING FUNCTIONS #
#######################################################

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
