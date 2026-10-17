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
# Defines process option from a command-line option, verifying that it
# names an existing path of the given kind and normalizing it to an
# absolute path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
# $4 - Kind of path: "file" or "dir".
debasher::_define_cmdline_path_opt()
{
    local cmdline=$1
    local opt=$2
    local varname=$3
    local kind=$4

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt" || { debasher::errmsg "$opt option not found" ; return 1; }
    local value="${_OPT_VALUE_}"

    # Verify the path exists and normalize it to an absolute path
    debasher::_path_of_kind_exists "$value" "$kind" || { debasher::errmsg "$(debasher::_path_kind_noun "$kind") $value does not exist ($opt option)" ; return 1; }
    value=$(debasher::_get_absolute_path "$value")

    # Add option
    debasher::define_opt "$opt" "$value" "$varname"
}

########
# Defines process option from a command-line option that names an
# existing path of the given kind, only if the option was given through
# the command line; verifies the path exists and normalizes it to an
# absolute path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
# $4 - Kind of path: "file" or "dir".
debasher::_define_cmdline_path_opt_if_given()
{
    local cmdline=$1
    local opt=$2
    local varname=$3
    local kind=$4

    # Get value for option
    debasher::_read_opt_value_from_line_memoiz "$cmdline" "$opt"
    local value=${_OPT_VALUE_}

    if [ "$value" != ${DEBASHER_OPT_NOT_FOUND} ]; then
        debasher::_define_cmdline_path_opt "$cmdline" "$opt" "$varname" "$kind"
    fi
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
#   debasher::define_cmdline_infile_opt "${cmdline}" "-f" "optlist"
#
# The function does not return any value
debasher::define_cmdline_infile_opt()
{
    debasher::_define_cmdline_path_opt "$1" "$2" "$3" file
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
    debasher::_define_cmdline_path_opt_if_given "$1" "$2" "$3" file
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
# Public: Defines process option from a command-line option, verifying
# that it names an existing directory and normalizing it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_indir_opt "${cmdline}" "-d" "optlist"
#
# The function does not return any value
debasher::define_cmdline_indir_opt()
{
    debasher::_define_cmdline_path_opt "$1" "$2" "$3" dir
}

########
# Public: Defines process option from a command-line option, verifying
# that it names an existing directory and normalizing it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_indir_opt "${cmdline}" "-d" "optlist"
#
# The function does not return any value
define_cmdline_indir_opt() { debasher::define_cmdline_indir_opt "$@"; }

########
# Public: Defines process option from a command-line option that names
# an existing directory, only if the option was given through the command
# line; verifies the directory exists and normalizes it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   debasher::define_cmdline_indir_opt_if_given "${cmdline}" "-d" "optlist"
#
# The function does not return any value
debasher::define_cmdline_indir_opt_if_given()
{
    debasher::_define_cmdline_path_opt_if_given "$1" "$2" "$3" dir
}

########
# Public: Defines process option from a command-line option that names
# an existing directory, only if the option was given through the command
# line; verifies the directory exists and normalizes it to an absolute
# path.
#
# $1 - Command-line options taken as input of the `define_opts` or `generate_opts` method.
# $2 - Name of option given in the command line.
# $3 - Name of the variable that will store the newly added option.
#
# Examples
#
#   define_cmdline_indir_opt_if_given "${cmdline}" "-d" "optlist"
#
# The function does not return any value
define_cmdline_indir_opt_if_given() { debasher::define_cmdline_indir_opt_if_given "$@"; }

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
# computing it again. Any process can ask for that of any other, from the
# methods that define its options, and a task can ask too. Once the
# options of the asked process are defined, and inside a task, the answer
# is at hand. Before that, while the run is prepared, it is computed
# every time it is asked for: for an option generator, its
# _generate_opts_size method gives it, so its task shaping options have
# to be given; for a process without one, its whole _define_opts method
# runs again, in a subshell, which is costly, so a process whose number
# of tasks other processes need is written with an option generator when
# it can be, and a method asks once, keeping the answer in a variable. A
# number of tasks that depends on itself stops the preparation of the
# run. The number of tasks is usually read in a command substitution,
# whose failure has to stop the method that reads it.
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

    # A process whose number of tasks is being computed, in the call stack
    # that led here, depends on itself; checked first, as the tasks that
    # its method registered so far would otherwise answer
    debasher::_check_num_tasks_chain "${processname}" || return 1

    # Options defined already, or inside a task, whose execution context
    # carries the number of tasks of every process
    if [[ -v DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"] ]]; then
        echo "${DEBASHER_PROCESS_OPT_LIST_LEN["${processname}"]}"
        return 0
    fi

    # Not defined yet. Computing the number of tasks needs the command
    # line, which is only at hand while the run is prepared; once it is,
    # every process has its number of tasks, so this is a call from
    # outside a run
    if [ -z "${DEBASHER_DEFINING_OPTS_CMDLINE+x}" ]; then
        echo "Error: get_process_num_tasks: the number of tasks of process ${processname} is not known yet" >&2
        return 1
    fi
    debasher::_compute_num_tasks "${DEBASHER_DEFINING_OPTS_CMDLINE}" "${processname}"
}

########
# Public: Gets the number of tasks of a process of the program.
#
# $1 - Name of the process.
#
# A process whose number of tasks is that of another process, or whose
# task reads every task of another process, asks for it instead of
# computing it again. Any process can ask for that of any other, from the
# methods that define its options, and a task can ask too. Once the
# options of the asked process are defined, and inside a task, the answer
# is at hand. Before that, while the run is prepared, it is computed
# every time it is asked for: for an option generator, its
# _generate_opts_size method gives it, so its task shaping options have
# to be given; for a process without one, its whole _define_opts method
# runs again, in a subshell, which is costly, so a process whose number
# of tasks other processes need is written with an option generator when
# it can be, and a method asks once, keeping the answer in a variable. A
# number of tasks that depends on itself stops the preparation of the
# run. The number of tasks is usually read in a command substitution,
# whose failure has to stop the method that reads it.
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
# Gets the absolute path of the Python file of a process, given relative
# to the module that adds the process or as an absolute path, as the file
# of an external alias is.
#
# $1 - Path of the file.
# $2 - Process name.
# $3 - What the file is, for the messages.
#
# Prints the absolute path, or nothing, returning 1 with an error, if the
# file does not exist.
debasher::_resolve_py_func_file()
{
    local file=$1
    local processname=$2
    local description=$3

    if ! debasher::_resolve_path_relative_to_pfile_dir "${file}" "${DEBASHER_PROCESS_PFILE_DIR[${processname}]:-.}" "${description} of process ${processname}"; then
        echo "Error: the ${description} ${file} of process ${processname} does not exist" >&2
        return 1
    fi
}

########
# Public: Builds the array of the tasks of an array process from a
# Python file, which defines a function tasks(run) that returns the
# elements of the array. The function receives the command line of the
# run (run.value(label), run.given(label) and run.args, read as
# read_opt_value_from_line reads them), the name of the process
# (run.process) and its process output directory (run.outdir), and
# returns a list, or any other iterable, of strings, numbers or paths,
# each of which becomes an element. It replaces, in Python, the Bash
# that builds the array in the _define_opts method of the process,
# before the loop that defines the options of each task.
#
# $1 - Name of the array variable that receives the elements.
# $2 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $3 - Serialized command line (the cmdline argument of _define_opts).
# $4 - Process name.
# $5 - Process output directory.
#
# Examples
#
#   local array
#   debasher::tasks_from_file array "worker_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}" || return 1
#
# Returns 1, with an error, if the file does not exist or its function
# fails or returns something other than the elements of an array.
debasher::tasks_from_file()
{
    local -n tasks_from_file_ref=$1
    local file=$2
    local cmdline=$3
    local processname=$4
    local process_outdir=$5

    local path
    path=$(debasher::_resolve_py_func_file "${file}" "${processname}" "tasks file") || return 1

    # The elements are separated by NUL characters, which a command
    # substitution would drop, so they are read from a file
    local elems_file
    elems_file=$("${MKTEMP}") || return 1
    debasher::_deserialize_args "${cmdline}"
    if ! "${debasher_libexecdir}/debasher_run_py_func" array "${path}" "${processname}" "${process_outdir}" \
         -- "${DEBASHER_DESERIALIZED_ARGS[@]}" > "${elems_file}"; then
        "${RM}" -f "${elems_file}"
        return 1
    fi

    tasks_from_file_ref=()
    local elem
    while IFS= read -r -d '' elem; do
        tasks_from_file_ref+=("${elem}")
    done < "${elems_file}"
    "${RM}" -f "${elems_file}"
}

########
# Public: Builds the array of the tasks of an array process from a
# Python file, which defines a function tasks(run) that returns the
# elements of the array. The function receives the command line of the
# run (run.value(label), run.given(label) and run.args, read as
# read_opt_value_from_line reads them), the name of the process
# (run.process) and its process output directory (run.outdir), and
# returns a list, or any other iterable, of strings, numbers or paths,
# each of which becomes an element. It replaces, in Python, the Bash
# that builds the array in the _define_opts method of the process,
# before the loop that defines the options of each task.
#
# $1 - Name of the array variable that receives the elements.
# $2 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $3 - Serialized command line (the cmdline argument of _define_opts).
# $4 - Process name.
# $5 - Process output directory.
#
# Examples
#
#   local array
#   tasks_from_file array "worker_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}" || return 1
#
# Returns 1, with an error, if the file does not exist or its function
# fails or returns something other than the elements of an array.
tasks_from_file() { debasher::tasks_from_file "$@"; }

########
# Public: Prints the number of tasks of an option generator from a
# Python file, which defines a function tasks(run) that returns it. The
# function receives what it receives for an array process (see
# tasks_from_file) and returns an integer, 0 or more. It replaces, in
# Python, the body of the _generate_opts_size method of the process.
#
# $1 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $2 - Serialized command line (the cmdline argument of
#      _generate_opts_size).
# $3 - Process name.
# $4 - Process output directory.
#
# Examples
#
#   debasher::num_tasks_from_file "worker_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}"
#
# The function prints the number of tasks, or nothing, returning 1 with
# an error, if the file does not exist or its function fails or returns
# something other than a number of tasks.
debasher::num_tasks_from_file()
{
    local file=$1
    local cmdline=$2
    local processname=$3
    local process_outdir=$4

    local path
    path=$(debasher::_resolve_py_func_file "${file}" "${processname}" "tasks file") || return 1

    debasher::_deserialize_args "${cmdline}"
    "${debasher_libexecdir}/debasher_run_py_func" count "${path}" "${processname}" "${process_outdir}" \
        -- "${DEBASHER_DESERIALIZED_ARGS[@]}" || return 1
}

########
# Public: Prints the number of tasks of an option generator from a
# Python file, which defines a function tasks(run) that returns it. The
# function receives what it receives for an array process (see
# tasks_from_file) and returns an integer, 0 or more. It replaces, in
# Python, the body of the _generate_opts_size method of the process.
#
# $1 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $2 - Serialized command line (the cmdline argument of
#      _generate_opts_size).
# $3 - Process name.
# $4 - Process output directory.
#
# Examples
#
#   num_tasks_from_file "worker_tasks.py" "${cmdline}" "${process_name}" "${process_outdir}"
#
# The function prints the number of tasks, or nothing, returning 1 with
# an error, if the file does not exist or its function fails or returns
# something other than a number of tasks.
num_tasks_from_file() { debasher::num_tasks_from_file "$@"; }

########
# Public: Decides whether a task is skipped from a Python file, which
# defines a function skip(task) that returns True to skip the task and
# False to run it. The function receives the options of the task
# (task.value(label), task.given(label) and task.args, read as
# read_opt_value_from_func_args reads them) and the name of the process
# (task.process). It is the skip method of a process in Python, called
# by the task with its options, before its process output directory is
# reset.
#
# $1 - Process name.
# $2 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $3,$4,...,$n - Options of the task (the arguments of the skip method).
#
# Examples
#
#   worker_skip() { debasher::skip_from_file "worker" "worker_skip.py" "$@"; }
#
# Returns 0 if the task is skipped, 1 if it runs, and 2, with an error,
# if the file does not exist or its function fails or returns something
# other than True or False, which fails the task.
debasher::skip_from_file()
{
    local processname=$1
    local file=$2
    shift 2

    local path
    path=$(debasher::_resolve_py_func_file "${file}" "${processname}" "skip file") || return 2

    local skip_status=0
    "${debasher_libexecdir}/debasher_run_py_func" skip "${path}" "${processname}" -- "$@" || skip_status=$?
    return ${skip_status}
}

########
# Public: Decides whether a task is skipped from a Python file, which
# defines a function skip(task) that returns True to skip the task and
# False to run it. The function receives the options of the task
# (task.value(label), task.given(label) and task.args, read as
# read_opt_value_from_func_args reads them) and the name of the process
# (task.process). It is the skip method of a process in Python, called
# by the task with its options, before its process output directory is
# reset.
#
# $1 - Process name.
# $2 - Path of the Python file, relative to the module that adds the
#      process, or absolute.
# $3,$4,...,$n - Options of the task (the arguments of the skip method).
#
# Examples
#
#   worker_skip() { skip_from_file "worker" "worker_skip.py" "$@"; }
#
# Returns 0 if the task is skipped, 1 if it runs, and 2, with an error,
# if the file does not exist or its function fails or returns something
# other than True or False, which fails the task.
skip_from_file() { debasher::skip_from_file "$@"; }

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
# Defines process option whose value is a path, resolving it relative
# to the directory of the .sh that defines the process if it's relative
# (or verifying it as an absolute path otherwise): same resolution
# debasher::_add_debasher_ext_alias_process uses for an external alias
# script, so a "file" or "dir" option's value can likewise point at
# something shipped alongside the program (e.g. via the webui's
# program-files browser) using a portable, relative path.
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
# $2 - Path associated to the option being defined (relative or
#      absolute).
# $3 - Name of variable that will store the information about the option to be added.
# $4 - Name of the process this option is being defined for.
# $5 - Kind of path: "file" or "dir".
debasher::_define_path_opt()
{
    local opt=$1
    local value=$2
    local varname=$3
    local process_name=$4
    local kind=$5
    local pfile_dir="${DEBASHER_PROCESS_PFILE_DIR[${process_name}]}"

    local resolved
    if ! resolved=$(debasher::_resolve_path_relative_to_pfile_dir "${value}" "${pfile_dir}" "value for option ${opt}" "${kind}"); then
        debasher::errmsg "$(debasher::_path_kind_noun "${kind}") ${value} does not exist (${opt} option)"
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
#   debasher::define_infile_opt "-f" "config/settings.txt" "optlist" "${process_name}"
#
# The function does not return any value
debasher::define_infile_opt()
{
    debasher::_define_path_opt "$1" "$2" "$3" "$4" file
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
# Public: Defines process option whose value is a directory path,
# resolved relative to the .sh defining the process.
#
# $1 - Option name.
# $2 - Directory path associated to the option being defined (relative
#      or absolute).
# $3 - Name of variable that will store the information about the option to be added.
# $4 - Name of the process this option is being defined for.
#
# Examples
#
#   debasher::define_indir_opt "-d" "reference" "optlist" "${process_name}"
#
# The function does not return any value
debasher::define_indir_opt()
{
    debasher::_define_path_opt "$1" "$2" "$3" "$4" dir
}

########
# Public: Defines process option whose value is a directory path,
# resolved relative to the .sh defining the process.
#
# $1 - Option name.
# $2 - Directory path associated to the option being defined (relative
#      or absolute).
# $3 - Name of variable that will store the information about the option to be added.
# $4 - Name of the process this option is being defined for.
#
# Examples
#
#   define_indir_opt "-d" "reference" "optlist" "${process_name}"
#
# The function does not return any value
define_indir_opt() { debasher::define_indir_opt "$@"; }

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
