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

###############################
# OPTION DEFINITION FUNCTIONS #
###############################

########
esc_dq()
{
    local escaped_str=${1//\"/\\\"};
    echo "${escaped_str}"
}

########
serialize_args()
{
    local serial_args=""
    for arg in "$@"; do
        if [ -z "$serial_args" ]; then
            serial_args=${arg}
        else
            serial_args=${serial_args}${ARG_SEP}${arg}
        fi
    done
    echo "${serial_args}"
}

########
serialize_args_nameref()
{
    local -n var_ref=$1;
    shift
    local serial_args=""
    for arg in "$@"; do
        if [ -z "$serial_args" ]; then
            serial_args=${arg}
        else
            serial_args=${serial_args}${ARG_SEP}${arg}
        fi
    done
    var_ref="${serial_args}"
}

########
deserialize_args_given_sep()
{
    local serial_args=$1
    local sep=$2

    if [ -z "${serial_args}" ]; then
        unset DESERIALIZED_ARGS
        declare -ga DESERIALIZED_ARGS
    else
        local new_sep=$'\n'
        local preproc_sargs="${serial_args//${sep}/$new_sep}"
        unset DESERIALIZED_ARGS
        declare -ga DESERIALIZED_ARGS
        while IFS=${new_sep} read -r; do DESERIALIZED_ARGS+=( "${REPLY}" ); done <<< "${preproc_sargs}"
    fi
}

########
deserialize_args()
{
    local serial_args=$1

    deserialize_args_given_sep "${serial_args}" "${ARG_SEP}"
}

########
sargs_to_sargsquotes()
{
    local sargs=$1

    # Convert string to array
    local preproc_sargs
    preproc_sargs="${sargs//${ARG_SEP}/$'\n'}"
    local array=()
    while IFS= read -r; do array+=( "${REPLY}" ); done <<< "${preproc_sargs}"

    # Process array
    local i=0
    local sargsquotes
    while [ $i -lt ${#array[@]} ]; do
        elem=${array[$i]}
        elem=$("${SED}" "s/'/'\\\''/g" <<<"$elem")
        if [ -z "${sargsquotes}" ]; then
            sargsquotes=${elem}
        else
            sargsquotes="${sargsquotes}${ARG_SEP_QUOTES}${elem}"
        fi
        i=$((i+1))
    done
    sargsquotes="'${sargsquotes}'"

    echo "${sargsquotes}"
}

########
sargsquotes_to_sargs()
{
    local sargsquotes=$1

    # Remove first and last quotes
    local preproc_sargsquotes
    preproc_sargsquotes="${sargsquotes%\'*}"
    preproc_sargsquotes="${preproc_sargsquotes#\'*}"

    # Convert string to array
    local new_sep=$'\n'
    preproc_sargsquotes="${preproc_sargsquotes//${ARG_SEP_QUOTES}/$new_sep}"
    local array=()
    while IFS=$new_sep read -r; do array+=( "${REPLY}" ); done <<< "${preproc_sargsquotes}"

    # Process array
    local i=0
    local sargs
    while [ $i -lt ${#array[@]} ]; do
        elem=${array[$i]}
        elem="${elem//\\\'/\'}"
        if [ -z "${sargs}" ]; then
            sargs=${elem}
        else
            sargs="${sargs}${ARG_SEP}${elem}"
        fi
        i=$((i+1))
    done

    echo "${sargs}"
}

########
serialize_cmdexec()
{
    local pipe_exec_cmd=$1

    # Create temporary file
    local tmpfile=`"${MKTEMP}"`

    # Obtain command line
    local cmdline
    cmdline=`eval serialize_args "${pipe_exec_cmd}"`

    echo ${cmdline}
}

########
normalize_cmd()
{
    local args=$1
    local sargs=`eval serialize_args "${args}"`
    local sargsquotes=`sargs_to_sargsquotes "${sargs}"`
    echo "${sargsquotes}"
}

########
replace_blank_with_word()
{
    local str=$1
    local word=$2
    echo ${str// /$word}
}

########
replace_word_with_blank()
{
    local str=$1
    local word=$2
    echo ${str//$word/ }
}

########
memoize_opts()
{
    local cmdline=$1

    # Convert string to array (result is placed into the
    # DESERIALIZED_ARGS variable)
    deserialize_args "${cmdline}"

    # Scan DESERIALIZED_ARGS
    local i=1
    while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
        if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
            local opt="${DESERIALIZED_ARGS[$i]}"
            i=$((i+1))
            # Obtain value if it exists
            local value=""
            # Check if next token is an option
            if [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; then
                if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
                    :
                else
                    value="${DESERIALIZED_ARGS[$i]}"
                    i=$((i+1))
                fi
            fi

            # Store option
            if [ -z "${value}" ]; then
                MEMOIZED_OPTS[$opt]=${VOID_VALUE}
            else
                MEMOIZED_OPTS[$opt]="$value"
            fi
        else
            echo "Warning: unexpected value (${DESERIALIZED_ARGS[$i]}), skipping..." >&2
            i=$((i+1))
        fi
    done
}

########
check_opt_given()
{
    local cmdline=$1
    local opt=$2

    # Convert string to array (result is placed into the
    # DESERIALIZED_ARGS variable)
    deserialize_args "${cmdline}"

    # Scan DESERIALIZED_ARGS
    i=0
    while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
        if [ ${DESERIALIZED_ARGS[$i]} = "${opt}" ]; then
            return 0
        fi
        i=$((i+1))
    done

    # Option not given
    return 1
}

########
check_memoized_opt()
{
    local opt=$1

    # Check if option was not given
    if [ -z "${MEMOIZED_OPTS[$opt]}" ]; then
        return 1
    else
        return 0
    fi
}

########
check_opt_given_memoiz()
{
    local cmdline=$1
    local opt=$2

    if [ "${LAST_PROC_LINE_MEMOPTS}" = "$cmdline" ]; then
        # Given line was previously processed, return memoized result
        check_memoized_opt $opt || return 1
    else
        # Process not memoized line
        memoize_opts "$cmdline"

        # Store processed line
        LAST_PROC_LINE_MEMOPTS="$cmdline"

        # Return result
        check_memoized_opt $opt || return 1
    fi
}

########
get_opt_value_from_func_args()
{
    local opt=$1

    # Process function arguments
    shift
    local i=1
    while [ $i -le $# ]; do
        # Check if option was found
        if [ "${!i}" = "${opt}" ]; then
            i=$((i+1))
            # Obtain value if it exists
            local value=""
            # Check if next token is an option
            if [ $i -le $# ]; then
                if [ "${!i:0:1}" = "-" ] || [ "${!i:0:2}" = "--" ]; then
                    :
                else
                    value="${!i}"
                    i=$((i+1))
                fi
            fi

            # Show value if it exists and return
            if [ -z "${value}" ]; then
                echo "${VOID_VALUE}"
                return 1
            else
                echo "${value}"
                return 0
            fi
        fi
        i=$((i+1))
    done

    # Option not given
    echo "${OPT_NOT_FOUND}"
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
#   local str=$(read_opt_value_from_func_args "-s" "$@")
#
# The function prints the value of the option if it was given, or the "OPT_NOT_FOUND" constant otherwise.
read_opt_value_from_func_args()
{
    local opt=$1

    # Get value for option
    local value=`get_opt_value_from_func_args "$@"`

    # If the value is a descriptor and opt is not an output option, then
    # we should read the descriptor
    if str_is_val_descriptor "${value}" && ! str_is_output_option "${opt}"; then
        read_value_from_desc "${value}" || return 1
    else
        echo "${value}"
    fi
}

########
read_opt_value_from_line()
{
    local cmdline=$1
    local opt=$2

    # Convert string to array (result is placed into the
    # DESERIALIZED_ARGS variable)
    deserialize_args "${cmdline}"

    # Get opt value
    get_opt_value_from_func_args "${opt}" "${DESERIALIZED_ARGS[@]}"
}

########
read_memoized_opt_value()
{
    local opt=$1

    # Check if option was not given or it had void value
    if [ -z "${MEMOIZED_OPTS[$opt]}" -o "${MEMOIZED_OPTS[$opt]}" = ${VOID_VALUE} ]; then
        echo ${OPT_NOT_FOUND}
        return 1
    else
        echo "${MEMOIZED_OPTS[$opt]}"
        return 0
    fi
}

########
read_opt_value_from_line_memoiz()
{
    local cmdline=$1
    local opt=$2

    if [ "${LAST_PROC_LINE_MEMOPTS}" = "$cmdline" ]; then
        # Given line was previously processed, return memoized result
        _OPT_VALUE_=`read_memoized_opt_value $opt` || return 1
    else
        # Process not memoized line
        memoize_opts "$cmdline"

        # Store processed line
        LAST_PROC_LINE_MEMOPTS="$cmdline"

        # Return result
        _OPT_VALUE_=`read_memoized_opt_value $opt` || return 1
    fi
}

########
update_opt_to_process_map()
{
    local processname=$1
    local opts=$2

    for opt in ${opts}; do
        if [ "${PROGRAM_OPT_PROCESS[${opt}]}" = "" ]; then
            PROGRAM_OPT_PROCESS[${opt}]=${processname}
        else
            PROGRAM_OPT_PROCESS[${opt}]="${PROGRAM_OPT_PROCESS[${opt}]} ${processname}"
        fi
    done
}

########
explain_cmdline_req_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    PROGRAM_OPT_TYPE[$opt]=$type
    PROGRAM_OPT_REQ[$opt]=1
    PROGRAM_OPT_DESC[$opt]=$desc
    PROGRAM_OPT_CATEG[$opt]=$categ
    PROGRAM_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
}

########
# Public: Explains command-line option.
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
explain_cmdline_opt()
{
    local opt=$1
    local type=$2
    local desc=$3
    local categ=$4

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    PROGRAM_OPT_TYPE[$opt]=$type
    PROGRAM_OPT_DESC[$opt]=$desc
    PROGRAM_OPT_CATEG[$opt]=$categ
    PROGRAM_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
}

########
explain_cmdline_opt_wo_value()
{
    local opt=$1
    local desc=$2
    local categ=$3

    # Assign default category if not given
    if [ "$categ" = "" ]; then
        categ=${GENERAL_OPT_CATEGORY}
    fi

    # Store option in associative arrays
    PROGRAM_OPT_TYPE[$opt]=""
    PROGRAM_OPT_DESC[$opt]=$desc
    PROGRAM_OPT_CATEG[$opt]=$categ
    PROGRAM_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
}

########
print_program_opts()
{
    local lineno=0

    # Iterate over option categories
    local categ
    for categ in ${!PROGRAM_CATEG_MAP[@]}; do
        if [ ${lineno} -gt 0 ]; then
            echo ""
        fi
        echo "CATEGORY: ${categ}"
        # Iterate over options
        local opt
        for opt in ${!PROGRAM_OPT_TYPE[@]}; do
            # Check if option belongs to current category
            if [ ${PROGRAM_OPT_CATEG[${opt}]} = $categ ]; then
                # Set value of required option flag
                if [ "${PROGRAM_OPT_REQ[${opt}]}" != "" ]; then
                    reqflag=" (required) "
                else
                    reqflag=" "
                fi

                # Print option
                if [ -z ${PROGRAM_OPT_TYPE[$opt]} ]; then
                    echo "${opt} ${PROGRAM_OPT_DESC[$opt]}${reqflag}[${PROGRAM_OPT_PROCESS[$opt]}]"
                else
                    echo "${opt} ${PROGRAM_OPT_TYPE[$opt]} ${PROGRAM_OPT_DESC[$opt]}${reqflag}[${PROGRAM_OPT_PROCESS[$opt]}]"
                fi
            fi
        done

        lineno=$((lineno + 1))
    done
}

########
define_fifo_task_idx()
{
    local fifoname=$1
    local processname=$2
    local task_idx=$3

    # Get augmented fifo name
    local augm_fifoname="${processname}/${fifoname}"

    # Store name of FIFO in associative arrays
    PROGRAM_FIFOS["${augm_fifoname}"]=${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}
}

########
define_fifo_opt()
{
    local opt=$1
    local fifoname=$2
    local varname=$3

    # Check that the call is valid
    local proc_generate=`get_processname_from_caller "${PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    if [ -n "${proc_generate}" ]; then
        echo "define_fifo_opt: Error, this function cannot be called from an option generator" >&2
        exit 1
    fi

    # Get process name
    local processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`

    # Get task index
    local task_idx=${#CURRENT_PROCESS_OPT_LIST[@]}

    # Define FIFO
    define_fifo_task_idx "${fifoname}" "${processname}" "${task_idx}"

    # Get absolute name of FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for FIFO
    define_opt "-outf" "${abs_fifoname}" "${varname}" || return 1
}

########
define_fifo_opt_generator()
{
    local opt=$1
    local fifoname=$2
    local task_idx=$3
    local varname=$4

    # Check that the call is valid
    local proc_define=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    if [ -n "${proc_define}" ]; then
        echo "define_fifo_opt_generator: Error, this function should only be called from an option generator" >&2
        exit 1
    fi

    # Get process name
    local processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_GENERATE_OPTS}"`

    # Define FIFO
    define_fifo_task_idx "${fifoname}" "${processname}" "${task_idx}"

    # Get absolute name of FIFO
    local abs_fifoname=$(get_absolute_fifoname "${process_name}" "${fifoname}")

    # Define option for FIFO
    define_opt "-outf" "${abs_fifoname}" "${varname}" || return 1
}

########
define_shared_dir()
{
    local shared_dir=$1

    # Check whether the shared directory is being defined by a module or
    # by a process

    # Try to get process name from define_opts or generate_opts method
    local processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    if [ -z "${processname}" ]; then
        processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    fi

    # If processname variable is void, then the shared directory was
    # defined at module-level
    if [ -z "${processname}" ]; then
        PROGRAM_SHDIRS["${shared_dir}"]=${SHDIR_MODULE_OWNER}
    else
        PROGRAM_SHDIRS["${shared_dir}"]=${processname}
    fi
}

########
get_cmdline_opt()
{
    local cmdline=$1
    local opt=$2

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value="${_OPT_VALUE_}"

    # Return option
    echo "${value}"
}

########
define_cmdline_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" "$opt" || { errmsg "$opt option not found" ; return 1; }
    local value="${_OPT_VALUE_}"

    # Add option
    define_opt $opt "$value" $varname
}

########
define_cmdline_opt_wo_value()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    check_opt_given "$cmdline" "$opt" || { errmsg "$opt option not found" ; return 1; }

    # Add option
    define_opt_wo_value "$opt" "$varname"
}

########
define_cmdline_nonmandatory_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value="${_OPT_VALUE_}"

    if [ "$value" = ${OPT_NOT_FOUND} ]; then
        value=${default_value}
    fi

    # Add option
    define_opt "$opt" "$value" "$varname"
}

########
define_cmdline_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value=${_OPT_VALUE_}

    if [ "$value" != ${OPT_NOT_FOUND} ]; then
        # Add option
        define_opt "$opt" "$value" "$varname"
    fi
}

########
define_cmdline_infile_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }
    local value="${_OPT_VALUE_}"

    if [ "$value" != ${NOFILE} ]; then
        # Check if file exists
        file_exists "$value" || { errmsg "file $value does not exist ($opt option)" ; return 1; }

        # Absolutize path
        value=`get_absolute_path "${value}"`
    fi

    # Add option
    define_opt "$opt" "$value" "$varname"
}

########
define_cmdline_infile_nonmand_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value="${_OPT_VALUE_}"

    if [ "$value" = ${OPT_NOT_FOUND} ]; then
        value=${default_value}
    fi

    if [ "$value" != ${NOFILE} ]; then
        # Check if file exists
        file_exists "$value" || { errmsg "file $value does not exist ($opt option)" ; return 1; }

        # Absolutize path
        value=`get_absolute_path "${value}"`
    fi

    # Add option
    define_opt $opt "$value" "$varname"
}

########
define_opt_from_proc_out()
{
    local opt=$1
    local proc=$2
    local out_opt=$3
    local varname=$4

    local task_idx=0
    define_opt_from_proc_task_out "${opt}" "${proc}" "${task_idx}" "${out_opt}" "${varname}"
}

########
define_opt_from_proc_task_out()
{
    local opt=$1
    local proc=$2
    local task_idx=$3
    local out_opt=$4
    local varname=$5

    # Check parameters
    if [[ "${opt}" == "-out"* || "${opt}" == "--out"* ]]; then
        errmsg "define_opt_from_proc_task_out: wrong input parameters, process option cannot start with ${opt} (it should not be an output option)"
        return 1
    else
        if [[ ! "${out_opt}" != "-out"* && ! "${out_opt}" != "--out"* ]]; then
            errmsg "define_opt_from_proc_task_out: wrong input parameters, connected process option should start with -out or --out"
            return 1
        fi
    fi

    # Generate process info
    local process_opt_info="${proc}${ASSOC_ARRAY_ELEM_SEP}${task_idx}${ASSOC_ARRAY_ELEM_SEP}${out_opt}"

    # Generate value
    local value=${PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}${process_opt_info}

    # Add option
    define_opt "$opt" "$value" "$varname"
}

########
optname_is_correct()
{
    local funcname=$1
    local opt=$2

    if [ "${opt}" = "" ]; then
        errmsg "$funcname: option name could not be the empty string"
        return 1
    else
        if [[ ! "${opt}" =~ ^(-|--) ]]; then
            errmsg "$funcname: option name should start with '-' or '--'"
            return 1
        fi
    fi

    return 0
}

########
optlist_varname_is_correct()
{
    local funcname=$1
    local varname=$2

    if [ -z "${varname}" ]; then
        errmsg "$funcname: name of option list variable should not be empty"
        return 1
    else
        if [[ "${varname}" == *"${OPTLIST_VARNAME_SUFFIX}" ]]; then
            return 0
        else
            errmsg "$funcname: name of option list variable should end with the suffix ${OPTLIST_VARNAME_SUFFIX}"
            return 1
        fi
    fi
}

########
define_opt_wo_value()
{
    local opt=$1
    local varname=$2
    local -n var_ref=$3

    # Check parameters
    optname_is_correct "${FUNCNAME}" "$opt" || return 1
    optlist_varname_is_correct "${FUNCNAME}" "$varname" || return 1

    if [ -z "${var_ref}" ]; then
        var_ref="${opt}"
    else
        var_ref="${var_ref}${ARG_SEP}${opt}"
    fi
}

########
# Public: Defines process option.
#
# TO-BE-DONE
#
# $1 - Option name
#
# Examples
#
#   TO-BE-DONE
#
# The function does not return any value
define_opt()
{
    local opt=$1
    local value=$2
    local varname=$3
    local -n var_ref=$3

    # Check parameters
    optname_is_correct "${FUNCNAME}" "$opt" || return 1
    optlist_varname_is_correct "${FUNCNAME}" "$varname" || return 1

    if [ -z "${var_ref}" ]; then
        var_ref="${opt}${ARG_SEP}${value}"
    else
        var_ref="${var_ref}${ARG_SEP}${opt}${ARG_SEP}${value}"
    fi
}

########
get_value_descriptor_name()
{
    local process_name=$1
    local opt=$2

    # Obtain output directory for process
    local process_outdir=$(get_process_outdir "${process_name}")

    # Obtain value descriptor name
    local val_desc="${process_outdir}/${VALUE_DESCRIPTOR_NAME_PREFIX}${opt}"

    echo "${val_desc}"
}

########
define_value_desc_opt()
{
    local opt=$1
    local varname=$2

    # Obtain caller process name
    local caller_proc_name=`get_processname_from_caller "${PROCESS_METHOD_NAME_GENERATE_OPTS}"`
    if [ -z "${caller_proc_name}" ]; then
        caller_proc_name=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`
    fi

    # Get name of value descriptor
    local val_desc=$(get_value_descriptor_name "${caller_proc_name}" "${opt}")

    # Define option
    define_opt "${opt}" "${val_desc}" "${varname}"
}

########
define_infile_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check if file exists
    file_exists "$value" || { errmsg "file $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path "${value}"`

    define_opt "${opt}" "${value}" "${varname}"
}

########
define_indir_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check if file exists
    dir_exists "$value" || { errmsg "directory $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path "${value}"`

    define_opt "${opt}" "${value}" "${varname}"
}

########
show_program_shdirs()
{
    local dirname
    for dirname in "${!PROGRAM_SHDIRS[@]}"; do
        local absdir=`get_absolute_shdirname "$dirname"`
        echo "${absdir}"
    done
}

########
register_module_program_shdirs()
{
    # Populate associative array of shared directories for the loaded
    # modules
    local absmodname
    for absmodname in "${PROGRAM_MODULES[@]}"; do
        local shrdirs_funcname=`get_shrdirs_funcname ${absmodname}`
        if func_exists "${shrdirs_funcname}"; then
            ${shrdirs_funcname} || exit 1
        fi
    done
}

########
create_mod_shdirs()
{
    # Create shared directories for modules
    local dirname
    for dirname in "${!PROGRAM_SHDIRS[@]}"; do
        local owner=${PROGRAM_SHDIRS["${dirname}"]}
        if [ "${owner}" = "${SHDIR_MODULE_OWNER}" ]; then
            local absdir=`get_absolute_shdirname "$dirname"`
            if [ ! -d "${absdir}" ]; then
                "${MKDIR}" -p "${absdir}" || exit 1
            fi
        fi
    done
}

########
create_shdirs_owned_by_process()
{
    local processname=$1
    # Create shared directories for process
    local dirname
    for dirname in "${!PROGRAM_SHDIRS[@]}"; do
        local owner=${PROGRAM_SHDIRS["${dirname}"]}
        if [ "${processname}" = "${owner}" ]; then
            local absdir=`get_absolute_shdirname "$dirname"`
            if [ ! -d "${absdir}" ]; then
                "${MKDIR}" -p "${absdir}" || exit 1
            fi
        fi
    done
}

########
show_program_fifos()
{
    local augm_fifoname
    for augm_fifoname in "${!PROGRAM_FIFOS[@]}"; do
        echo "${augm_fifoname}" ${PROGRAM_FIFOS["${augm_fifoname}"]} ${FIFO_USERS["${augm_fifoname}"]}
    done
}

########
prepare_fifos_owned_by_process()
{
    local processname=$1

    # Obtain name of directory for FIFOS
    local fifodir=`get_absolute_fifodir`

    # Create FIFOS
    local augm_fifoname
    for augm_fifoname in "${!PROGRAM_FIFOS[@]}"; do
        local proc_plus_idx=${PROGRAM_FIFOS["${augm_fifoname}"]}
        local proc="${proc_plus_idx%%${ASSOC_ARRAY_ELEM_SEP}*}"
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
get_absolute_shdirname()
{
    local shdirname=$1

    # Output absolute shared directory name
    echo "${PROGRAM_OUTDIR}/${shdirname}"
}

########
get_absolute_fifodir()
{
    echo "${PROGRAM_OUTDIR}/.fifos"
}

########
get_absolute_fifoname()
{
    local owner_process=$1
    local fifoname=$2
    local augm_fifoname="${owner_process}/${fifoname}"
    local fifodir=`get_absolute_fifodir`

    echo "${fifodir}/${augm_fifoname}"
}

########
get_augm_fifoname_from_absname()
{
    local absname=$1

    local fifoname=`${BASENAME} "${absname}"`
    local dirname=`${DIRNAME} "${absname}"`
    local owner_process=`${BASENAME} "${dirname}"`

    echo "${owner_process}/${fifoname}"
}

########
get_absolute_condadir()
{
    echo "${PROGRAM_OUTDIR}/.conda"
}

########
clear_curr_opt_list_array()
{
    unset CURRENT_PROCESS_OPT_LIST
    declare -ga CURRENT_PROCESS_OPT_LIST
}

########
# Public: Saves option list.
#
# TO-BE-DONE
#
# $1 - Option name
#
# Examples
#
#   TO-BE-DONE
#
# The function does not return any value
save_opt_list()
{
    generate_opt_list()
    {
        local processname=$1
        local task_idx=$2
        local opts=$3

        # Initialize reference to associative array storing the option
        # list
        local opt_list_name="opt_list_${processname}_${task_idx}"
        declare -gA "${opt_list_name}"
        declare -nl opt_list=${opt_list_name}

        # Iterate over options
        deserialize_args "${opts}"
        local i=0
        while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
            # Check if option was found
            if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
                local opt="${DESERIALIZED_ARGS[$i]}"
                i=$((i+1))
                # Obtain value if it exists
                local value=""
                # Check if next token is an option
                if [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; then
                    if str_is_option "${DESERIALIZED_ARGS[$i]}"; then
                        opt_list["${opt}"]=""
                    else
                        value="${DESERIALIZED_ARGS[$i]}"
                        opt_list["${opt}"]=${value}
                        i=$((i+1))
                    fi
                fi
            else
                echo "Warning: unexpected value (${DESERIALIZED_ARGS[$i]}), skipping..." >&2
                i=$((i+1))
            fi
        done
    }

    get_output_opts_info()
    {
        local processname=$1
        local task_idx=$2

        # Process function arguments
        shift
        shift
        local i=1
        while [ $i -le $# ]; do
            # Check if option was found
            if str_is_option "${!i}"; then
                local opt=${!i}
                i=$((i+1))
                # Obtain value if it exists
                local value=""
                # Check if next token is an option
                if [ "$i" -le $# ]; then
                    if str_is_option "${!i}"; then
                        :
                    else
                        value="${!i}"
                        if is_absolute_path "${value}" && str_is_output_option "${opt}"; then
                            # Update out value to processes array
                            local process_info="${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}"
                            if [[ -v OUT_VALUE_TO_PROCESSES["${value}"] ]]; then
                                OUT_VALUE_TO_PROCESSES["$value"]=${OUT_VALUE_TO_PROCESSES["$value"]}${ASSOC_ARRAY_PROC_SEP}${process_info}
                            else
                                OUT_VALUE_TO_PROCESSES["$value"]=${process_info}
                            fi
                        fi
                        i=$((i+1))
                    fi
                fi
            else
                echo "Warning: unexpected value (${!i}), skipping..." >&2
                i=$((i+1))
            fi
        done
    }

    get_output_opts_info_given_opts()
    {
        local processname=$1
        local task_idx=$2
        local opts=$3

        deserialize_args "${opts}"
        get_output_opts_info "${processname}" "${task_idx}" "${DESERIALIZED_ARGS[@]}"
    }

    save_opt_list_loop()
    {
        # Initialize variables
        local processname=$1
        local opts=$2

        # Obtain task index and update list length for process
        local task_idx
        if [ -z "${PROCESS_OPT_LIST_LEN[${processname}]}" ]; then
            task_idx=0
            PROCESS_OPT_LIST_LEN[${processname}]=1
        else
            task_idx=${PROCESS_OPT_LIST_LEN[${processname}]}
            ((PROCESS_OPT_LIST_LEN[${processname}]++))
        fi

        # Generate option list for process
        generate_opt_list "${processname}" "${task_idx}" "${opts}"

        # Update variables storing output option information
        get_output_opts_info_given_opts "${processname}" "${task_idx}" "${opts}"
    }

    save_opt_list_generator()
    {
        # Initialize variables
        local opts=$1

        # Put options in DESERIALIZED_ARGS (this is the only thing that
        # should be done by the generator here)
        deserialize_args "${opts}"
    }

    # Initialize variables
    local -n opts=$1
    local save_opt_list_proc

    # Try to extract process name from generate_opts function
    get_processname_from_caller_nameref "${PROCESS_METHOD_NAME_GENERATE_OPTS}" save_opt_list_proc
    if [ -n "${save_opt_list_proc}" ]; then
        save_opt_list_generator "${opts}"
        return 0
    fi

    # Try to extract process name from define_opts_function
    get_processname_from_caller_nameref "${PROCESS_METHOD_NAME_DEFINE_OPTS}" save_opt_list_proc
    if [ -n "${save_opt_list_proc}" ]; then
        save_opt_list_loop "${save_opt_list_proc}" "${opts}"
        return 0
    fi

    # If no process name was found, abort execution
    echo "save_opts: critical error, process name could not be determined!" >&2
    exit 1
}

########
load_curr_opt_list_loop()
{
    # WARNING: The resolve_proc_output_desc function should be called in
    # a subshell, otherwise it may clash with the caller due to its use
    # of the DESERIALIZE_ARGS variable
    resolve_proc_output_desc()
    {
        local cmdline=$1
        local value=$2

        # Extract information of connected process
        local connected_proc_info="${value#$PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"
        deserialize_args_given_sep "${connected_proc_info}" "${ASSOC_ARRAY_ELEM_SEP}"
        local connected_proc=${DESERIALIZED_ARGS[0]}
        local connected_proc_task_idx=${DESERIALIZED_ARGS[1]}
        local connected_proc_opt=${DESERIALIZED_ARGS[2]}

        # If connected process uses a generator, the treatment should be
        # different
        if uses_option_generator "${connected_proc}"; then
            # Obtain name of options generator
            local generate_opts_funcname=`get_generate_opts_funcname ${connected_proc}`

            # Call options generator (output stored into DESERIALIZED_ARGS)
            local connected_proc_spec=${INITIAL_PROCESS_SPEC["${connected_proc}"]}
            local connected_proc_outdir=`get_process_outdir "${connected_proc}"`
            ${generate_opts_funcname} "${cmdline}" "${connected_proc_spec}" "${connected_proc}" "${connected_proc_outdir}" "${task_idx}" || return 1

            # Option value from options
            value=`get_opt_value_from_func_args "${connected_proc_opt}" "${DESERIALIZED_ARGS[@]}"`

            # Obtain value from list
            echo ${value}
        else
            # Obtain reference to option list of connected process
            local connected_proc_opt_list_name="opt_list_${connected_proc}_${connected_proc_task_idx}"
            declare -nl connected_proc_opt_list=${connected_proc_opt_list_name}

            # Obtain value from list
            value=${connected_proc_opt_list[$connected_proc_opt]}
            echo ${value}
        fi
    }

    local cmdline=$1
    local processname=$2

    # Clear array
    clear_curr_opt_list_array

    # Iterate over process options
    local task_idx
    for (( task_idx=0; task_idx<${PROCESS_OPT_LIST_LEN[${processname}]}; task_idx++ )); do
        # Initialize variables
        local opt_list_name="opt_list_${processname}_${task_idx}"
        declare -nl opt_list=${opt_list_name}
        local _load_curr_opt_list_loop_optlist=""

        # Process options for task
        local opt
        for opt in "${!opt_list[@]}"; do
            local value=${opt_list[$opt]}

            # Resolve process output descriptor if necessary
            if str_is_proc_out_opt_descriptor "${value}"; then
                value=`resolve_proc_output_desc "${cmdline}" "${value}"`
            fi

            # Define option
            if [ -z "${value}" ]; then
                define_opt_wo_value "${opt}" "_load_curr_opt_list_loop_optlist"
            else
                define_opt "${opt}" "${value}" "_load_curr_opt_list_loop_optlist"
            fi
        done
        CURRENT_PROCESS_OPT_LIST+=("${_load_curr_opt_list_loop_optlist}")
    done
}

########
show_curr_opt_list()
{
    local cmdline=$1
    local processname=$2

    # Show array length
    local num_tasks=`get_numtasks_for_process "${processname}"`
    echo "${processname}${ASSOC_ARRAY_ELEM_SEP}${ASSOC_ARRAY_KEY_LEN} -> ${num_tasks}"

    # Show options
    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        local opts=`get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`
        echo "${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx} -> ${opts}"
    done
}

########
get_serial_process_opts()
{
    local cmdline=$1
    local processname=$2
    local max_num_proc_opts_to_display=$3

    # Store options in array
    local process_opts_array=()
    local ellipsis=""
    local num_tasks=`get_numtasks_for_process "${processname}"`

    local task_idx
    for ((task_idx = 0; task_idx < num_tasks; task_idx++)); do
        # Obtain process options
        local process_opts=`get_opts_for_process_and_task "${cmdline}" "${processname}" "${task_idx}"`

        # Obtain human-readable representation of process options
        hr_process_opts=$(sargs_to_sargsquotes "${process_opts}")
        process_opts_array+=("${hr_process_opts}")

        # Exit loop if maximum number of options is exceeded
        if [ "${#process_opts_array[@]}" -ge "${max_num_proc_opts_to_display}" ]; then
            ellipsis="..."
            break
        fi
    done

    # Serialize array
    local serial_process_opts=`serialize_string_array "process_opts_array" "${ARRAY_TASK_SEP}"`

    # Return result
    echo "${serial_process_opts} ${ellipsis}"
}

########
show_out_values_for_processes()
{
    for outval in "${!OUT_VALUE_TO_PROCESSES[@]}"; do
        echo "${outval} -> ${OUT_VALUE_TO_PROCESSES[${outval}]}"
    done
}

########
get_proc_out_opt_from_desc()
{
    local proc_out_opt_descriptor=$1

    # Obtain process plus option info
    local process_opt_info="${proc_out_opt_descriptor#$PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"

    echo ${PROCESS_TO_OUT_VALUE["${process_opt_info}"]}
}

########
write_value_to_desc()
{
    local value=$1
    local value_descriptor=$2

    echo "${value}" > "${value_descriptor}"
}

########
read_value_from_desc()
{
    local value_descriptor=$1

    cat "${value_descriptor}"
}

########
get_sched_opts_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${SCHED_OPTS_DIRNAME}"
}

########
get_sched_opts_dir()
{
    get_sched_opts_dir_given_basedir "${PROGRAM_OUTDIR}"
}

########
get_sched_opts_fname_for_process()
{
    local dirname=$1
    local processname=$2

    local sched_opts_dir=`get_sched_opts_dir_given_basedir "${dirname}"`
    echo "${sched_opts_dir}/${SCHED_OPTS_FNAME_FOR_PROCESS_PREFIX}${processname}"
}
