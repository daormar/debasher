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

############################
# MODULE-RELATED FUNCTIONS #
############################

########
debasher::_get_modname_from_absmodname()
{
    local absmodname=$1

    local modname=$(${BASENAME} "${absmodname}")

    modname="${modname%.sh}"

    echo "${modname}"
}

########
debasher::_get_mod_document_funcname()
{
    local absmodname=$1

    local modname=$(debasher::_get_modname_from_absmodname "${absmodname}")

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_DOCUMENT}"
}

########
debasher::_get_shrdirs_funcname()
{
    local absmodname=$1

    local modname=$(debasher::_get_modname_from_absmodname "${absmodname}")

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_SHRDIRS}"
}

########
debasher::_get_program_funcname()
{
    local absmodname=$1

    local modname=$(debasher::_get_modname_from_absmodname "${absmodname}")

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_PROGRAM}"
}

########
debasher::_get_ui_program_metadata_fname()
{
    local dir=$1

    echo "${dir}/${DEBASHER_UI_PROGRAM_DIRNAME}/${DEBASHER_UI_PROGRAM_METADATA_FNAME}"
}

########
debasher::_is_ui_program_dir()
{
    # $1 - directory that may hold a module the DeBasher UI generated
    # $2 - module name that a genuine UI program directory here would
    #      have as its "name" field
    #
    # api/persistence.py::save_script always names the script after the
    # program's own "name", and save_program always writes that same
    # name into the sibling .debasher/program.json (api/persistence.py::
    # METADATA_DIRNAME/PROGRAM_FILENAME) -- so a real UI directory whose
    # script is "${module}.sh" always has "name": "${module}" in that
    # file. The directory itself need not be called "${module}" (the UI
    # lets a program be saved under any output directory name), so this
    # metadata check is the only way to tell a genuine UI program
    # directory apart from an unrelated folder that just happens to
    # contain a same-named script.
    local dir=$1
    local module=$2

    local metadata_fname=$(debasher::_get_ui_program_metadata_fname "${dir}")

    [ -f "${metadata_fname}" ] || return 1

    "${GREP}" -q "\"name\"[[:space:]]*:[[:space:]]*\"${module}\"" "${metadata_fname}"
}

########
debasher::_search_mod_in_immediate_subdirs()
{
    # $1 - parent directory (an entry from DEBASHER_MOD_DIR, or the
    #      current directory)
    # $2 - module name (no extension)
    #
    # Looks one level below $1 for a module the DeBasher UI saved into
    # its own output directory (api/persistence.py never nests a saved
    # program any deeper than that, so this never descends further).
    # Unlike a hand-written module, the file must carry the ".sh"
    # extension and is only accepted once debasher::_is_ui_program_dir
    # confirms it via the sibling .debasher/program.json metadata the UI
    # always writes alongside it.
    #
    # Leaves the resolved path in DEBASHER_SUBDIR_MOD_MATCH on success
    # (empty otherwise) -- not echoed, since this is called directly
    # rather than via $(...): a command substitution would run it in a
    # subshell, losing the DEBASHER_REJECTED_MOD_CANDIDATES entries it
    # appends below. Every same-named candidate that fails the
    # UI-program-dir check is appended to that array, so a subsequent
    # "module not found" error can mention it.
    local parentdir=$1
    local module=$2

    DEBASHER_SUBDIR_MOD_MATCH=""

    local candidates=$("${FIND}" "${parentdir}" -mindepth 2 -maxdepth 2 -type f -name "${module}.sh" 2>/dev/null | "${SORT}")

    [ -z "${candidates}" ] && return

    local candidate
    while IFS= read -r candidate; do
        local subdir=$("${DIRNAME}" "${candidate}")
        if debasher::_is_ui_program_dir "${subdir}" "${module}"; then
            if [ -z "${DEBASHER_SUBDIR_MOD_MATCH}" ]; then
                DEBASHER_SUBDIR_MOD_MATCH="${candidate}"
            else
                echo "Warning: module \"${module}\" matches more than one DeBasher UI program directory under ${parentdir}; using ${DEBASHER_SUBDIR_MOD_MATCH}" >&2
            fi
        else
            DEBASHER_REJECTED_MOD_CANDIDATES+=("${candidate}")
        fi
    done <<< "${candidates}"
}

########
debasher::_search_mod_in_dirs()
{
    local module=$1

    # Obtain array with directories
    debasher::_deserialize_args_given_sep "${DEBASHER_MOD_DIR}" "${DEBASHER_MOD_DIR_SEP}"

    # Add current directory
    DEBASHER_DESERIALIZED_ARGS+=( "." )

    # Reset the list of rejected same-named candidates so a later error
    # message reports only what this search actually found
    DEBASHER_REJECTED_MOD_CANDIDATES=()

    # Search module in directories listed in DEBASHER_MOD_DIR (plus the
    # current directory), stopping at the first hit -- unlike a
    # PATH-style search, the *first* matching directory wins
    local dir
    local fname
    local fullmodname=""
    for dir in "${DEBASHER_DESERIALIZED_ARGS[@]}"; do
        for fname in "${dir}/${module}" "${dir}/${module}.sh"; do
            if [ -f "${fname}" ]; then
                fullmodname="${fname}"
                break 2
            fi
        done

        # Not found directly under $dir: also look one level below, for
        # a module the DeBasher UI saved into its own output directory
        debasher::_search_mod_in_immediate_subdirs "${dir}" "${module}"
        if [ -n "${DEBASHER_SUBDIR_MOD_MATCH}" ]; then
            fullmodname="${DEBASHER_SUBDIR_MOD_MATCH}"
            break
        fi
    done

    if [ -n "${fullmodname}" ]; then
        if ! debasher::_is_absolute_path "${fullmodname}"; then
            fullmodname=$(debasher::_get_absolute_path "${fullmodname}")
        fi
    else
        # Fallback to package bindir
        fullmodname="${debasher_bindir}/${module}"
    fi

    # Not echoed: called directly rather than via $(...) so that
    # DEBASHER_REJECTED_MOD_CANDIDATES, populated above, reaches the
    # caller's own shell instead of a subshell's copy of it (see
    # DEBASHER_RESOLVED_MODNAME's declaration in debasher_lib.sh)
    DEBASHER_RESOLVED_MODNAME="${fullmodname}"
}

########
debasher::_determine_full_module_name()
{
    local module=$1
    if debasher::_is_absolute_path "${module}"; then
        # No directory search performed for an absolute path, so any
        # candidates rejected by an earlier, unrelated search must not
        # be reported alongside this module
        DEBASHER_REJECTED_MOD_CANDIDATES=()
        DEBASHER_RESOLVED_MODNAME="${module}"
    else
        debasher::_search_mod_in_dirs "${module}"
    fi
}

########
debasher::_module_is_loaded()
{
    local fullmodname=$1

    # Search module name in the array of loaded modules
    local absmodname
    for absmodname in "${DEBASHER_PROGRAM_MODULES[@]}"; do
        if [ "${absmodname}" = "${fullmodname}" ]; then
            return 0
        fi
    done

    # The given module name was not found
    return 1
}

########
# Public: Loads a DeBasher module.
#
# $1 - String containing the name of a module.
#
# Examples
#
#   debasher::load_debasher_module "module_name"
#
# The function does not return any value.
debasher::load_debasher_module()
{
    local module=$1

    # Determine full module name (called directly, not via $(...), so
    # that a rejected-candidates report below reflects this search --
    # see DEBASHER_RESOLVED_MODNAME's declaration in debasher_lib.sh)
    debasher::_determine_full_module_name "$module"
    local fullmodname="${DEBASHER_RESOLVED_MODNAME}"

    echo "Loading module $module (${fullmodname})..." >&2

    # Check that module file exists
    if [ -f "${fullmodname}" ]; then
        # Check that module has not been loaded previously
        if debasher::_module_is_loaded "${fullmodname}"; then
            :
        else
            # Obtain directory for module
            local dirname=$("${DIRNAME}" "${fullmodname}")

            # Change to module dir
            pushd "${dirname}" > /dev/null

            # Load file
            . "${fullmodname}" || exit 1

            # Restore previous dir
            popd > /dev/null

            # Store module file name in array
            DEBASHER_PROGRAM_MODULES+=("${fullmodname}")
        fi
    else
        echo "File not found: ${fullmodname} (module \"${module}\"; consider setting an appropriate value for DEBASHER_MOD_DIR environment variable)">&2
        if [ ${#DEBASHER_REJECTED_MOD_CANDIDATES[@]} -gt 0 ]; then
            echo "Note: found the following same-named file(s) one level below a DEBASHER_MOD_DIR entry, but none was recognized as a DeBasher UI program directory (missing or mismatched ${DEBASHER_UI_PROGRAM_DIRNAME}/${DEBASHER_UI_PROGRAM_METADATA_FNAME}):" >&2
            local candidate
            for candidate in "${DEBASHER_REJECTED_MOD_CANDIDATES[@]}"; do
                echo "  - ${candidate}" >&2
            done
        fi
        exit 1
    fi
}

########
# Public: Loads a DeBasher module.
#
# $1 - String containing the name of a module.
#
# Examples
#
#   load_debasher_module "module_name"
#
# The function does not return any value.
load_debasher_module() { debasher::load_debasher_module "$@"; }

########
debasher::_show_all_program_envvars()
{
    # $1 - newline-separated variable names (as produced by "compgen
    #      -v") captured right before load_debasher_module ran.
    # $2 - the same, captured right after loading the module (plus
    #      everything it loads, transitively). Both snapshots are taken
    #      by the caller, in its own stack frame, rather than here: a
    #      "compgen -v" run from *inside* this function would also see
    #      this function's own locals, which would then wrongly show up
    #      as "new".
    #
    # Anything in $2 but not $1 was bound while loading — a
    # caller-supplied name like DEBASHER_MOD_DIR is excluded because it
    # was already set beforehand, and the engine's own bookkeeping
    # (DEBASHER_*, plus plain bash/shell state a "cd" or subshell
    # naturally updates) is excluded so only the module's own variables
    # show.
    local before=$1
    local after=$2

    local name
    while IFS= read -r name; do
        case "$name" in
            DEBASHER_*|BASH_*) continue ;;
            OLDPWD|PWD|DIRSTACK|PIPESTATUS|FUNCNAME|GROUPS|SECONDS|RANDOM|\
LINENO|REPLY|EUID|UID|PPID|BASHPID|SHLVL|HISTCMD|OPTIND|OPTARG|IFS) continue ;;
        esac
        if ! "${GREP}" -qxF "$name" <<< "$before"; then
            echo "- \`${name}\`: \`${!name}\`"
        fi
    done <<< "$after"
}

########
debasher::_get_mod_vars_and_funcs_fname()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_MOD_VARS_AND_FUNCS_BASENAME}"
}

########
# Public: Generates a description for a module.
#
# $1 - Text describing the module
#
# Examples
#
#   debasher::document_module "This module implements the \"Hello World!\" program."
#
# The function prints the given module description to the standard output.
debasher::document_module()
{
    local desc=$1
    echo $desc
}

document_module() { debasher::document_module "$@"; }

########
debasher::_show_module_documentation()
{
    local modulename=$1
    local show_shrdirs=$2

    # Print header
    local modname=$(debasher::_get_modname_from_absmodname "${modulename}")
    echo "# ${modname}"
    echo ""

    # Print body
    local document_funcname=$(debasher::_get_mod_document_funcname ${modulename})
    if debasher::_func_exists ${document_funcname}; then
        ${document_funcname}
        echo ""
    else
        echo "Warning: no document function was defined" >&2
        echo "" >&2
    fi

    if [ "${show_shrdirs}" = 1 ]; then
        echo "## Shared Directories"
        debasher::_show_module_shared_dirs "${modulename}"
        echo ""
    fi
}

########
debasher::_show_module_shared_dirs()
{
    local absmodname=$1

    # Reset global variable so that only the shared directories
    # defined directly by this module are taken into account (and not
    # those defined by other modules)
    DEBASHER_PROGRAM_SHDIRS=()

    # Execute the module's shared_dirs method, if defined
    local shrdirs_funcname=$(debasher::_get_shrdirs_funcname "${absmodname}")
    if debasher::_func_exists "${shrdirs_funcname}"; then
        ${shrdirs_funcname} || exit 1
    fi

    # Print shared directory names
    local dirname
    for dirname in "${!DEBASHER_PROGRAM_SHDIRS[@]}"; do
        echo "- \`${dirname}\`"
    done
}
