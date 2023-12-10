############################
# MODULE-RELATED FUNCTIONS #
############################

########
get_modname_from_absmodname()
{
    local absmodname=$1

    local modname=`${BASENAME} "${absmodname}"`

    modname="${modname%.sh}"

    echo "${modname}"
}

########
get_shrdirs_funcname()
{
    local absmodname=$1

    local modname=`get_modname_from_absmodname "${absmodname}"`

    get_module_funcname "${modname}" "${MODULE_METHOD_NAME_SHRDIRS}"
}

########
get_pipeline_funcname()
{
    local absmodname=$1

    local modname=`get_modname_from_absmodname "${absmodname}"`

    get_module_funcname "${modname}" "${MODULE_METHOD_NAME_PIPELINE}"
}

########
search_mod_in_dirs()
{
    local module=$1

    # Obtain array with directories
    deserialize_args_given_sep "${PANPIPE_MOD_DIR}" "${PANPIPE_MOD_DIR_SEP}"

    # Add current directory
    DESERIALIZED_ARGS+=( "." )

    # Search module in directories listed in PANPIPE_MOD_DIR
    local dir
    local fullmodname
    for dir in "${DESERIALIZED_ARGS[@]}"; do
        for fname in "${dir}/${module}" "${dir}/${module}.sh"; do
            if [ -f "${fname}" ]; then
                if is_absolute_path "${fname}"; then
                    fullmodname="${fname}"
                else
                    fullmodname=`get_absolute_path "${fname}"`
                fi
                break
            fi
        done
    done

    # Fallback to package bindir
    if [ -z "${fullmodname}" ]; then
        fullmodname="${panpipe_bindir}/${module}"
    fi

    echo "$fullmodname"
}

########
determine_full_module_name()
{
    local module=$1
    if is_absolute_path "${module}"; then
        fullmodname="${module}"
    else
        fullmodname=`search_mod_in_dirs "${module}"`
    fi

    echo "$fullmodname"
}

########
module_is_loaded()
{
    local fullmodname=$1

    # Search module name in the array of loaded modules
    local absmodname
    for absmodname in "${PIPELINE_MODULES[@]}"; do
        if [ "${absmodname}" = "${fullmodname}" ]; then
            return 0
        fi
    done

    # The given module name was not found
    return 1
}

########
load_panpipe_module()
{
    local module=$1

    # Determine full module name
    local fullmodname=`determine_full_module_name "$module"`

    echo "Loading module $module (${fullmodname})..." >&2

    # Check that module file exists
    if [ -f "${fullmodname}" ]; then
        # Check that module has not been loaded previously
        if module_is_loaded "${fullmodname}"; then
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
            PIPELINE_MODULES+=("${fullmodname}")
        fi
    else
        echo "File not found (consider setting an appropriate value for PANPIPE_MOD_DIR environment variable)">&2
        exit 1
    fi
}

get_mod_vars_and_funcs_fname()
{
    local dirname=$1

    echo "${dirname}/${MOD_VARS_AND_FUNCS_BASENAME}"
}
