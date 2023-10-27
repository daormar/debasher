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
deserialize_args()
{
    local serial_args=$1
    if [ -z "${serial_args}" ]; then
        unset DESERIALIZED_ARGS
        declare -ga DESERIALIZED_ARGS
    else
        local new_sep=$'\n'
        local preproc_sargs="${serial_args//${ARG_SEP}/$new_sep}"
        unset DESERIALIZED_ARGS
        declare -ga DESERIALIZED_ARGS
        while IFS=${new_sep} read -r; do DESERIALIZED_ARGS+=( "${REPLY}" ); done <<< "${preproc_sargs}"
    fi
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
read_opt_value_from_line()
{
    local cmdline=$1
    local opt=$2

    # Convert string to array (result is placed into the
    # DESERIALIZED_ARGS variable)
    deserialize_args "${cmdline}"

    # Scan DESERIALIZED_ARGS
    local i=0
    while [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; do
        # Check if option was found
        if [ "${DESERIALIZED_ARGS[$i]}" = "${opt}" ]; then
            i=$((i+1))
            # Obtain value if it exists
            local value=""
            # Check if next token is an option
            if [ $i -lt ${#DESERIALIZED_ARGS[@]} ]; then
                if [ "${DESERIALIZED_ARGS[$i]:0:1}" = "-" ] || [ "${DESERIALIZED_ARGS[$i]:0:2}" = "--" ]; then
                    :
                else
                    value="${DESERIALIZED_ARGS[$i]}"
                    i=$((i+1))
                fi
            fi

            # Show value if it exists and return
            if [ -z "${value}" ]; then
                echo ${VOID_VALUE}
                return 1
            else
                echo "${value}"
                return 0
            fi
        fi
        i=$((i+1))
    done

    # Option not given
    echo ${OPT_NOT_FOUND}
    return 1
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
        if [ "${PIPELINE_OPT_PROCESS[${opt}]}" = "" ]; then
            PIPELINE_OPT_PROCESS[${opt}]=${processname}
        else
            PIPELINE_OPT_PROCESS[${opt}]="${PIPELINE_OPT_PROCESS[${opt}]} ${processname}"
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
    PIPELINE_OPT_TYPE[$opt]=$type
    PIPELINE_OPT_REQ[$opt]=1
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
}

########
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
    PIPELINE_OPT_TYPE[$opt]=$type
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1

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
    PIPELINE_OPT_TYPE[$opt]=""
    PIPELINE_OPT_DESC[$opt]=$desc
    PIPELINE_OPT_CATEG[$opt]=$categ
    PIPELINE_CATEG_MAP[$categ]=1

    # Add option to differential command line option string
    if [ "${DIFFERENTIAL_CMDLINE_OPT_STR}" = "" ]; then
        DIFFERENTIAL_CMDLINE_OPT_STR=${opt}
    else
        DIFFERENTIAL_CMDLINE_OPT_STR="${DIFFERENTIAL_CMDLINE_OPT_STR} ${opt}"
    fi
}

########
print_pipeline_opts()
{
    local lineno=0

    # Iterate over option categories
    local categ
    for categ in ${!PIPELINE_CATEG_MAP[@]}; do
        if [ ${lineno} -gt 0 ]; then
            echo ""
        fi
        echo "CATEGORY: ${categ}"
        # Iterate over options
        local opt
        for opt in ${!PIPELINE_OPT_TYPE[@]}; do
            # Check if option belongs to current category
            if [ ${PIPELINE_OPT_CATEG[${opt}]} = $categ ]; then
                # Set value of required option flag
                if [ "${PIPELINE_OPT_REQ[${opt}]}" != "" ]; then
                    reqflag=" (required) "
                else
                    reqflag=" "
                fi

                # Print option
                if [ -z ${PIPELINE_OPT_TYPE[$opt]} ]; then
                    echo "${opt} ${PIPELINE_OPT_DESC[$opt]}${reqflag}[${PIPELINE_OPT_PROCESS[$opt]}]"
                else
                    echo "${opt} ${PIPELINE_OPT_TYPE[$opt]} ${PIPELINE_OPT_DESC[$opt]}${reqflag}[${PIPELINE_OPT_PROCESS[$opt]}]"
                fi
            fi
        done

        lineno=$((lineno + 1))
    done
}

########
define_fifo()
{
    local fifoname=$1

    # Get process name
    local processname=`get_processname_from_caller "${PROCESS_METHOD_NAME_DEFINE_OPTS}"`

    # Get task index
    task_idx=${#CURRENT_PROCESS_OPT_LIST[@]}

    # Get augmented fifo name
    local augm_fifoname="${processname}/${fifoname}"

    # Store name of FIFO in associative arrays
    PIPELINE_FIFOS["${augm_fifoname}"]=${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}
    PIPELINE_FIFOS_DEF_OPTS["${augm_fifoname}"]=${processname}${ASSOC_ARRAY_ELEM_SEP}${task_idx}
}

########
define_shared_dir()
{
    local shared_dir=$1

    # Store name of shared directory in associative arrays
    PIPELINE_SHDIRS["${shared_dir}"]=1
    PIPELINE_SHDIRS_DEF_OPTS["${shared_dir}"]=1
}

########
define_cmdline_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }
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
    check_opt_given "$cmdline" $opt || { errmsg "$opt option not found" ; return 1; }

    # Add option
    define_opt_wo_value $opt $varname
}

########
define_cmdline_nonmandatory_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt
    local value="${_OPT_VALUE_}"

    if [ "$value" = ${OPT_NOT_FOUND} ]; then
        value=${default_value}
    fi

    # Add option
    define_opt $opt "$value" $varname
}

########
define_cmdline_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt
    local value=${_OPT_VALUE_}

    if [ "$value" != ${OPT_NOT_FOUND} ]; then
        # Add option
        define_opt $opt "$value" $varname
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
    define_opt $opt "$value" $varname
}

########
define_cmdline_infile_nonmand_opt()
{
    local cmdline=$1
    local opt=$2
    local default_value=$3
    local varname=$4

    # Get value for option
    read_opt_value_from_line_memoiz "$cmdline" $opt
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
    define_opt $opt "$value" $varname
}

########
define_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_opt: wrong input parameters"
        return 1
    fi

    if [ -z "${!varname}" ]; then
        local var=${varname}
        local val="${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$val" || { errmsg "define_opt: execution error" ; return 1; }
    else
        local var=${varname}
        local val="${!varname}${ARG_SEP}${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$val" || { errmsg "define_opt: execution error" ; return 1; }
    fi
}

########
define_opt_wo_value()
{
    local opt=$1
    local varname=$2

    # Check parameters
    if [ "${opt}" = "" -o "${varname}" = "" ]; then
        errmsg "define_opt_wo_value: wrong input parameters"
        return 1
    fi

    if [ -z "${!varname}" ]; then
        local var=${varname}
        local value="${opt}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_opt_wo_value: execution error" ; return 1; }
    else
        local var=${varname}
        local value="${!varname}${ARG_SEP}${opt}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_opt_wo_value: execution error" ; return 1; }
    fi
}

########
define_infile_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_infile_opt: wrong input parameters"
        return 1
    fi

    # Check if file exists
    file_exists "$value" || { errmsg "file $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path "${value}"`

    if [ -z "${!varname}" ]; then
        local var=${varname}
        local value="${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_infile_opt: execution error" ; return 1; }
    else
        local var=${varname}
        local value="${!varname}${ARG_SEP}${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_infile_opt: execution error" ; return 1; }
    fi
}

########
define_indir_opt()
{
    local opt=$1
    local value=$2
    local varname=$3

    # Check parameters
    if [ "${opt}" = "" -o "${value}" = "" -o "${varname}" = "" ]; then
        errmsg "define_indir_opt: wrong input parameters"
        return 1
    fi

    # Check if file exists
    dir_exists "$value" || { errmsg "directory $value does not exist ($opt option)" ; return 1; }

    # Absolutize path
    value=`get_absolute_path "${value}"`

    if [ -z "${!varname}" ]; then
        local var=${varname}
        local value="${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_indir_opt: execution error" ; return 1; }
    else
        local var=${varname}
        local value="${!varname}${ARG_SEP}${opt}${ARG_SEP}${value}"
        IFS= read -r "$var" <<<"$value" || { errmsg "define_indir_opt: execution error" ; return 1; }
    fi
}

########
show_pipeline_shdirs()
{
    local dirname
    for dirname in "${!PIPELINE_SHDIRS[@]}"; do
        local absdir=`get_absolute_shdirname "$dirname"`
        echo "${absdir}"
    done
}

########
register_module_pipeline_shdirs()
{
    # Populate associative array of shared directories for the loaded
    # modules
    local absmodname
    for absmodname in "${PIPELINE_MODULES[@]}"; do
        local shrdirs_funcname=`get_shrdirs_funcname ${absmodname}`
        if func_exists "${shrdirs_funcname}"; then
            ${shrdirs_funcname} || exit 1
        fi
    done
}

########
create_pipeline_shdirs()
{
    # Create shared directories
    local dirname
    for dirname in "${!PIPELINE_SHDIRS[@]}"; do
        local absdir=`get_absolute_shdirname "$dirname"`
        if [ ! -d "${absdir}" ]; then
           "${MKDIR}" -p "${absdir}" || exit 1
        fi
    done
}

########
create_shdirs_owned_by_process()
{
    # Create shared directories
    local dirname
    for dirname in "${!PIPELINE_SHDIRS_DEF_OPTS[@]}"; do
        local absdir=`get_absolute_shdirname "$dirname"`
        if [ ! -d "${absdir}" ]; then
           "${MKDIR}" -p "${absdir}" || exit 1
        fi
    done
}

########
show_pipeline_fifos()
{
    local augm_fifoname
    for augm_fifoname in "${!PIPELINE_FIFOS[@]}"; do
        echo "${augm_fifoname}" ${PIPELINE_FIFOS["${augm_fifoname}"]} ${FIFO_USERS["${augm_fifoname}"]}
    done
}

########
show_pipeline_fifos_def_opts()
{
    local augm_fifoname
    for augm_fifoname in "${!PIPELINE_FIFOS_DEF_OPTS[@]}"; do
        echo "${augm_fifoname}" ${PIPELINE_FIFOS_DEF_OPTS["${augm_fifoname}"]} ${FIFO_USERS["${augm_fifoname}"]}
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
    for augm_fifoname in "${!PIPELINE_FIFOS_DEF_OPTS[@]}"; do
        local proc_plus_idx=${PIPELINE_FIFOS_DEF_OPTS["${augm_fifoname}"]}
        local proc="${proc_plus_idx%%${ASSOC_ARRAY_ELEM_SEP}*}"
        if [ "${proc}" = "${processname}" ]; then
            local dirname=`"${DIRNAME}" "${augm_fifoname}"`
            "${MKDIR}" -p "${fifodir}/${dirname}"
            rm -f "${fifodir}/${augm_fifoname}" || exit 1
            "${MKFIFO}" "${fifodir}/${augm_fifoname}" || exit 1
        fi
    done
}

########
get_absolute_shdirname()
{
    local shdirname=$1

    # Output absolute shared directory name
    echo "${PIPELINE_OUTDIR}/${shdirname}"
}

########
get_absolute_fifodir()
{
    echo "${PIPELINE_OUTDIR}/.fifos"
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
    echo "${PIPELINE_OUTDIR}/.conda"
}

########
clear_curr_opt_list_array()
{
    unset CURRENT_PROCESS_OPT_LIST
    declare -ga CURRENT_PROCESS_OPT_LIST
}

########
clear_opt_list_assoc_array()
{
    unset PROCESS_OPT_LIST
    declare -gA PROCESS_OPT_LIST
}

########
save_opt_list()
{
    # Set option list for current process
    local optlist_varname=$1
    CURRENT_PROCESS_OPT_LIST+=("${!optlist_varname}")
}

########
show_opt_list_for_processes()
{
    for process in "${!PROCESS_OPT_LIST[@]}"; do
        echo "${process} -> ${PROCESS_OPT_LIST[${process}]}"
    done
}

########
show_out_values_for_processes()
{
    for outval in "${!PROCESS_OUT_VALUES[@]}"; do
        echo "${outval} -> ${PROCESS_OUT_VALUES[${outval}]}"
    done
}
