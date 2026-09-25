#!/usr/bin/env bats
#
# Unit tests for the search of a module or a program file
# (engine/debasher_lib_modules.sh): a relative name is looked for in the
# current directory and then in the directories of DEBASHER_MOD_DIR, and
# the tools that take a program file resolve it the same way
# (debasher::_resolve_pfile).

setup() {
    : "${ENGINE_BUILDDIR:?ENGINE_BUILDDIR must point at the built engine/ dir}"
    debasher_pkglibdir="${ENGINE_BUILDDIR}"
    debasher_bindir="/fake/bindir"

    # Tool paths normally supplied by the preamble the Makefile suffix
    # rule prepends (see test/engine/lib_programs.bats), set before
    # sourcing, as the preamble does
    BASENAME="$(command -v basename)"
    DIRNAME="$(command -v dirname)"
    FIND="$(command -v find)"
    SORT="$(command -v sort)"
    GREP="$(command -v grep)"
    REALPATH="$(command -v realpath)"

    source "${ENGINE_BUILDDIR}/debasher_lib.sh"

    # See test/engine/lib_processes.bats: a bare top-level "declare" in
    # debasher_lib.sh becomes local to setup() unless forced global here
    declare -ga DEBASHER_REJECTED_MOD_CANDIDATES
    declare -ga DEBASHER_PROGRAM_MODULES

    cwd_dir="${BATS_TEST_TMPDIR}/cwd"
    mod_dir="${BATS_TEST_TMPDIR}/mods"
    mkdir -p "${cwd_dir}" "${mod_dir}"
    cd "${cwd_dir}"
}

# --- debasher::_search_mod_in_dirs --------------------------------------

@test "a module in the current directory is not shadowed by one in DEBASHER_MOD_DIR" {
    touch "${cwd_dir}/prg.sh" "${mod_dir}/prg.sh"
    DEBASHER_MOD_DIR="${mod_dir}"

    debasher::_search_mod_in_dirs "prg.sh"

    [ "${DEBASHER_RESOLVED_MODNAME}" = "${cwd_dir}/prg.sh" ]
}

@test "a module not in the current directory is found in DEBASHER_MOD_DIR" {
    touch "${mod_dir}/prg.sh"
    DEBASHER_MOD_DIR="/nonexistent:${mod_dir}"

    debasher::_search_mod_in_dirs "prg"

    [ "${DEBASHER_RESOLVED_MODNAME}" = "${mod_dir}/prg.sh" ]
}

# --- debasher::_resolve_pfile -------------------------------------------

@test "debasher::_resolve_pfile finds a program file through DEBASHER_MOD_DIR" {
    touch "${mod_dir}/prg.sh"
    DEBASHER_MOD_DIR="${mod_dir}"

    run debasher::_resolve_pfile "prg.sh"

    [ "${status}" -eq 0 ]
    [ "${output}" = "${mod_dir}/prg.sh" ]
}

@test "debasher::_resolve_pfile makes a relative path in the current directory absolute" {
    mkdir "${cwd_dir}/sub"
    touch "${cwd_dir}/sub/prg.sh"
    DEBASHER_MOD_DIR=""

    run debasher::_resolve_pfile "sub/prg.sh"

    [ "${status}" -eq 0 ]
    [ "${output}" = "${cwd_dir}/sub/prg.sh" ]
}

@test "debasher::_resolve_pfile takes an absolute path as is" {
    touch "${mod_dir}/prg.sh"
    DEBASHER_MOD_DIR=""

    run debasher::_resolve_pfile "${mod_dir}/prg.sh"

    [ "${status}" -eq 0 ]
    [ "${output}" = "${mod_dir}/prg.sh" ]
}

@test "debasher::_resolve_pfile fails on a program file found nowhere" {
    DEBASHER_MOD_DIR="${mod_dir}"

    run debasher::_resolve_pfile "prg.sh"

    [ "${status}" -eq 1 ]
    [[ "${output}" == *"File not found"* ]]
}

# --- debasher::_get_loaded_module_fname ---------------------------------

@test "debasher::_get_loaded_module_fname gives the file a module was loaded from" {
    DEBASHER_PROGRAM_MODULES=( "${mod_dir}/other.sh" "${mod_dir}/prg.sh" )

    run debasher::_get_loaded_module_fname "prg"

    [ "${status}" -eq 0 ]
    [ "${output}" = "${mod_dir}/prg.sh" ]
}

@test "debasher::_get_loaded_module_fname fails for a module not loaded" {
    DEBASHER_PROGRAM_MODULES=( "${mod_dir}/other.sh" )

    run debasher::_get_loaded_module_fname "prg.sh"

    [ "${status}" -eq 1 ]
}

# --- debasher::_set_opt_value_in_serialized_cmdline ---------------------

@test "debasher::_set_opt_value_in_serialized_cmdline replaces the value of the option only" {
    local cmdline
    cmdline=$(debasher::_serialize_args "debasher_exec" "--pfile" "prg.sh" "--outdir" "out" "-x" "--pfile")

    local result
    result=$(debasher::_set_opt_value_in_serialized_cmdline "${cmdline}" "--pfile" "/abs/prg.sh")

    [ "${result}" = "$(debasher::_serialize_args "debasher_exec" "--pfile" "/abs/prg.sh" "--outdir" "out" "-x" "--pfile")" ]
}

# --- modules saved by the DeBasher UI -----------------------------------

@test "a module saved by the UI into its own directory is found with or without its extension" {
    mkdir -p "${mod_dir}/some_outdir/.debasher"
    touch "${mod_dir}/some_outdir/prg.sh"
    echo '{"name": "prg"}' > "${mod_dir}/some_outdir/.debasher/program.json"
    DEBASHER_MOD_DIR="${mod_dir}"

    run debasher::_resolve_pfile "prg"
    [ "${status}" -eq 0 ]
    [ "${output}" = "${mod_dir}/some_outdir/prg.sh" ]

    run debasher::_resolve_pfile "prg.sh"
    [ "${status}" -eq 0 ]
    [ "${output}" = "${mod_dir}/some_outdir/prg.sh" ]
}
