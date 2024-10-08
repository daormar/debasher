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

######################
# DEBASHER UTILITIES #
######################

########
debasher_version()
{
    echo "${debasher_pkgname} version: ${debasher_version}" >&2
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
                         othervars["OUT_VALUE_TO_PROCESSES"]=1
                         othervars["FIFO_USERS"]=1
                         othervars["PROGRAM_FIFOS"]=1
                         othervars["CURRENT_PROCESS_OPT_LIST"]=1 # This variable may become huge when working with arrays and is loaded from a separate file
                         othervars["PROCESS_OPT_LIST"]=1 # This variable is not necessary and may become huge when working with arrays
                        }
                        {
                         if(!($1 in othervars)) printf"%s\n",$0
                        }'
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
var_exists()
{
    local varname=$1

    if [ -v "${varname}" ]; then
        return 0
    else
        return 1
    fi
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
    echo "${DEBASHER_LOG_ERR_MSG_START} $msg" >&2
}

########
log_warning_msg()
{
    local msg=$1
    echo "${DEBASHER_LOG_WARNING_MSG_START} $msg" >&2
}

########
get_script_log_filenames()
{
    local exec_dirname=`get_prg_exec_dir`

    local sched=`get_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            get_script_log_filenames_slurm "${exec_dirname}"
            ;;
        ${BUILTIN_SCHEDULER})
            get_script_log_filenames_builtin "${exec_dirname}"
            ;;
    esac
}

########
filter_errors_in_script_log_file()
{
    local prefix=$1
    local filename=$2

    "${GREP}" "${DEBASHER_LOG_ERROR_MSG_START}" "${filename}" | "${AWK}" -v prefix="${prefix}" '{printf"%s%s\n\n",prefix,$0}' ; pipe_fail || return 1
}

########
filter_warnings_in_script_log_file()
{
    local prefix=$1
    local filename=$2

    "${GREP}" "${DEBASHER_LOG_WARNING_MSG_START}" "${filename}" | "${AWK}" -v prefix="${prefix}" '{printf"%s%s\n\n",prefix,$0}' ; pipe_fail || return 1
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
str_is_option()
{
    local str=$1
    if [ "${str:0:1}" = "-" ] || [ "${str:0:2}" = "--" ]; then
        return 0
    else
        return 1
    fi
}

########
str_is_output_option()
{
    local str=$1
    if [ "${str:0:4}" = "-out" ] || [ "${str:0:5}" = "--out" ]; then
        return 0
    else
        return 1
    fi
}

########
str_is_proc_out_opt_descriptor()
{
    local str=$1

    if [[ "${str}" == "${PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX}"* ]]; then
        return 0
    else
        return 1
    fi
}

########
str_is_val_descriptor()
{
    local str=$1

    if is_absolute_path "${str}"; then
        local basename=`"${BASENAME}" "${str}"`
        if [[ "${basename}" == "${VALUE_DESCRIPTOR_NAME_PREFIX}"* ]]; then
            return 0
        else
            return 1
        fi
    else
        return 1
    fi
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
get_debasher_exec_path()
{
    echo "${debasher_bindir}/debasher_exec"
}

########
get_processname_from_caller()
{
    local caller_method_name=$1

    for element in "${FUNCNAME[@]}"; do
        if [[ "$element" == *"${caller_method_name}" ]]; then
            local processname=${element%"${caller_method_name}"}
            echo "${processname}"
            return 0
        fi
    done

    return 1
}

########
get_processname_from_caller_nameref()
{
    local caller_method_name=$1
    local -n var_ref=$2

    for element in "${FUNCNAME[@]}"; do
        if [[ "$element" == *"${caller_method_name}" ]]; then
            var_ref=${element%"${caller_method_name}"}
            return 0
        fi
    done

    var_ref=""
    return 1
}

########
get_suffix_from_processname()
{
    local processname=$1

    # Check if processname incorporates a suffix
    if [[ "$processname" == *"${PROCESSNAME_SUFFIX_SEP}"* ]]; then
        suffix="${processname##*${PROCESSNAME_SUFFIX_SEP}}"
        echo "${suffix}"
    else
        # The processname variable does not contain any suffix
        echo ""
    fi
}

########
remove_suffix_from_processname()
{
    local processname=$1

    echo "${processname%%${PROCESSNAME_SUFFIX_SEP}*}"
}

########
get_processname_given_suffix()
{
    local processname=$1
    local suffix=$2

    if [ -z "${suffix}" ]; then
        echo "${processname}"
    else
        echo "${processname}${PROCESSNAME_SUFFIX_SEP}${suffix}"
    fi
}

########
get_process_funcname()
{
    local processname=$1
    local method_name=$2

    local process_function="${processname}${method_name}"
    echo ${process_function}
}

########
get_process_varname()
{
    local processname=$1
    local method_name=$2

    local process_function="${processname}${method_name}"
    echo ${process_function}
}

########
search_process_func()
{
    local processname=$1
    local method_name=$2

    # Check if function exists
    local process_function=`get_process_funcname "${processname}" "${method_name}"`
    if func_exists "${process_function}"; then
        echo "${process_function}"
    else
        # Check if function without process suffix exists
        local processname_wo_proc_suffix=`remove_suffix_from_processname ${processname}`
        process_function=`get_process_funcname "${processname_wo_proc_suffix}" "${method_name}"`
        if func_exists "${process_function}"; then
            echo "${process_function}"
        else
            echo "${FUNCT_NOT_FOUND}"
        fi
    fi
}

########
search_process_var()
{
    local processname=$1
    local method_name=$2

    # Check if function exists
    local process_var=`get_process_varname "${processname}" "${method_name}"`
    if var_exists "${process_var}"; then
        echo "${process_var}"
    else
        # Check if function without process suffix exists
        local processname_wo_proc_suffix=`remove_suffix_from_processname ${processname}`
        process_var=`get_process_varname "${processname_wo_proc_suffix}" "${method_name}"`
        if var_exists "${process_var}"; then
            echo "${process_var}"
        else
            echo "${VAR_NOT_FOUND}"
        fi
    fi
}

########
search_process_func_nameref()
{
    local processname=$1
    local method_name=$2
    local -n var_ref=$3

    # Check if function exists
    local process_function=`get_process_funcname "${processname}" "${method_name}"`
    if func_exists "${process_function}"; then
        var_ref="${process_function}"
    else
        # Check if function without process suffix exists
        local processname_wo_proc_suffix=`remove_suffix_from_processname ${processname}`
        process_function=`get_process_funcname "${processname_wo_proc_suffix}" "${method_name}"`
        if func_exists "${process_function}"; then
            var_ref="${process_function}"
        else
            var_ref="${FUNCT_NOT_FOUND}"
        fi
    fi
}

########
search_process_mandatory_func()
{
    local processname=$1
    local method_name=$2

    # Check if function exists
    local process_function=`get_process_funcname "${processname}" "${method_name}"`
    if func_exists "${process_function}"; then
        echo "${process_function}"
    else
        # Return function name without process suffix
        local processname_wo_suffix=`remove_suffix_from_processname ${processname}`
        process_wo_suffix_function=`get_process_funcname "${processname_wo_suffix}" "${method_name}"`
        echo "${process_wo_suffix_function}"
    fi
}

########
copy_func()
{
    local existing_funcname=$1
    local new_funcname=$2

    eval "`echo "${new_funcname}()"; declare -f ${existing_funcname} | tail -n +2`"
}

########
get_module_funcname()
{
    local modname=$1
    local method_name=$2

    local mod_function="${modname}${method_name}"
    echo ${mod_function}
}

########
print_array_elems()
{
    local arr_name=$1
    local arr_size=$2

    for ((i=0; i<$arr_size; i++)); do
        local element="${arr_name}[$i]"
        echo "${!element}"
    done
}

########
split_file_in_blocks()
{
    local filename=$1
    local outpref=$2
    local num_lines=$3

    "${AWK}" -v lines_per_block="${num_lines}" -v outpref="${outpref}" 'BEGIN{block_count=0}
             {
              if ((NR-1)  % lines_per_block == 0) {
               output_file = outpref "_" (block_count);
               ++block_count
              }
              print > output_file;
             }' "${filename}"
}

########
get_nth_file_line()
{
    local filename=$1
    local n=$2

    "${HEAD}" -n $n "${filename}" | "${TAIL}" -n 1
}

########
read_fifo_line()
{
    local fifoname=$1

    "${SED}" -u 1q $1 < "${fifoname}"
}

########
get_deblib_vars_and_funcs_fname()
{
    local dirname=$1

    echo "${dirname}/${DEBLIB_VARS_AND_FUNCS_BASENAME}"
}
