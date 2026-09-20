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

    # debasher::_get_modname_from_absmodname (exercised below via
    # debasher::_resolve_program_type) calls out to "${BASENAME}",
    # normally supplied by the tool-path preamble the Makefile suffix
    # rule prepends when building debasher_lib.sh -> debasher_lib --
    # absent here since, like debasher_pkglibdir above, this sources
    # the plain .sh source directly (its own preamble bakes in the
    # configured install prefix as debasher_pkglibdir, which would
    # override the one just set above and break sourcing the rest of
    # the built engine/ dir). Set *before* sourcing, not after: unlike
    # a live "${BASENAME}"/"${PYTHON}" read, debasher_lib.sh's own
    # DEBASHER_HEREDOC_INTERPRETERS=("${PYTHON}" ...) array literal is
    # evaluated once, right when it is sourced, exactly like the real
    # preamble (which writes these vars before appending the .sh
    # source) -- setting them afterwards would silently capture empty
    # values into that array.
    BASENAME="$(command -v basename)"

    # debasher::_classify_resident_process_role shells out to "${PYTHON}".
    PYTHON="$(command -v python3)"

    # debasher::_python_heredoc_sys_path_prelude reads these two.
    debasher_pythondir="/fake/pythondir"
    debasher_pkgpythondir="/fake/pkgpythondir"

    source "${ENGINE_BUILDDIR}/debasher_lib.sh"

    # See test/engine/lib_processes.bats for why this is needed: a bare
    # top-level "declare" in debasher_lib.sh becomes local to setup()
    # unless forced global here, and would vanish once setup() returns.
    declare -g DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"
    declare -gA DEBASHER_PROGRAM_PROCESSES
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

# --- debasher::_get_python_heredoc_provider / _get_resident_process_source --

@test "debasher::_get_python_heredoc_provider finds the modern function-form provider" {
    pyproc_heredoc_py()
    {
        cat <<'EOF'
print("hi")
EOF
    }

    result=$(debasher::_get_python_heredoc_provider "pyproc")
    [ "${result}" = "pyproc_heredoc_py func" ]
}

@test "debasher::_get_python_heredoc_provider finds the legacy variable-form provider" {
    declare -g legacyproc_py="print('hi')"

    result=$(debasher::_get_python_heredoc_provider "legacyproc")
    [ "${result}" = "legacyproc_py var" ]
}

@test "debasher::_get_python_heredoc_provider fails for a process with no heredoc at all" {
    plainproc() { :; }

    run debasher::_get_python_heredoc_provider "plainproc"
    [ "${status}" -eq 1 ]
}

@test "debasher::_get_python_heredoc_provider fails for a process whose heredoc is a different language" {
    perlproc_heredoc_perl()
    {
        cat <<'EOF'
print "hi\n";
EOF
    }

    run debasher::_get_python_heredoc_provider "perlproc"
    [ "${status}" -eq 1 ]
}

@test "debasher::_get_resident_process_source returns the function-form provider's text" {
    srcproc_heredoc_py()
    {
        cat <<'EOF'
class Worker(FBPProcess):
    pass
EOF
    }

    result=$(debasher::_get_resident_process_source "srcproc")
    [[ "${result}" == *"class Worker(FBPProcess):"* ]]
}

@test "debasher::_get_resident_process_source returns the legacy variable-form provider's text" {
    declare -g legacysrcproc_py="class Worker(FBPProcess): pass"

    result=$(debasher::_get_resident_process_source "legacysrcproc")
    [ "${result}" = "class Worker(FBPProcess): pass" ]
}

@test "debasher::_get_resident_process_source fails for a process with no Python heredoc" {
    noheredocproc() { :; }

    run debasher::_get_resident_process_source "noheredocproc"
    [ "${status}" -eq 1 ]
}

# --- debasher::_classify_resident_process_role ---------------------------

@test "debasher::_classify_resident_process_role recognizes a class deriving from FBPProcess" {
    fbpproc_heredoc_py()
    {
        cat <<'EOF'
class Worker(FBPProcess):
    pass
EOF
    }

    result=$(debasher::_classify_resident_process_role "fbpproc")
    [ "${result}" = "fbpprocess" ]
}

@test "debasher::_classify_resident_process_role recognizes a class deriving from Supervisor" {
    supervisorproc_heredoc_py()
    {
        cat <<'EOF'
class Watchdog(Supervisor):
    pass
EOF
    }

    result=$(debasher::_classify_resident_process_role "supervisorproc")
    [ "${result}" = "supervisor" ]
}

@test "debasher::_classify_resident_process_role follows an aliased import of Supervisor" {
    aliasedproc_heredoc_py()
    {
        cat <<'EOF'
from mylib import Supervisor as Sup


class Watchdog(Sup):
    pass
EOF
    }

    result=$(debasher::_classify_resident_process_role "aliasedproc")
    [ "${result}" = "supervisor" ]
}

@test "debasher::_classify_resident_process_role returns unknown for a class deriving from neither base" {
    unrelatedproc_heredoc_py()
    {
        cat <<'EOF'
class Worker:
    pass
EOF
    }

    result=$(debasher::_classify_resident_process_role "unrelatedproc")
    [ "${result}" = "unknown" ]
}

@test "debasher::_classify_resident_process_role returns unknown for source with no class at all" {
    noclassproc_heredoc_py()
    {
        cat <<'EOF'
print("just a script")
EOF
    }

    result=$(debasher::_classify_resident_process_role "noclassproc")
    [ "${result}" = "unknown" ]
}

@test "debasher::_classify_resident_process_role fails with an error for a non-heredoc process" {
    regularproc() { :; }

    run debasher::_classify_resident_process_role "regularproc"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: process regularproc does not provide its code as a Python heredoc"* ]]
}

# --- debasher::_validate_resident_program_processes -----------------------

@test "debasher::_validate_resident_program_processes is a no-op for a general program" {
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"
    DEBASHER_PROGRAM_PROCESSES["whatever"]=1

    run debasher::_validate_resident_program_processes
    [ "${status}" -eq 0 ]
}

@test "debasher::_validate_resident_program_processes accepts one supervisor and several fbpprocess" {
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    DEBASHER_PROGRAM_PROCESSES=(["watchdog"]=1 ["worker_a"]=1 ["worker_b"]=1)

    watchdog_heredoc_py() { cat <<'EOF'
class Watchdog(Supervisor):
    pass
EOF
    }
    worker_a_heredoc_py() { cat <<'EOF'
class Worker(FBPProcess):
    pass
EOF
    }
    worker_b_heredoc_py() { cat <<'EOF'
class Worker(FBPProcess):
    pass
EOF
    }

    run debasher::_validate_resident_program_processes
    [ "${status}" -eq 0 ]
}

@test "debasher::_validate_resident_program_processes accepts zero supervisors" {
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    DEBASHER_PROGRAM_PROCESSES=(["worker_a"]=1)

    worker_a_heredoc_py() { cat <<'EOF'
class Worker(FBPProcess):
    pass
EOF
    }

    run debasher::_validate_resident_program_processes
    [ "${status}" -eq 0 ]
}

@test "debasher::_validate_resident_program_processes rejects a second supervisor" {
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    DEBASHER_PROGRAM_PROCESSES=(["watchdog_a"]=1 ["watchdog_b"]=1)

    watchdog_a_heredoc_py() { cat <<'EOF'
class Watchdog(Supervisor):
    pass
EOF
    }
    watchdog_b_heredoc_py() { cat <<'EOF'
class Watchdog(Supervisor):
    pass
EOF
    }

    run debasher::_validate_resident_program_processes
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: a resident program can have at most one Supervisor process"* ]]
}

@test "debasher::_validate_resident_program_processes rejects a process classifying as unknown" {
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    DEBASHER_PROGRAM_PROCESSES=(["plain_worker"]=1)

    plain_worker_heredoc_py() { cat <<'EOF'
class Worker:
    pass
EOF
    }

    run debasher::_validate_resident_program_processes
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: process plain_worker does not derive from FBPProcess or Supervisor"* ]]
}

# --- debasher::_python_heredoc_sys_path_prelude / _create_heredoc_func_body --

@test "debasher::_python_heredoc_sys_path_prelude emits sys.path.append lines for both directories" {
    result=$(debasher::_python_heredoc_sys_path_prelude)
    [[ "${result}" == *"import sys"* ]]
    [[ "${result}" == *"sys.path.append('/fake/pythondir')"* ]]
    [[ "${result}" == *"sys.path.append('/fake/pkgpythondir')"* ]]
}

@test "debasher::_create_heredoc_func_body includes the sys.path prelude for a Python heredoc process" {
    pyprelproc_heredoc_py() { cat <<'EOF'
print("hi")
EOF
    }

    result=$(debasher::_create_heredoc_func_body "pyprelproc")
    [[ "${result}" == *"sys.path.append('/fake/pythondir')"* ]]
    [[ "${result}" == *"sys.path.append('/fake/pkgpythondir')"* ]]
}

@test "debasher::_create_heredoc_func_body does not add a sys.path prelude for a non-Python heredoc process" {
    perlprelproc_heredoc_perl() { cat <<'EOF'
print "hi\n";
EOF
    }

    result=$(debasher::_create_heredoc_func_body "perlprelproc")
    [[ "${result}" != *"sys.path.append"* ]]
}

@test "a generated Python heredoc process function actually has the fake dirs on sys.path at run time" {
    realpyproc_heredoc_py() { cat <<'EOF'
import sys
print('/fake/pythondir' in sys.path)
print('/fake/pkgpythondir' in sys.path)
EOF
    }

    debasher::_create_process_func_heredoc "realpyproc"
    run realpyproc
    [ "${status}" -eq 0 ]
    [ "${lines[0]}" = "True" ]
    [ "${lines[1]}" = "True" ]
}

# --- debasher::_add_sched_to_serialized_cmdline ----------------------------
#
# debasher_exec saves the scheduler the program really runs with in the
# command line file of the output directory, because the tools that operate
# on that directory later read it from there.

@test "debasher::_add_sched_to_serialized_cmdline appends --sched when the command line has none" {
    local serialized expected result
    serialized=$(debasher::_serialize_args "debasher_exec" "--pfile" "prog.sh" "--outdir" "out")
    expected=$(debasher::_serialize_args "debasher_exec" "--pfile" "prog.sh" "--outdir" "out" "--sched" "BUILTIN")

    result=$(debasher::_add_sched_to_serialized_cmdline "${serialized}" "BUILTIN")

    [ "${result}" = "${expected}" ]
}

@test "debasher::_add_sched_to_serialized_cmdline leaves a command line that already gives --sched untouched, whatever its value" {
    local serialized result
    serialized=$(debasher::_serialize_args "debasher_exec" "--sched" "SLURM" "--pfile" "prog.sh")

    result=$(debasher::_add_sched_to_serialized_cmdline "${serialized}" "BUILTIN")

    [ "${result}" = "${serialized}" ]
}

@test "debasher::_add_sched_to_serialized_cmdline does not mistake an argument that merely contains --sched for the option" {
    local serialized expected result
    serialized=$(debasher::_serialize_args "debasher_exec" "--pfile" "a--sched.sh" "--schedule" "x")
    expected=$(debasher::_serialize_args "debasher_exec" "--pfile" "a--sched.sh" "--schedule" "x" "--sched" "BUILTIN")

    result=$(debasher::_add_sched_to_serialized_cmdline "${serialized}" "BUILTIN")

    [ "${result}" = "${expected}" ]
}

@test "debasher::_add_sched_to_serialized_cmdline works on a command line with no options at all" {
    local serialized expected result
    serialized=$(debasher::_serialize_args "debasher_exec")
    expected=$(debasher::_serialize_args "debasher_exec" "--sched" "SLURM")

    result=$(debasher::_add_sched_to_serialized_cmdline "${serialized}" "SLURM")

    [ "${result}" = "${expected}" ]
}

@test "debasher::_add_sched_to_serialized_cmdline adds the option the tools read back, keeping the other arguments intact" {
    local serialized result qcmdline
    serialized=$(debasher::_serialize_args "debasher_exec" "--pfile" "with space.sh" "--outdir" "out")

    result=$(debasher::_add_sched_to_serialized_cmdline "${serialized}" "BUILTIN")
    qcmdline=$(debasher::_sep_serialized_to_qstr "${DEBASHER_ARG_SEP}" "${result}")

    run debasher::_get_opt_value_from_quoted_cmd "${qcmdline}" "--sched"
    [ "${status}" -eq 0 ]
    [ "${output}" = "BUILTIN" ]

    run debasher::_get_opt_value_from_quoted_cmd "${qcmdline}" "--pfile"
    [ "${output}" = "with space.sh" ]
}
