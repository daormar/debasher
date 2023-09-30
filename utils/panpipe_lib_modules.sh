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

    echo "${modname}_shared_dirs"
}

########
get_pipeline_funcname()
{
    local absmodname=$1

    local modname=`get_modname_from_absmodname "${absmodname}"`

    echo "${modname}_pipeline"
}

########
get_commasep_ppl_modules()
{
    local pfile=$1
    local modules=`"$AWK" '{if($1=="#import") {$1=""; gsub(","," ",$0); printf "%s ",$0}}' $pfile | "$AWK" '{for(i=1;i<=NF;++i) {if(i>1) printf","; printf"%s",$i}}'` ; pipe_fail || return 1
    echo "${modules}"
}


########
search_mod_in_dirs()
{
    local module=$1

    # Search module in directories listed in PANPIPE_MOD_DIR
    local PANPIPE_MOD_DIR_BLANKS=`replace_str_elem_sep_with_blank "," ${PANPIPE_MOD_DIR}`
    PANPIPE_MOD_DIR_BLANKS=". "${PANPIPE_MOD_DIR_BLANKS}
    local dir
    local fullmodname
    for dir in ${PANPIPE_MOD_DIR_BLANKS}; do
        for fname in "${dir}/${module}" "${dir}/${module}.sh"; do
            if [ -f "${fname}" ]; then
                fullmodname="${fname}"
                break
            fi
        done
    done

    # Fallback to package bindir
    if [ -z "${fullmodname}" ]; then
        fullmodname="${panpipe_bindir}/${module}"
    fi

    echo $fullmodname
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
load_pipeline_module()
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
            # Load file
            . "${fullmodname}" || return 1
            # Store module name in array
            local i=${#PIPELINE_MODULES[@]}
            PIPELINE_MODULES[${i}]="${fullmodname}"
        fi
    else
        echo "File not found (consider setting an appropriate value for PANPIPE_MOD_DIR environment variable)">&2
        return 1
    fi
}

########
load_pipeline_modules()
{
    local pfile=$1

    file_exists "$pfile" || { echo "Error: file "$pfile" does not exist" >&2 ; return 1; }

    local comma_sep_modules=`get_commasep_ppl_modules "$pfile"`

    if [ -z "${comma_sep_modules}" ]; then
        echo "Error: no pipeline modules were given" >&2
        return 1
    else
        # Load modules
        local blank_sep_modules=`replace_str_elem_sep_with_blank "," "${comma_sep_modules}"`
        local mod
        for mod in ${blank_sep_modules}; do
            load_pipeline_module "$mod" || { echo "Error while loading ${mod}" >&2 ; return 1; }
        done
    fi
}

########
get_pipeline_fullmodnames()
{
    local pfile=$1

    file_exists "$pfile" || { echo "Error: file $pfile does not exist" >&2 ; return 1; }

    local comma_sep_modules=`get_commasep_ppl_modules "$pfile"`

    if [ -z "${comma_sep_modules}" ]; then
        echo "Warning: no pipeline modules were given" >&2
    else
        # Get names
        local fullmodnames
        local blank_sep_modules=`replace_str_elem_sep_with_blank "," ${comma_sep_modules}`
        local mod
        for mod in ${blank_sep_modules}; do
            local fullmodname=`determine_full_module_name $mod`
            if [ -z "${fullmodnames}" ]; then
                fullmodnames=${fullmodname}
            else
                fullmodnames="${fullmodnames} ${fullmodname}"
            fi
        done
        echo "${fullmodnames}"
    fi
}
