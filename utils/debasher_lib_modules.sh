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

############################
# MODULE-RELATED FUNCTIONS #
############################

########
debasher::_get_modname_from_absmodname()
{
    local absmodname=$1

    local modname=`${BASENAME} "${absmodname}"`

    modname="${modname%.sh}"

    echo "${modname}"
}

########
debasher::_get_mod_document_funcname()
{
    local absmodname=$1

    local modname=`debasher::_get_modname_from_absmodname "${absmodname}"`

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_DOCUMENT}"
}

########
debasher::_get_shrdirs_funcname()
{
    local absmodname=$1

    local modname=`debasher::_get_modname_from_absmodname "${absmodname}"`

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_SHRDIRS}"
}

########
debasher::_get_program_funcname()
{
    local absmodname=$1

    local modname=`debasher::_get_modname_from_absmodname "${absmodname}"`

    debasher::_get_module_funcname "${modname}" "${DEBASHER_MODULE_METHOD_NAME_PROGRAM}"
}

########
debasher::_search_mod_in_dirs()
{
    local module=$1

    # Obtain array with directories
    debasher::_deserialize_args_given_sep "${DEBASHER_MOD_DIR}" "${DEBASHER_MOD_DIR_SEP}"

    # Add current directory
    DEBASHER_DESERIALIZED_ARGS+=( "." )

    # Search module in directories listed in DEBASHER_MOD_DIR
    local dir
    local fullmodname
    for dir in "${DEBASHER_DESERIALIZED_ARGS[@]}"; do
        for fname in "${dir}/${module}" "${dir}/${module}.sh"; do
            if [ -f "${fname}" ]; then
                if debasher::_is_absolute_path "${fname}"; then
                    fullmodname="${fname}"
                else
                    fullmodname=`debasher::_get_absolute_path "${fname}"`
                fi
                break
            fi
        done
    done

    # Fallback to package bindir
    if [ -z "${fullmodname}" ]; then
        fullmodname="${debasher_bindir}/${module}"
    fi

    echo "$fullmodname"
}

########
debasher::_determine_full_module_name()
{
    local module=$1
    if debasher::_is_absolute_path "${module}"; then
        fullmodname="${module}"
    else
        fullmodname=`debasher::_search_mod_in_dirs "${module}"`
    fi

    echo "$fullmodname"
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

    # Determine full module name
    local fullmodname=`debasher::_determine_full_module_name "$module"`

    echo "Loading module $module (${fullmodname})..." >&2

    # Check that module file exists
    if [ -f "${fullmodname}" ]; then
        # Check that module has not been loaded previously
        if debasher::_module_is_loaded "${fullmodname}"; then
            :
        else
            # Obtain directory for module
            local dirname=`"${DIRNAME}" "${fullmodname}"`

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
        echo "File not found (consider setting an appropriate value for DEBASHER_MOD_DIR environment variable)">&2
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
#   debasher::module_description "This module implements the \"Hello World!\" program."
#
# The function prints the given module description to the standard output.
debasher::module_description()
{
    local desc=$1
    echo $desc
}

module_description() { debasher::module_description "$@"; }

########
debasher::document_module()
{
    local modulename=$1

    # Print header
    local modname=`debasher::_get_modname_from_absmodname "${modulename}"`
    echo "# ${modname}"
    echo ""

    # Print body
    local document_funcname=`debasher::_get_mod_document_funcname ${modulename}`
    if debasher::_func_exists ${document_funcname}; then
        ${document_funcname}
        echo ""
    else
        echo "Warning: no document function was defined" >&2
        echo "" >&2
    fi
}

document_module() { debasher::document_module "$@"; }
