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

###################################################
# OUTPUT DIRECTORY AND FIFO PREPARATION FUNCTIONS #
###################################################

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
        # Record the use, checked once the shared directories are known
        # (see debasher::_check_shared_dirs_declared)
        DEBASHER_PROGRAM_SHDIR_USES["${shdirname}"]=${opt}
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
# Fails when an option names, with define_opt_from_shared_dir and without
# a shared subdirectory, a shared directory that no module declares,
# whose path would never be created. A shared subdirectory is checked
# alike by debasher::_prepare_shared_subdirs.
#
# Must be called once the shared directories of the modules are
# registered.
debasher::_check_shared_dirs_declared()
{
    local shdirname
    for shdirname in "${!DEBASHER_PROGRAM_SHDIR_USES[@]}"; do
        if [[ ! -v DEBASHER_PROGRAM_SHDIRS["${shdirname}"] ]]; then
            echo "Error: option ${DEBASHER_PROGRAM_SHDIR_USES["${shdirname}"]} asks for the shared directory ${shdirname}, which no module declares as a shared directory" >&2
            return 1
        fi
    done
}

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
# Fails when a path below the directory $1 that an output option of the
# run names goes through a symbolic link on the way to it, so that the
# pruning of $1, which takes such a link for an entry to remove, never
# meets one. The path itself may be a link, which the pruning keeps whole.
# $2 names the directory for the message.
debasher::_check_output_named_paths_have_no_link()
{
    local absroot=$1
    local what=$2

    local -A named=()
    debasher::_add_output_named_paths "${absroot}" named

    local relpath
    for relpath in "${!named[@]}"; do
        [[ "${relpath}" == */* ]] || continue
        debasher::_check_subpath_has_no_link "${absroot}" "${relpath%/*}" "the path ${relpath} that an output option names in ${what}" || return 1
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
# Adds to the associative array named $1, as keys, the shared directories
# for which some option of the run asks for a shared subdirectory: the
# subdivided shared directories. Fails when one of them is not declared by
# any module.
debasher::_collect_subdivided_shdirs()
{
    local -n subdivided_ref=$1

    local relpath
    for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
        local shdirname=${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}
        if [[ ! -v DEBASHER_PROGRAM_SHDIRS["${shdirname}"] ]]; then
            echo "Error: an option asks for the shared subdirectory ${relpath} of ${shdirname}, which no module declares as a shared directory" >&2
            return 1
        fi
        subdivided_ref["${shdirname}"]=1
    done
}

########
# Creates every shared subdirectory that the options of the run ask for,
# refusing one whose subpath goes through a symbolic link. When $1 is 1,
# the subpaths are only checked.
debasher::_create_shared_subdirs()
{
    local only_report=$1

    local relpath
    for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
        local shdirname=${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}
        local absdir=$(debasher::get_absolute_shdirname "${shdirname}")
        local subpath=${relpath#"${shdirname}/"}
        debasher::_check_subpath_has_no_link "${absdir}" "${subpath}" "the shared subdirectory ${relpath}" || return 1
        if [ "${only_report}" -ne 1 ]; then
            "${MKDIR}" -p "${absdir}/${subpath}" || { echo "Error: cannot create the shared subdirectory ${relpath}" >&2; return 1; }
        fi
    done
}

########
# Removes from the subdivided shared directory $2 each entry that is
# neither one of its shared subdirectories, nor a path that an output
# option of the run names, nor a directory on the way to one of them.
# When $1 is 1, the entries are only named.
debasher::_prune_subdivided_shdir()
{
    local only_report=$1
    local shdirname=$2

    local absdir=$(debasher::get_absolute_shdirname "${shdirname}")
    [ -d "${absdir}" ] || return 0

    # What the shared directory keeps: its shared subdirectories and the
    # paths that output options name, relative to it
    local -A kept=()
    local -A ways=()
    local relpath
    for relpath in "${!DEBASHER_PROGRAM_SHSUBDIRS[@]}"; do
        [ "${DEBASHER_PROGRAM_SHSUBDIRS["${relpath}"]}" = "${shdirname}" ] && kept["${relpath#"${shdirname}/"}"]=1
    done
    debasher::_add_output_named_paths "${absdir}" kept
    debasher::_add_ways_to_paths kept ways

    debasher::_prune_subdivided_dir "${only_report}" "the shared directory ${shdirname}" "" "${absdir}" kept ways
}

########
# Prepares the shared subdirectories that the options of the run ask
# for (see debasher::define_opt_from_shared_dir): refuses an output
# option that holds a subdivided shared directory, checks that no process
# that the program no longer has is still running, refuses a path that an
# output option names in a subdivided shared directory through a symbolic
# link on the way to it, creates every shared subdirectory, and removes
# from every subdivided shared directory each entry that is neither a
# shared subdirectory of the run, nor a path that an output option of the
# run names, nor a directory on the way to one of them. When $1 is 1, as
# in a validation, nothing is created or removed, and the entries that a
# run would remove are only named.
#
# Must be called once the options of every process are defined and the
# shared directories created.
debasher::_prepare_shared_subdirs()
{
    local only_report=$1

    [ ${#DEBASHER_PROGRAM_SHSUBDIRS[@]} -eq 0 ] && return 0

    local -A subdivided=()
    debasher::_collect_subdivided_shdirs subdivided || return 1

    debasher::_check_no_output_opt_holds_subdivided_shdir subdivided || return 1
    if [ "${only_report}" -ne 1 ]; then
        debasher::_check_left_processes_not_running || return 1
    fi

    local shdirname
    for shdirname in "${!subdivided[@]}"; do
        debasher::_check_output_named_paths_have_no_link "$(debasher::get_absolute_shdirname "${shdirname}")" "the shared directory ${shdirname}" || return 1
    done

    debasher::_create_shared_subdirs "${only_report}" || return 1

    for shdirname in "${!subdivided[@]}"; do
        debasher::_prune_subdivided_shdir "${only_report}" "${shdirname}" || return 1
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
#      directory on the way to one of them is removed from it.
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
# Fills the associative array named $2 with the task subdirectories of the
# process $1, each with the index of the task that asks for it. Fails when
# two tasks ask for the same one.
debasher::_collect_task_subdir_owners()
{
    local processname=$1
    local -n owner_ref=$2

    local task_idx subpath
    while IFS=$'\t' read -r task_idx subpath; do
        if [[ -v owner_ref["${subpath}"] ]] && [ "${owner_ref["${subpath}"]}" != "${task_idx}" ]; then
            echo "Error: tasks ${owner_ref["${subpath}"]} and ${task_idx} of process ${processname} ask for the same task subdirectory ${subpath}" >&2
            return 1
        fi
        owner_ref["${subpath}"]=${task_idx}
    done < <(debasher::_list_task_subdirs_of_process "${processname}")
}

########
# Fails when a task subdirectory of the process $1, a key of the
# associative array named $2, is below another one of them, since each one
# is emptied on its own.
debasher::_check_task_subdirs_not_nested()
{
    local processname=$1
    local -n nested_owner_ref=$2

    local subpath
    for subpath in "${!nested_owner_ref[@]}"; do
        local parent=${subpath}
        while [[ "${parent}" == */* ]]; do
            parent=${parent%/*}
            if [[ -v nested_owner_ref["${parent}"] ]]; then
                echo "Error: the task subdirectory ${subpath} of process ${processname} is below another one, ${parent}" >&2
                return 1
            fi
        done
    done
}

########
# Fails when an output option holds the path of the output directory of
# the process $1, which has task subdirectories, since it would name the
# whole directory as something that a task produces.
debasher::_check_no_output_opt_holds_process_outdir()
{
    local processname=$1

    local outd=$(debasher::_get_process_outdir "${processname}")
    local value
    for value in "${outd}" "${outd}/"; do
        if [[ -v DEBASHER_OUT_VALUE_TO_PROCESSES["${value}"] ]]; then
            echo "Error: an output option holds the output directory of process ${processname}, which has task subdirectories; a task writes only into its own task subdirectories (define_opt_from_process_outdir --subdir)" >&2
            return 1
        fi
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
        debasher::_collect_task_subdir_owners "${processname}" owner || return 1
        debasher::_check_task_subdirs_not_nested "${processname}" owner || return 1
        debasher::_check_no_output_opt_holds_process_outdir "${processname}" || return 1
    done
}

########
# Prepares the task subdirectories of the process $2 in the output
# directory $1, when the process is prepared: unless the process has a
# _reset_outfiles method or belongs to a resident program, removes from
# its subdivided process output directory every entry that is neither a
# task subdirectory of the run, nor a path that an output option of the
# run names, nor a directory on the way to one of them; then creates the
# task subdirectories that do not exist. A task subdirectory whose subpath
# goes through a symbolic link, or a path that an output option names in
# the directory through one on the way to it, is refused first.
debasher::_prepare_task_subdirs_for_process()
{
    local dirname=$1
    local processname=$2

    # The task subdirectories of every task, finished or not, since the
    # options of a finished task still ask for its own; a process without
    # any has nothing to prepare
    local -A kept=()
    local task_idx subpath
    while IFS=$'\t' read -r task_idx subpath; do
        kept["${subpath}"]=1
    done < <(debasher::_list_task_subdirs_of_process "${processname}")
    [ ${#kept[@]} -eq 0 ] && return 0

    local outd=$(debasher::_get_process_outdir_given_dirname "${dirname}" "${processname}")
    local -a subpaths=("${!kept[@]}")

    # A symbolic link is refused before anything is removed, since removal
    # would take the link for an entry to remove: one in the subpath of a
    # task subdirectory, or on the way to a path that an output option names
    for subpath in "${subpaths[@]}"; do
        debasher::_check_subpath_has_no_link "${outd}" "${subpath}" "the task subdirectory ${subpath} of process ${processname}" || return 1
    done
    debasher::_check_output_named_paths_have_no_link "${outd}" "the output directory of process ${processname}" || return 1

    # The directory is pruned unless a _reset_outfiles method decides
    # itself what it holds, or the program is resident, whose nodes keep
    # their state from one run to the next. What it keeps: the task
    # subdirectories, the paths that output options name and the
    # directories on the way to them
    local reset_funct=$(debasher::_get_reset_funcname "${processname}")
    if [ "${reset_funct}" = "${DEBASHER_FUNCT_NOT_FOUND}" ] && [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ] && [ -d "${outd}" ]; then
        local -A ways=()
        debasher::_add_output_named_paths "${outd}" kept
        debasher::_add_ways_to_paths kept ways
        debasher::_prune_subdivided_dir 0 "the output directory of process ${processname}" "" "${outd}" kept ways || return 1
    fi

    # The task subdirectories that do not exist yet, with any missing
    # directory above them, the process output directory included
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
