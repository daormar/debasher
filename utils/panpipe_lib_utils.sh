#####################
# PANPIPE UTILITIES #
#####################

########
panpipe_version()
{
    echo "${panpipe_pkgname} version: ${panpipe_version}" >&2
}

########
version_to_number()
{
    local ver=$1

    echo "$ver" | "${AWK}" -F. '{ printf("%03d%03d%03d\n", $1,$2,$3); }'
}

########
pipe_fail()
{
    # test if there is at least one command to exit with a non-zero status
    local pipestatus=${PIPESTATUS[*]}
    local pipe_status_elem
    for pipe_status_elem in ${pipestatus}; do
        if test ${pipe_status_elem} -ne 0; then
            return 1;
        fi
    done
    return 0
}

########
init_bash_shebang_var()
{
    echo "#!${BASH}"
}

########
is_absolute_path()
{
    local file=$1
    case "$file" in
        /*) return 0
            ;;
        *) return 1
           ;;
    esac
}

########
get_absolute_path()
{
  local relative_path=$1
  local current_dir="$(pwd)"
  local absolute_path=""

  if [[ "$relative_path" == /* ]]; then
    # If the relative path is already an absolute path
    absolute_path="$relative_path"
  else
    # If the relative path is not absolute, make it absolute
    absolute_path="$current_dir/$relative_path"
  fi

  # Normalize the path to handle any double slashes or dots
  absolute_path=$("${REALPATH}" "$absolute_path")

  echo "$absolute_path"
}

########
get_absolute_path_existing()
{
    # IMPORTANT WARNING: This function just returns the given path if it
    # does not correspond with a existing file or directory.
    local file=$1

    # Check if an absolute path was given
    if is_absolute_path "$file"; then
        echo "$file"
        return 0
    else
        # Check if path corresponds to a directory
        if [ -d "$file" ]; then
            local oldpwd=$PWD
            cd "$file"
            local result=${PWD}
            cd "$oldpwd"
            echo "$result"
            return 0
        else
            # Path corresponds to a file
            local oldpwd=$PWD
            local basetmp=`"$BASENAME" "$PWD/$file"`
            local dirtmp=`"$DIRNAME" "$PWD/$file"`
            # Check if directory containing the file exists
            if [ -d "$dirtmp" ]; then
                cd "$dirtmp"
                local result=${PWD}/${basetmp}
                cd "$oldpwd"
                echo "$result"
                return 0
            else
                # Directory containing the file does not exist, so it's
                # not possible to obtain the absolute path
                echo "$file"
                echo "get_absolute_path: absolute path could not be determined!" >&2
                return 1
            fi
        fi
    fi
}

########
normalize_dirname()
{
    local dir=$1

    echo `echo "${dir}/" | "$TR" -s "/"`
}

########
dirnames_are_equal()
{
    local dir1=$1
    local dir2=$2

    norm_dir1=`normalize_dirname "$dir1"`
    norm_dir2=`normalize_dirname "$dir2"`

    if [ "${norm_dir1}" = "${norm_dir2}" ]; then
        return 0
    else
        return 1
    fi
}

########
expand_tildes()
{
    local str=$1
    str="${str/#\~/$HOME}"
    str="${str// \~/ $HOME}"
    echo "${str}"
}

########
exclude_readonly_vars()
{
    "$AWK" -F "=" 'BEGIN{
                         readonlyvars["BASHOPTS"]=1
                         readonlyvars["BASH_VERSINFO"]=1
                         readonlyvars["EUID"]=1
                         readonlyvars["PPID"]=1
                         readonlyvars["SHELLOPTS"]=1
                         readonlyvars["UID"]=1
                        }
                        {
                         if(!($1 in readonlyvars)) printf"%s\n",$0
                        }'
}

########
exclude_other_vars()
{
    "$AWK" -F "=" 'BEGIN{
                         othervars["MEMOIZED_OPTS"]=1
                        }
                        {
                         if(!($1 in othervars)) printf"%s\n",$0
                        }'
}

########
exclude_bashisms()
{
    "$AWK" '{if(index($1,"=(")==0) printf"%s\n",$0}'
}

########
replace_str_elem_sep_with_blank()
{
    local sep=$1
    local str=$2
    local str_array
    local result

    IFS="$sep" read -r -a str_array <<< "${str}"

    result=${str_array[@]}

    echo "${result}"
}

########
serialize_string_array()
{
    local str_array_name=$1[@]
    local str_array=("${!str_array_name}")
    local array_task_sep=$2
    local max_elems=$3
    local result=""
    local num_elem=0

    local str
    for str in "${str_array[@]}"; do
        # Check if number of elements has been exceeded
        if [ ! -z "${max_elems}" ]; then
            if [ ${num_elem} -ge ${max_elems} ]; then
                if [ ! -z "${result}" ]; then
                    result="${result}${array_task_sep}..."
                    break
                fi
            fi
        fi

        # Add new element
        if [ -z "${result}" ]; then
            result="${str}"
        else
            result="${result}${array_task_sep}${str}"
        fi

        num_elem=$((num_elem + 1))
    done

    echo "$result"
}

########
func_exists()
{
    local funcname=$1

    type ${funcname} >/dev/null 2>&1 || return 1

    return 0
}

########
errmsg()
{
    local msg=$1
    echo "$msg" >&2
}

########
logmsg()
{
    local msg=$1
    echo "$msg" >&2
}

########
log_err_msg()
{
    local msg=$1
    echo "${PANPIPE_LOG_ERR_MSG_START} $msg" >&2
}

########
log_warning_msg()
{
    local msg=$1
    echo "${PANPIPE_LOG_WARNING_MSG_START} $msg" >&2
}

########
get_script_log_filenames()
{
    local scripts_dirname=`get_ppl_scripts_dir`

    for filename in "${scripts_dirname}/"*.${BUILTIN_SCHED_LOG_FEXT}; do
        if [ -f "${filename}" ]; then
            echo "${filename}"
        fi
    done

    for filename in "${scripts_dirname}/"*.${SLURM_SCHED_LOG_FEXT}; do
        if [ -f "${filename}" ]; then
            echo "${filename}"
        fi
    done
}

########
filter_errors_in_script_log_file()
{
    local prefix=$1
    local filename=$2

    "${GREP}" "${PANPIPE_LOG_ERROR_MSG_START}" "${filename}" | "${AWK}" -v prefix="${prefix}" '{printf"%s%s\n\n",prefix,$0}' ; pipe_fail || return 1
}

########
filter_warnings_in_script_log_file()
{
    local prefix=$1
    local filename=$2

    "${GREP}" "${PANPIPE_LOG_WARNING_MSG_START}" "${filename}" | "${AWK}" -v prefix="${prefix}" '{printf"%s%s\n\n",prefix,$0}' ; pipe_fail || return 1
}

########
create_script_log_file_errwarn_entry()
{
    local errpref=$1
    local warnpref=$2
    local format=$3
    local filename=$4

    case "${format}" in
        "md")
            echo "[${filename}](file://${filename})"
            echo ""
            filter_errors_in_script_log_file "${errpref}" "${filename}"
            filter_warnings_in_script_log_file "${warnpref}" "${filename}"
            ;;
        *)
            echo "File: ${filename}"
            if ! filter_errors_in_script_log_file "${errpref}" "${filename}"; then
                if ! filter_warnings_in_script_log_file "${warnpref}" "${filename}"; then
                    echo "NONE"
                fi
            fi
            ;;
    esac
}

########
filter_errwarns_in_script_log_files_pref()
{
    local errpref=$1
    local warnpref=$2
    local format=$3
    local scripts_dirname=`get_ppl_scripts_dir`
    local i=0

    while read filename; do
        if [ ${i} -gt 0 ]; then
            echo ""
        fi

        create_script_log_file_errwarn_entry "${errpref}" "${warnpref}" "${format}" "${filename}"

        i=$((i+1))
    done < <(get_script_log_filenames)
}

########
filter_errwarns_in_script_log_files()
{
    filter_warnings_in_script_log_files_pref "" "" "md"
}

########
replace_tilde_by_homedir()
{
    local file=$1

    if [ "${file:0:1}" = "~" ]; then
        echo "$HOME${file:1}"
    else
        echo "$file"
    fi
}

########
file_exists()
{
    local file=$1
    if [ -f "$file" ]; then
        return 0
    else
        return 1
    fi
}

########
dir_exists()
{
    local dir=$1
    if [ -d "$dir" ]; then
        return 0
    else
        return 1
    fi
}

########
convert_mem_value_to_mb()
{
    local mem_value=$1

    local len=${#mem_value}
    local len_m_one=$((len - 1))
    local mem_value_suff="${mem_value:${len_m_one}:1}"
    case ${mem_value_suff} in
        "K") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} / 1024 || return 1
             ;;
        "M") echo ${mem_value:0:${len_m_one}}
             ;;
        "G") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} \* 1024 || return 1
             ;;
        "T") local mem_value_wo_suff=${mem_value:0:${len_m_one}}
             expr ${mem_value_wo_suff} \* 1024 \* 1024 || return 1
             ;;
        *) echo ${mem_value}
           ;;
    esac
}

########
str_is_natural_number()
{
    local str=$1

    case $str in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

########
get_num_words_in_string()
{
    local str=$1
    echo "${str}" | "${WC}" -w
}

########
get_first_n_fields_of_str()
{
    local str=$1
    local n_val=$2

    local result
    for field in ${str}; do
        if [ ${n_val} -eq 0 ]; then
            break
        else
            n_val=$((n_val - 1))
        fi

        if [ "${result}" = "" ]; then
            result="$field"
        else
            result="${result} ${field}"
        fi
    done

    echo $result
}

########
get_panpipe_exec_path()
{
    echo "${panpipe_bindir}/panpipe_exec"
}

########
clear_pipeline_shdirs_array()
{
    declare -gA PIPELINE_SHDIRS
}

########
get_processname_from_caller()
{
    local caller_suffix=$1

    for element in "${FUNCNAME[@]}"; do
        if [[ "$element" == *"${caller_suffix}" ]]; then
            local processname=${element%"${caller_suffix}"}
            echo "${processname}"
            return 0
        fi
    done

    return 1
}

########
get_suffix_from_processname()
{
    local processname=$1
    suffix="${processname##*${PROCESSNAME_SUFFIX_SEP}}"
    echo "${suffix}"
}

########
remove_suffix_from_processname()
{
    local processname=$1

    echo "${processname%%${PROCESSNAME_SUFFIX_SEP}*}"
}

########
search_process_func()
{
    local processname=$1
    local funcname_suffix=$2

    # Check if function exists
    local process_function_reset="${processname}${funcname_suffix}"
    if func_exists ${process_function_reset}; then
        echo ${process_function_reset}
    else
        # Check if function without suffix exists
        local processname_wo_suffix=`remove_suffix_from_processname ${processname}`
        process_function_reset="${processname_wo_suffix}${funcname_suffix}"
        if func_exists ${process_function_reset}; then
            echo ${process_function_reset}
        else
            echo ${FUNCT_NOT_FOUND}
        fi
    fi
}

########
search_process_mandatory_func()
{
    local processname=$1
    local funcname_suffix=$2

    # Check if function exists
    local process_function="${processname}${funcname_suffix}"
    if func_exists ${process_function}; then
        echo ${process_function}
    else
        # Return function name without suffix
        local processname_wo_suffix=`remove_suffix_from_processname ${processname}`
        echo "${processname_wo_suffix}${funcname_suffix}"
    fi
}
