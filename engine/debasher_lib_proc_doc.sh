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

###########################################
# PROCESS DOCUMENTATION-RELATED FUNCTIONS #
###########################################

########
debasher::document_process()
{
    local desc=$1
    echo $desc
}

document_process() { debasher::document_process "$@"; }

########
# Prints the options that a process declares, either those that its
# tasks receive or its task shaping options.
#
# $1 - Process name.
# $2 - 1 to print the task shaping options, 0 (the default) to print
#      the others.
debasher::_show_proc_opts()
{
    local processname=$1
    local task_shaping=${2:-0}

    # Iterate over processname plut options
    local key
    for key in ${!DEBASHER_PROGRAM_OPT_TYPE[@]}; do
        local processname
        local opt
        local flags=""
        local paren_flags=""
        curr_proc_name="${key%%"${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"*}"
        opt="${key#*"${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"}"
        local key_is_task_shaping=0
        if [ "${DEBASHER_PROGRAM_OPT_IS_TASK_SHAPING[${key}]}" = 1 ]; then
            key_is_task_shaping=1
        fi
        if [ "${processname}" = "${curr_proc_name}" ] && [ "${key_is_task_shaping}" -eq "${task_shaping}" ]; then
            if [ "${DEBASHER_PROGRAM_OPT_IS_CMDLINE[${key}]}" = 1 ] || [ "${key_is_task_shaping}" -eq 1 ]; then
                flags+="${flags:+,}command-line"
            fi

            if [ "${DEBASHER_PROGRAM_OPT_IS_MANDATORY[${key}]}" = 1 ]; then
                flags+="${flags:+,}mandatory"
            fi

            if [ -n "${flags}" ]; then
                paren_flags="(${flags})"
            fi

            # Print option
            if [ -z ${DEBASHER_PROGRAM_OPT_TYPE[$key]} ]; then
                echo "- \`${opt}\` ${DEBASHER_PROGRAM_OPT_DESC[$key]} ${paren_flags}"
            else
                echo "- \`${opt}\` ${DEBASHER_PROGRAM_OPT_TYPE[$key]} ${DEBASHER_PROGRAM_OPT_DESC[$key]} ${paren_flags}"
            fi
        fi
    done
}

########
# processname's short method name for method suffix $2 (an entry of
# DEBASHER_PROCESS_METHODS, e.g. "_reset_outfiles") -- just that suffix
# with its leading DEBASHER_PROCESS_METHOD_SEP stripped, except "exec"
# itself, whose suffix is the empty string.
debasher::_proc_method_label()
{
    local method_suffix=$1

    local label=${method_suffix#"${DEBASHER_PROCESS_METHOD_SEP}"}
    if [ -z "${label}" ]; then
        echo "exec"
    else
        echo "${label}"
    fi
}

########
debasher::_show_proc_methods()
{
    local processname=$1
    local show_code=$2

    local i
    for i in "${!DEBASHER_PROCESS_METHODS[@]}"; do
        if debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHODS[$i]}" >/dev/null; then
            local proc_func=$(debasher::_get_process_funcname "${processname}" "${DEBASHER_PROCESS_METHODS[$i]}")
            echo "- \`${proc_func}\`"
        fi
    done

    if [ "${show_code}" = 1 ]; then
        for i in "${!DEBASHER_PROCESS_METHODS[@]}"; do
            if debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHODS[$i]}" >/dev/null; then
                local proc_func=$(debasher::_get_process_funcname "${processname}" "${DEBASHER_PROCESS_METHODS[$i]}")
                echo ""
                echo "#### $(debasher::_proc_method_label "${DEBASHER_PROCESS_METHODS[$i]}")"
                echo ""
                echo '```'bash
                declare -f "${proc_func}"
                echo '```'
            fi
        done
    fi
}

########
debasher::_show_proc_vars()
{
    local processname=$1
    local show_values=$2

    local i
    for i in "${!DEBASHER_PROCESS_VARNAMES[@]}"; do
        local proc_varname=$(debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAMES[$i]}")
        if [ "${proc_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
            echo "- \`${proc_varname}\`"
        fi
    done

    if [ "${show_values}" = 1 ]; then
        for i in "${!DEBASHER_PROCESS_VARNAMES[@]}"; do
            local proc_varname=$(debasher::_search_process_var "${processname}" "${DEBASHER_PROCESS_VARNAMES[$i]}")
            if [ "${proc_varname}" != "${DEBASHER_VAR_NOT_FOUND}" ]; then
                echo ""
                echo "#### ${DEBASHER_HEREDOC_LANGUAGES[$i]}"
                echo ""
                echo '```'"${DEBASHER_HEREDOC_LANGUAGES[$i]}"
                echo "${!proc_varname}"
                echo '```'
            fi
        done
    fi
}

########
debasher::_show_proc_opt_handler()
{
    local processname=$1

    # Search for process option handler functions
    local func_found=0
    for method in $DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS $DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPT_DEPS \
                  $DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE $DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS; do
        if debasher::_search_process_func "${processname}" "${method}" >/dev/null; then
            local funcname=$(debasher::_search_process_func "${processname}" "${method}")
            echo '```'bash
            declare -f "${funcname}"
            echo '```'
            func_found=1
        fi
    done

    if [ "${func_found}" -eq 1 ]; then
        return 0
    else
        return 1
    fi
}

########
debasher::_show_proc_specs()
{
    local processname=$1

    # The specification of a process, or else that of a sequential
    # process
    local process_spec="${DEBASHER_INITIAL_PROCESS_SPEC[${processname}]-${DEBASHER_SEQ_PROCESS_SPEC[${processname}]-}}"

    echo "### Computational Specifications"
    local cpus=$(debasher::_extract_cpus_from_process_spec "${process_spec}")
    [ "${cpus}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`cpus\`: ${cpus}"
    local mem=$(debasher::_extract_mem_from_process_spec "${process_spec}")
    [ "${mem}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`mem\`: ${mem}"
    local time=$(debasher::_extract_time_from_process_spec "${process_spec}")
    [ "${time}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`time\`: ${time}"
    local nodes=$(debasher::_extract_nodes_from_process_spec "${process_spec}")
    [ "${nodes}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`nodes\`: ${nodes}"
    local account=$(debasher::_extract_account_from_process_spec "${process_spec}")
    [ "${account}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`account\`: ${account}"
    local partition=$(debasher::_extract_partition_from_process_spec "${process_spec}")
    [ "${partition}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`partition\`: ${partition}"
    local throttle=$(debasher::_extract_throttle_from_process_spec "${process_spec}")
    [ "${throttle}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`throttle\`: ${throttle}"
    # Those that the nodes of a resident program read, when the process gives
    # them
    local comp_specs=$(debasher::extract_process_comp_specs "${process_spec}")
    local specname value
    for specname in ${DEBASHER_RESIDENT_COMP_SPEC_NAMES} ${DEBASHER_BATCH_SCHED_COMP_SPEC_NAME}; do
        value=$(debasher::extract_attr_from_process_comp_specs "${comp_specs}" "${specname}")
        [ "${value}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`${specname}\`: ${value}"
    done
    echo ""

    echo "### Additional Specifications"
    local force=$(debasher::_extract_force_from_process_spec "${process_spec}")
    [ "${force}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`force\`: ${force}"
    local processdeps=$(debasher::_extract_processdeps_from_process_spec "${process_spec}")
    [ "${processdeps}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`processdeps\`: ${processdeps}"
    local alias=$(debasher::_extract_alias_from_process_spec "${process_spec}")
    [ "${alias}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`alias\`: ${alias}"
    local alias_opt_map=$(debasher::_extract_alias_opt_map_from_process_spec "${process_spec}")
    [ "${alias_opt_map}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`alias_opt_map\`: ${alias_opt_map}"
    local ext_alias=$(debasher::_extract_ext_alias_from_process_spec "${process_spec}")
    [ "${ext_alias}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`ext_alias\`: ${ext_alias}"
    local sched=$(debasher::_extract_sched_from_process_spec "${process_spec}")
    [ "${sched}" != "${DEBASHER_ATTR_NOT_FOUND}" ] && echo "- \`sched\`: ${sched}"
}

########
# debasher::_collect_func_deps helper: blanks out string-literal text
# that bash's own grammar guarantees can never contain a command
# invocation, so a later plain word-grep over the result doesn't
# mistake prose (or another language's syntax) for a call -- e.g.
# debasher_dynamic_fanout.sh's aggregate(), whose `echo "Warning: no
# count files found..."` would otherwise pull the unrelated "count"
# process in as a bogus dependency purely because that English word
# appears in the message; or count_chars()'s own embedded awk script
# (`awk '... count[c]++ ...'`), whose "count" array name would
# otherwise do the same to count_chars's own dependents (worker, via
# worker_task) despite the process "count" never actually being called.
#
# Handles two shapes: a single-quoted span (`'...'`, wholesale -- bash
# never expands anything inside single quotes, so its content is never
# code) and a double-quoted span with no "$" in it at all (a
# `$(...)`/`${...}` substitution can genuinely contain a real call, so
# any double-quoted span containing one is left untouched rather than
# risk dropping a real dependency). Processes the whole input as one
# blob rather than line by line -- declare -f reprints a function's
# body with real embedded newlines wherever the original source had
# them (e.g. inside a multi-line single-quoted awk/perl script), so a
# quoted span's opening and closing quote routinely land on different
# lines. Doesn't attempt to handle escaped quotes inside a string
# (`\"`, `$'...'`) -- not a style this package's own scripts use.
debasher::_blank_string_literals()
{
    awk -v sq="'" -v dq='"' '
        { text = text $0 "\n" }
        END {
            state = 0   # 0 = normal, 1 = single-quoted, 2 = double-quoted
            span = ""
            sawdollar = 0
            n = length(text)
            for (i = 1; i <= n; i++) {
                c = substr(text, i, 1)
                if (state == 0) {
                    if (c == sq) { state = 1 }
                    else if (c == dq) { state = 2; span = ""; sawdollar = 0 }
                    else { out = out c }
                } else if (state == 1) {
                    if (c == sq) { state = 0 }
                } else {
                    if (c == dq) {
                        state = 0
                        if (sawdollar) out = out dq span dq
                    } else {
                        if (c == "$") sawdollar = 1
                        span = span c
                    }
                }
            }
            printf "%s", out
        }
    '
}

########
# debasher::_collect_func_deps helper: prints, one per line, every name
# $1's body declares as a local/declare/typeset variable -- i.e. names
# that appear in that role purely as identifiers, never as an actual
# command word, even though a plain word-grep of the body can't tell
# the two apart (see debasher::_collect_func_deps for why that
# matters). Only the declared name itself is printed, not whatever
# follows an "=" on the same word (a "local x=$(some_func ...)"'s own
# "some_func" is a real call, and stays a candidate).
debasher::_declared_func_vars()
{
    local funcname=$1

    declare -f "${funcname}" \
        | debasher::_blank_string_literals \
        | grep -oE '(^|;)[[:space:]]*(local|declare|typeset)[[:space:]]+[^;]*' \
        | sed -E 's/^[;[:space:]]*(local|declare|typeset)[[:space:]]+//' \
        | tr -s '[:space:]' '\n' \
        | sed -E 's/=.*$//' \
        | grep -E '^[A-Za-z_][A-Za-z0-9_]*$'
}

########
# Recursively collects, into the "seen" associative array (passed by
# name in $3), every function reachable from $1's body that is itself
# defined in the same script file ($2) as $1 -- i.e. a helper the
# process author wrote, as opposed to a function belonging to the
# DeBasher framework itself (defined in a different file) or an
# external command. Relies on "shopt -s extdebug" already being active
# in the caller, since that is what makes "declare -F" report a
# function's defining file instead of just its name.
#
# Candidate names are every identifier-shaped word in $1's body -- a
# plain grep, blind to whether a given occurrence is actually a command
# word or just an argument/variable name -- other than ones
# debasher::_declared_func_vars finds declared as a local variable
# somewhere in that same body (e.g. debasher_dynamic_fanout.sh's
# fragment(), which has "local ... count ..." and later "count=$((...
# ))" purely as a loop counter that happens to collide with an
# unrelated sibling process named "count": without this exclusion, the
# mere presence of that identifier would pull "count" -- and
# transitively whatever it calls -- in as a bogus dependency of
# fragment. This can still be fooled the other way (a local variable
# deliberately shadowing a function of the same name that the body
# really does go on to call), but that isn't a style this package, or
# the frontend's own code editor, ever produces.
debasher::_collect_func_deps()
{
    local funcname=$1
    local scriptfile=$2
    # Kept as a plain string, and passed through unchanged on the
    # recursive call below, rather than re-using the nameref alias
    # itself -- a nameref that recursively aliases a variable of its
    # own name triggers bash's "circular name reference" and silently
    # stops propagating writes to the caller's array.
    local collected_name=$3
    local -n _collected=$3

    [ -n "${_collected[$funcname]+x}" ] && return 0
    _collected[$funcname]=1

    local -A declared_vars=()
    local declared_var
    while IFS= read -r declared_var; do
        [ -n "${declared_var}" ] && declared_vars[${declared_var}]=1
    done < <(debasher::_declared_func_vars "${funcname}")

    local word
    for word in $(declare -f "${funcname}" | debasher::_blank_string_literals | grep -oE '[A-Za-z_][A-Za-z0-9_]*' | sort -u); do
        [ -n "${_collected[$word]+x}" ] && continue
        [ -n "${declared_vars[$word]+x}" ] && continue
        # A sequential process that the function runs as a step has
        # code of its own, documented apart from that of the process
        [ -n "${DEBASHER_SEQ_PROCESSES[$word]+x}" ] && continue
        local defsite
        defsite=$(declare -F "${word}" 2>/dev/null)
        [ -z "${defsite}" ] && continue
        [ "${defsite##* }" = "${scriptfile}" ] && debasher::_collect_func_deps "${word}" "${scriptfile}" "${collected_name}"
    done
}

########
# debasher::_show_proc_implem helper: prints the real implementation
# behind an alias/ext_alias process instead of the synthesized
# dispatcher function debasher::_create_process_func_alias/_ext_alias
# creates for it (see engine/debasher_lib_programs.sh) -- recursing into
# the alias target's own implementation (chaining through further
# aliases, if any), or reading the ext_alias's external file directly.
# Only known once add_debasher_process has actually run for this
# process (i.e. only from debasher_doc_mod, not debasher_get_proc_info,
# which never runs the program's "_program" function). Returns 1 for
# anything else (regular/heredoc process, or a process
# add_debasher_process hasn't registered at all), leaving
# debasher::_show_proc_implem to try its other sources.
debasher::_show_proc_implem_delegate()
{
    local processname=$1

    # The type of a process, or else that of a sequential process
    case "${DEBASHER_PROGRAM_PROCESSES[${processname}]-${DEBASHER_SEQ_PROCESSES[${processname}]-}}" in
        "${DEBASHER_ALIAS_PROCESS_TYPE}")
            debasher::_show_proc_implem "${DEBASHER_PROCESS_ALIAS_TARGETS[${processname}]}"
            return $?
            ;;
        "${DEBASHER_EXT_ALIAS_PROCESS_TYPE}")
            local ext_alias_file="${DEBASHER_PROCESS_EXT_ALIAS_FILES[${processname}]}"
            local doc_language
            doc_language=$(debasher::_get_doc_language_for_file "${ext_alias_file}") || doc_language="bash"
            echo '```'"${doc_language}"
            cat "${ext_alias_file}"
            echo '```'
            return 0
            ;;
    esac

    return 1
}

########
# debasher::_show_proc_implem helper: prints the source of processname's
# heredoc as a fenced code block tagged with its language, whichever form
# provides it: the function "<processname>_heredoc_<py|r|perl|groovy>",
# which prints it, or the legacy variable "<processname>_<py|r|perl|groovy>",
# which holds it (see debasher::_search_heredoc_provider, which prefers
# the function, as the engine does when it runs the process). Returns 1
# if the process has neither.
debasher::_show_proc_implem_heredoc()
{
    local processname=$1

    local i provider_info provider kind
    for i in "${!DEBASHER_PROCESS_VARNAMES[@]}"; do
        provider_info=$(debasher::_search_heredoc_provider "${processname}" "${DEBASHER_PROCESS_FUNCNAMES[$i]}" "${DEBASHER_PROCESS_VARNAMES[$i]}") || continue
        read -r provider kind <<< "${provider_info}"
        echo '```'${DEBASHER_HEREDOC_LANGUAGES[$i]}
        if [ "${kind}" = "func" ]; then
            "${provider}"
        else
            echo "${!provider}"
        fi
        echo '```'
        return 0
    done

    return 1
}

########
# debasher::_show_proc_implem helper: prints processname's bash-function
# implementation (its exec function, plus any same-file helper functions
# it calls -- see debasher::_collect_func_deps) as a fenced ```bash
# block. Returns 1 if no such function exists.
debasher::_show_proc_implem_bash_func()
{
    local processname=$1

    if ! debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXEC}" >/dev/null; then
        return 1
    fi

    local funcname=$(debasher::_search_process_func "${processname}" "${DEBASHER_PROCESS_METHOD_NAME_EXEC}")

    # Pull in any helper functions the process author defined alongside
    # it in the same script file -- otherwise the implementation
    # captured here would call functions that don't exist anywhere else
    # in what gets shown/imported.
    shopt -s extdebug
    local scriptfile
    scriptfile=$(declare -F "${funcname}")
    scriptfile=${scriptfile##* }

    local -A seen=()
    debasher::_collect_func_deps "${funcname}" "${scriptfile}" seen
    shopt -u extdebug

    echo '```'bash
    local dep
    for dep in "${!seen[@]}"; do
        if [ "${dep}" != "${funcname}" ]; then
            declare -f "${dep}"
            echo ""
        fi
    done
    declare -f "${funcname}"
    echo '```'
}

########
# Prints processname's implementation as a fenced Markdown code block.
# Tries, in order, debasher::_show_proc_implem_delegate (an alias/
# ext_alias process), _heredoc (a heredoc-variable process), then
# _bash_func (a plain bash function) -- the same precedence
# debasher::add_debasher_process itself gives them when registering a
# process. Returns 1 if none of them find anything.
debasher::_show_proc_implem()
{
    local processname=$1

    debasher::_show_proc_implem_delegate "${processname}" && return 0
    debasher::_show_proc_implem_heredoc "${processname}" && return 0
    debasher::_show_proc_implem_bash_func "${processname}" && return 0

    return 1
}

########
debasher::_show_process_documentation()
{
    local processname=$1
    local show_methods=$2
    local show_methods_with_code=$3
    local show_varnames=$4
    local show_varnames_with_values=$5
    local show_options=$6
    local show_opt_handler=$7
    local show_implem=$8
    local show_specs=$9

    # Print header
    echo "## ${processname}"
    echo ""

    # Print body
    echo "### Description"
    local document_funcname=$(debasher::_get_proc_document_funcname "${processname}")
    if [ "${document_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        echo "Warning: function to document process was not found" >&2
        echo ""
    else
        ${document_funcname}
        echo ""
    fi

    if [ "${show_methods}" = 1 ] || [ "${show_methods_with_code}" = 1 ]; then
        echo "### Process Methods"
        debasher::_show_proc_methods "${processname}" "${show_methods_with_code}"
        echo ""
    fi

    if [ "${show_varnames}" = 1 ] || [ "${show_varnames_with_values}" = 1 ]; then
        echo "### Process Variables"
        debasher::_show_proc_vars "${processname}" "${show_varnames_with_values}"
        echo ""
    fi

    if [ "${show_options}" = 1 ]; then
        echo "### Process Options"
        local opts_funcname
        local identify_cmdline_opt_funcname
        opts_funcname=$(debasher::_get_explain_cmdline_opts_funcname ${processname})
        if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            opts_funcname=$(debasher::_get_explain_opts_funcname ${processname})
            if [ "${opts_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                echo "Warning: function to explain options for process ${processname} was not found" >&2
            else
                identify_cmdline_opt_funcname=$(debasher::_get_identify_cmdline_opts_funcname ${processname})
                if [ "${identify_cmdline_opt_funcname}" = ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                    identify_cmdline_opt_funcname=""
                fi
            fi
        fi

        if [ "${opts_funcname}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            ${opts_funcname}
            if [ "${identify_cmdline_opt_funcname}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
                ${identify_cmdline_opt_funcname}
            fi
            debasher::_show_proc_opts "${processname}"
        fi
        echo ""

        # Task shaping options get a section of their own, only for a
        # process that declares them, since the process function never
        # receives them
        local task_shaping_opts_funcname=$(debasher::_get_explain_task_shaping_opts_funcname "${processname}")
        if [ "${task_shaping_opts_funcname}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
            echo "### Task Shaping Options"
            echo "Read only to define the tasks of the process; the process function does not receive them."
            ${task_shaping_opts_funcname}
            debasher::_show_proc_opts "${processname}" 1
            echo ""
        fi
    fi

    if [ "${show_opt_handler}" = 1 ]; then
        echo "### Process Option Handler"
        local opt_handler
        opt_handler=$(debasher::_show_proc_opt_handler "${processname}")
        if [ $? -eq 0 ]; then
            echo "${opt_handler}"
        else
            echo "Warning: option handler for process ${processname} was not found" >&2
        fi
        echo ""
    fi

    if [ "${show_specs}" = 1 ]; then
        debasher::_show_proc_specs "${processname}"
        echo ""
    fi

    if [ "${show_implem}" = 1 ]; then
        echo "### Process Implementation"
        local implementation
        implementation=$(debasher::_show_proc_implem "${processname}")
        if [ $? -eq 0 ]; then
            echo "${implementation}"
        else
            echo "Warning: implementation for process ${processname} was not found" >&2
        fi
        echo ""
    fi
}

########
# Prints the documentation of a sequential process (see
# debasher::add_debasher_seq_process), under a heading of its own that
# tells it apart from that of a process: its description, when it has a
# _document method, and, as requested, its specifications and its
# implementation. A sequential process has no options, option handler
# or other methods to show.
#
# $1 - Name of the sequential process.
# $2 - 1 to show its implementation.
# $3 - 1 to show its specifications.
debasher::_show_seq_process_documentation()
{
    local processname=$1
    local show_implem=$2
    local show_specs=$3

    echo "## ${DEBASHER_SEQ_PROCESS_DOC_HEADING_PREFIX}${processname}"
    echo ""

    echo "### Description"
    local document_funcname=$(debasher::_get_proc_document_funcname "${processname}")
    if [ "${document_funcname}" != ${DEBASHER_FUNCT_NOT_FOUND} ]; then
        ${document_funcname}
    fi
    echo ""

    if [ "${show_specs}" = 1 ]; then
        debasher::_show_proc_specs "${processname}"
        echo ""
    fi

    if [ "${show_implem}" = 1 ]; then
        echo "### Process Implementation"
        local implementation
        implementation=$(debasher::_show_proc_implem "${processname}")
        if [ $? -eq 0 ]; then
            echo "${implementation}"
        else
            echo "Warning: implementation for sequential process ${processname} was not found" >&2
        fi
        echo ""
    fi
}
