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
# Convert a string serialized with a custom separator to a printf '%q'
# escaped string. The separator is passed as a parameter.
debasher::_sep_serialized_to_qstr()
{
    local sep=$1
    local sargs=$2
    local preproc_sargs
    preproc_sargs="${sargs//${sep}/$'\n'}"
    local array=()
    while IFS= read -r; do
        [[ -n "${REPLY}" ]] && array+=("${REPLY}")
    done <<< "${preproc_sargs}"
    printf '%q ' "${array[@]}"
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
        if [ "${1:0:1}" = "-" ] || [ "${1:0:2}" = "--" ]; then
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
    local value=`debasher::_get_opt_value_from_func_args "$@"`

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
        _OPT_VALUE_=`debasher::_read_memoized_opt_value $opt` || return 1
    else
        # Process not memoized line
        debasher::_memoize_opts "$cmdline"

        # Store processed line
        DEBASHER_LAST_PROC_LINE_MEMOPTS="$cmdline"

        # Return result
        _OPT_VALUE_=`debasher::_read_memoized_opt_value $opt` || return 1
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
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"`
    if [ -z "${proc_name}" ]; then
        proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}"`
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
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
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"`
    if [ -z "${proc_name}" ]; then
        proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}"`
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_CMDLINE[$proc_opt]=0
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
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"`
    if [ -z "${proc_name}" ]; then
        proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}"`
    fi

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${DEBASHER_GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    local proc_opt=${proc_name}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${opt}
    DEBASHER_PROGRAM_OPT_IS_CMDLINE[$proc_opt]=0
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
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}"`

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
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}"`

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
            if [ "${only_cmdline_opts}" -eq 1 ] && [ ${DEBASHER_PROGRAM_OPT_IS_CMDLINE[${key}]} -eq 0 ]; then
                continue
            fi

            # Check if option belongs to current category
            if [ ${DEBASHER_PROGRAM_OPT_CATEG[${key}]} = $categ ]; then
                # Print option
                if [ -z ${DEBASHER_PROGRAM_OPT_TYPE[$opt]} ]; then
                    echo "${opt} ${DEBASHER_PROGRAM_OPT_DESC[$key]} [${processname}]"
                else
                    echo "${opt} ${DEBASHER_PROGRAM_OPT_TYPE[$key]} ${DEBASHER_PROGRAM_OPT_DESC[$opt]} [${processname}]"
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

    # Get augmented fifo name
    local augm_fifoname="${processname}/${fifoname}"

    # Store name of FIFO in associative arrays
    DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]=${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${task_idx}

    # Register FIFO user as external initially (this registration will
    # be corrected later when analyzing the FIFOs used by each process)
    DEBASHER_FIFO_USERS["${augm_fifoname}"]=${DEBASHER_EXTERNAL_FIFO_USER}
}

########
# Public: Defines fifo option for process.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option.
#
# Examples
#
#   debasher::define_fifo_opt "-o" "${fifoname}" "optlist"
#
# The function does not return any value
debasher::define_fifo_opt()
{
    local opt=$1
    local fifoname=$2
    local varname=$3

    # Check that the call is valid
    local proc_generate=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    if [ -n "${proc_generate}" ]; then
        echo "define_fifo_opt: Error, this function cannot be called from an option generator" >&2
        exit 1
    fi

    # Get process name
    local processname=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"`

    # Get task index
    local task_idx=${#DEBASHER_CURRENT_PROCESS_OPT_LIST[@]}

    # Define FIFO
    debasher::_define_fifo_task_idx "${fifoname}" "${processname}" "${task_idx}"

    # Get absolute name of FIFO
    local abs_fifoname=$(debasher::_get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for FIFO
    debasher::define_opt "${opt}" "${abs_fifoname}" "${varname}" || return 1
}

########
# Public: Defines fifo option for process.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option.
#
# Examples
#
#   define_fifo_opt "-o" "${fifoname}" "optlist"
#
# The function does not return any value
define_fifo_opt() { debasher::define_fifo_opt "$@"; }

########
# Public: Defines a fifo option generator.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option.
# Additionally, the function should only be called from an option generator.
#
# Examples
#
#   debasher::define_fifo_opt_generator "-o" "${fifoname}" "optlist"
#
# The function does not return any value
debasher::define_fifo_opt_generator()
{
    local opt=$1
    local fifoname=$2
    local task_idx=$3
    local varname=$4

    # Check that the call is valid
    local proc_define=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    if [ -n "${proc_define}" ]; then
        echo "define_fifo_opt_generator: Error, this function should only be called from an option generator" >&2
        exit 1
    fi

    # Get process name
    local processname=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"`

    # Define FIFO
    debasher::_define_fifo_task_idx "${fifoname}" "${processname}" "${task_idx}"

    # Get absolute name of FIFO
    local abs_fifoname=$(debasher::_get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for FIFO
    debasher::define_opt "-outf" "${abs_fifoname}" "${varname}" || return 1
}

########
# Public: Defines a fifo option generator.
#
# $1 - Option name.
# $2 - Name of fifo.
# $3 - Name of variable that will store the information about the option to be added.
#
# This function should only be defined in one of the processes connected
# by the FIFO. More specifically, in the process defining an output option.
# Additionally, the function should only be called from an option generator.
#
# Examples
#
#   define_fifo_opt_generator "-o" "${fifoname}" "optlist"
#
# The function does not return any value
define_fifo_opt_generator() { debasher::define_fifo_opt_generator "$@"; }

########
debasher::define_shared_dir()
{
    local shared_dir=$1

    # Check whether the shared directory is being defined by a module or
    # by a process

    # Try to get process name from define_opts or generate_opts method
    local processname=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    if [ -z "${processname}" ]; then
        processname=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    fi

    # If processname variable is void, then the shared directory was
    # defined at module-level
    if [ -z "${processname}" ]; then
        DEBASHER_PROGRAM_SHDIRS["${shared_dir}"]=${DEBASHER_SHDIR_MODULE_OWNER}
    else
        DEBASHER_PROGRAM_SHDIRS["${shared_dir}"]=${processname}
    fi
}

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
    value=`debasher::_get_absolute_path "$value"`

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
        value=`debasher::_get_absolute_path "$value"`

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
        if [[ ! "${out_opt}" != "-out"* && ! "${out_opt}" != "--out"* ]]; then
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
debasher::_optname_is_correct()
{
    local funcname=$1
    local opt=$2

    if [ "${opt}" = "" ]; then
        debasher::errmsg "$funcname: option name could not be the empty string"
        return 1
    else
        if [[ ! "${opt}" =~ ^(-|--) ]]; then
            debasher::errmsg "$funcname: option name should start with '-' or '--'"
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
debasher::_get_value_descriptor_name()
{
    local process_name=$1
    local opt=$2

    # Obtain output directory for process
    local process_outdir=$(debasher::_get_process_outdir "${process_name}")

    # Obtain value descriptor name
    local val_desc="${process_outdir}/${DEBASHER_VALUE_DESCRIPTOR_NAME_PREFIX}${opt}"

    echo "${val_desc}"
}

########
# Public: Defines process option storing a value descriptor.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
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

    # Obtain caller process name
    local proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    if [ -z "${proc_name}" ]; then
        proc_name=`debasher::_get_processname_from_caller "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    fi

    # Get name of value descriptor
    local val_desc=$(debasher::_get_value_descriptor_name "${proc_name}" "${opt}")

    # Define option
    debasher::define_opt "${opt}" "${val_desc}" "${varname}"
}

########
# Public: Defines process option storing a value descriptor.
#
# $1 - Option name.
# $2 - Name of variable that will store the information about the option to be added.
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
        local absdir=`debasher::get_absolute_shdirname "$dirname"`
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
        local shrdirs_funcname=`debasher::_get_shrdirs_funcname ${absmodname}`
        if debasher::_func_exists "${shrdirs_funcname}"; then
            ${shrdirs_funcname} || exit 1
        fi
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
            local absdir=`debasher::get_absolute_shdirname "$dirname"`
            if [ ! -d "${absdir}" ]; then
                "${MKDIR}" -p "${absdir}" || exit 1
            fi
        fi
    done
}

########
debasher::_create_shdirs_owned_by_process()
{
    local processname=$1
    # Create shared directories for process
    local dirname
    for dirname in "${!DEBASHER_PROGRAM_SHDIRS[@]}"; do
        local owner=${DEBASHER_PROGRAM_SHDIRS["${dirname}"]}
        if [ "${processname}" = "${owner}" ]; then
            local absdir=`debasher::get_absolute_shdirname "$dirname"`
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
        echo "${augm_fifoname}" ${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]} ${DEBASHER_FIFO_USERS["${augm_fifoname}"]}
    done
}

########
debasher::_prepare_fifos_owned_by_process()
{
    local processname=$1

    # Obtain name of directory for FIFOS
    local fifodir=`debasher::_get_absolute_fifodir`

    # Create FIFOS
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        local proc_plus_idx=${DEBASHER_PROGRAM_FIFOS["${augm_fifoname}"]}
        local proc="${proc_plus_idx%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
        if [ "${proc}" = "${processname}" ]; then
            local dirname=`"${DIRNAME}" "${augm_fifoname}"`
            if [ ! -d "${fifodir}/${dirname}" ]; then
                "${MKDIR}" -p "${fifodir}/${dirname}"
            fi
            if [ -p "${fifodir}/${augm_fifoname}" ]; then
                "${RM}" -f "${fifodir}/${augm_fifoname}" || exit 1
            fi
            "${MKFIFO}" "${fifodir}/${augm_fifoname}" || exit 1
        fi
    done
}

########
debasher::get_absolute_shdirname()
{
    local shdirname=$1

    # Output absolute shared directory name
    echo "${DEBASHER_PROGRAM_OUTDIR}/${shdirname}"
}

get_absolute_shdirname() { debasher::get_absolute_shdirname "$@"; }

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
    local fifodir=`debasher::_get_absolute_fifodir`

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
    echo "${DEBASHER_PROGRAM_OUTDIR}/${DEBASHER_CONDA_DIRNAME}"
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

    echo "DEBASHER_OPT_LIST_${processname}_${task_idx}"
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
        local -n opt_list=${opt_list_name}

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

            # No token left after this option: nothing more to process
            [ $# -eq 0 ] && continue

            # If the next token is itself an option, this option has no
            # value; record it as empty and don't shift, so it's picked
            # up as a new option next iteration
            if debasher::_str_is_option "$1"; then
                opt_list["${opt}"]=""
                continue
            fi

            opt_list["${opt}"]="$1"
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
            local generate_opts_funcname=`debasher::_get_generate_opts_funcname ${connected_proc}`

            # Call options generator (output stored into DEBASHER_DESERIALIZED_ARGS)
            local connected_proc_spec=${DEBASHER_INITIAL_PROCESS_SPEC["${connected_proc}"]}
            local connected_proc_outdir=`debasher::_get_process_outdir "${connected_proc}"`
            ${generate_opts_funcname} "${cmdline}" "${connected_proc_spec}" "${connected_proc}" "${connected_proc_outdir}" "${task_idx}" || return 1

            # Get option value from function arguments
            value=`debasher::_get_opt_value_from_func_args "${connected_proc_opt}" "${DEBASHER_DESERIALIZED_ARGS[@]}"`

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
            local value

            # Resolve process output descriptor if necessary
            if debasher::_str_is_proc_out_opt_descriptor "${opt_list[$opt]}"; then
                local proc_out_desc
                proc_out_desc=${opt_list[$opt]}
                value=`debasher::_resolve_proc_output_desc "${cmdline}" "${proc_out_desc}"`
                if [ -z "${value}" ]; then
                    local conn_proc=`debasher::extract_processname_from_proc_output_desc "${proc_out_desc}"`
                    echo "Error: value of option ${opt} for process ${processname} could not be determined. Check if connected process ${conn_proc} does exist" >&2
                    exit 1
                fi
            else
                value=${opt_list[$opt]}
            fi

            # Define option
            if [ -z "${value}" ]; then
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
    local num_tasks=`debasher::_get_numtasks_for_process "${processname}"`
    echo "${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${DEBASHER_ASSOC_ARRAY_KEY_LEN} -> ${num_tasks}"

    # Show options
    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        local opts=`debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
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
    local num_tasks=`debasher::_get_numtasks_for_process "${processname}"`

    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        # Obtain process options
        local process_opts=`debasher::_get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`

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
    local serial_process_opts=`debasher::_serialize_string_array "process_opts_array" "${DEBASHER_ARRAY_TASK_SEP}"`

    # Return result
    echo "${serial_process_opts} ${ellipsis}"
}

########
debasher::_show_out_values_for_processes()
{
    for outval in "${!DEBASHER_OUT_VALUE_TO_PROCESSES[@]}"; do
        echo "${outval} -> ${DEBASHER_OUT_VALUE_TO_PROCESSES[${outval}]}"
    done
}

########
debasher::_get_proc_out_opt_from_desc()
{
    local proc_out_opt_descriptor=$1

    # Obtain process plus option info
    local process_opt_info="${proc_out_opt_descriptor#$DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"

    echo ${PROCESS_TO_OUT_VALUE["${process_opt_info}"]}
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

read_value_to_desc() { debasher::read_value_to_desc "$@"; }

########
debasher::get_sched_opts_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_SCHED_OPTS_DIRNAME}"
}

########
debasher::_get_sched_opts_dir()
{
    debasher::get_sched_opts_dir_given_basedir "${DEBASHER_PROGRAM_OUTDIR}"
}

########
debasher::_get_sched_opts_fname_for_process()
{
    local dirname=$1
    local processname=$2

    local sched_opts_dir=`debasher::get_sched_opts_dir_given_basedir "${dirname}"`
    echo "${sched_opts_dir}/${DEBASHER_SCHED_OPTS_FNAME_FOR_PROCESS_PREFIX}${processname}"
}
