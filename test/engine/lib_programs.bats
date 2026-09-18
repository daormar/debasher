#!/usr/bin/env bats
#
# Unit tests for the program-type declaration mechanism added to
# engine/debasher_lib_programs.sh (debasher::program_type,
# debasher::_resolve_program_type) for the new "resident" program type
# (see to_do_fbp.md): a module's optional `_program_type` method lets
# it opt into "resident" instead of today's default "general". Only
# the top-level pfile's own `_program_type` is ever resolved.

setup() {
    : "${ENGINE_BUILDDIR:?ENGINE_BUILDDIR must point at the built engine/ dir}"
    debasher_pkglibdir="${ENGINE_BUILDDIR}"
    source "${ENGINE_BUILDDIR}/debasher_lib.sh"

    # debasher::_get_modname_from_absmodname (exercised below via
    # debasher::_resolve_program_type) calls out to "${BASENAME}",
    # normally supplied by the tool-path preamble the Makefile suffix
    # rule prepends when building debasher_lib.sh -> debasher_lib --
    # absent here since, like debasher_pkglibdir above, this sources
    # the plain .sh source directly (its own preamble bakes in the
    # configured install prefix as debasher_pkglibdir, which would
    # override the one just set above and break sourcing the rest of
    # the built engine/ dir).
    BASENAME="$(command -v basename)"

    # See test/engine/lib_processes.bats for why this is needed: a bare
    # top-level "declare" in debasher_lib.sh becomes local to setup()
    # unless forced global here, and would vanish once setup() returns.
    declare -g DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"
}

# --- debasher::program_type -------------------------------------------

@test "debasher::program_type sets DEBASHER_PROGRAM_TYPE to a valid value" {
    debasher::program_type "resident"
    [ "${DEBASHER_PROGRAM_TYPE}" = "resident" ]
}

@test "debasher::program_type aborts on an invalid program type" {
    run debasher::program_type "bogus"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: invalid program type 'bogus'"* ]]
}

# --- debasher::_resolve_program_type ------------------------------------

@test "debasher::_resolve_program_type leaves DEBASHER_PROGRAM_TYPE at its default when the module declares no _program_type method" {
    debasher::_resolve_program_type "/tmp/no_program_type_mod.sh"
    [ "${DEBASHER_PROGRAM_TYPE}" = "${DEBASHER_PROGRAM_TYPE_GENERAL}" ]
}

@test "debasher::_resolve_program_type invokes the module's _program_type method and applies its declared type" {
    residentmod_program_type()
    {
        program_type "resident"
    }

    debasher::_resolve_program_type "/tmp/residentmod.sh"
    [ "${DEBASHER_PROGRAM_TYPE}" = "resident" ]
}

@test "debasher::_resolve_program_type does not resolve a same-named sibling module's method" {
    othermod_program_type()
    {
        program_type "resident"
    }

    debasher::_resolve_program_type "/tmp/notother.sh"
    [ "${DEBASHER_PROGRAM_TYPE}" = "${DEBASHER_PROGRAM_TYPE_GENERAL}" ]
}
