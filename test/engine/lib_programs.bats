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

@test "debasher::_classify_resident_process_role takes a class deriving from ProgramLauncher for a node" {
    launcherproc_heredoc_py()
    {
        cat <<'EOF'
from debasher_runtime_lib import ProgramLauncher


class Launch(ProgramLauncher):
    PFILE = "pipeline.sh"
EOF
    }

    result=$(debasher::_classify_resident_process_role "launcherproc")
    [ "${result}" = "fbpprocess" ]
}

@test "debasher::_classify_resident_process_role takes a class deriving from DirectoryWatcher for a node" {
    watcherproc_heredoc_py()
    {
        cat <<'EOF'
from debasher_runtime_lib import DirectoryWatcher


class Watch(DirectoryWatcher):
    PATTERN = "*.bam"
EOF
    }

    result=$(debasher::_classify_resident_process_role "watcherproc")
    [ "${result}" = "fbpprocess" ]
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

# --- fifo tags and the channels of a resident program ------------------------
#
# The registries are filled by hand, as debasher_exec leaves them once every
# process has defined its options and the other end of every fifo is known.

set_up_registries() {
    declare -gA DEBASHER_PROGRAM_FIFOS=() DEBASHER_FIFO_USERS=() DEBASHER_FIFO_KINDS=()
    declare -gA DEBASHER_FIFO_MIRRORED=() DEBASHER_RESIDENT_PROCESS_ROLES=()
    declare -gA DEBASHER_FIFO_OWNER_OPTS=() DEBASHER_FIFO_USER_OPTS=()
    declare -gA DEBASHER_RESIDENT_TASK_PORTS=()
    declare -gA DEBASHER_PROCESS_OPT_LIST_LEN=() DEBASHER_INITIAL_PROCESS_SPEC=()
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    SORT="$(command -v sort)"
    TR="$(command -v tr)"
}

# $1: process name, $2: role, $3: number of tasks (1 if omitted)
add_process() {
    DEBASHER_RESIDENT_PROCESS_ROLES["$1"]="$2"
    DEBASHER_PROCESS_OPT_LIST_LEN["$1"]="${3:-1}"
}

# A node or process end as the registries store it: $1 process, $2 task
end_of() {
    echo "$1${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${2:-0}"
}

# $1: fifo, $2: owner end, $3: other end (or "outside"), $4: tag (optional),
# $5: the owner's option (by default an input option for a tagged fifo fed
# from outside, which its owner reads, and an output option otherwise), $6:
# the option of the process at the other end ("-in" by default)
add_fifo() {
    DEBASHER_PROGRAM_FIFOS["$1"]="$2"
    if [ "$3" = "outside" ]; then
        DEBASHER_FIFO_USERS["$1"]="${DEBASHER_EXTERNAL_FIFO_USER}"
    else
        DEBASHER_FIFO_USERS["$1"]="$3"
    fi
    if [ -n "${4:-}" ]; then
        DEBASHER_FIFO_KINDS["$1"]="$4"
    fi
    if [ -n "${5:-}" ]; then
        DEBASHER_FIFO_OWNER_OPTS["$1"]="$5"
    elif [ -n "${4:-}" ] && [ "$3" = "outside" ]; then
        DEBASHER_FIFO_OWNER_OPTS["$1"]="-in"
    else
        DEBASHER_FIFO_OWNER_OPTS["$1"]="-out"
    fi
    if [ "$3" != "outside" ]; then
        DEBASHER_FIFO_USER_OPTS["$1"]="${6:--in}"
    fi
}

@test "debasher::_validate_program_fifo_kinds accepts the channels of the chaos reference program" {
    set_up_registries
    add_process fanin fbpprocess
    add_process loop fbpprocess
    add_process sink fbpprocess
    add_process sup supervisor
    add_fifo sup/sup_trig_fanin "$(end_of sup)" "$(end_of fanin)" control
    add_fifo sup/sup_manual "$(end_of sup)" outside control
    add_fifo fanin/fanin_ext "$(end_of fanin)" outside external
    add_fifo fanin/fanin_to_loop "$(end_of fanin)" "$(end_of loop)"
    add_fifo loop/loop_to_fanin "$(end_of loop)" "$(end_of fanin)"
    add_fifo fanin/fanin_to_sink "$(end_of fanin)" "$(end_of sink)"
    add_fifo fanin/fanin_hb "$(end_of fanin)" "$(end_of sup)"
    add_fifo sink/sink_hb "$(end_of sink)" "$(end_of sup)"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "debasher::_validate_program_fifo_kinds refuses a node that no round can reach" {
    # Two nodes fed from outside fan in to c, and only a can be triggered.
    set_up_registries
    add_process a fbpprocess
    add_process b fbpprocess
    add_process c fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control
    add_fifo a/a_ext "$(end_of a)" outside external
    add_fifo b/b_ext "$(end_of b)" outside external
    add_fifo a/a_out "$(end_of a)" "$(end_of c)"
    add_fifo b/b_out "$(end_of b)" "$(end_of c)"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: no round can reach b:"* ]]
}

@test "debasher::_validate_program_fifo_kinds follows the fifos in the direction they carry a marker" {
    # b only writes to the initiator a, so nothing reaches b.
    set_up_registries
    add_process a fbpprocess
    add_process b fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control
    add_fifo b/b_out "$(end_of b)" "$(end_of a)"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: no round can reach b:"* ]]
}

@test "debasher::_validate_program_fifo_kinds names an unreachable task of an array with its index" {
    set_up_registries
    add_process start fbpprocess
    add_process worker fbpprocess 3
    add_fifo start/start_trigger "$(end_of start)" outside control
    add_fifo start/start_out_0 "$(end_of start)" "$(end_of worker 0)"
    add_fifo start/start_out_1 "$(end_of start)" "$(end_of worker 1)"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: no round can reach worker:2:"* ]]
}

@test "debasher::_validate_program_fifo_kinds refuses an external fifo with its other end inside the program" {
    set_up_registries
    add_process a fbpprocess
    add_process b fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control
    add_fifo a/a_ext "$(end_of a)" "$(end_of b)" external

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: fifo a/a_ext is tagged --external, but process b of the program uses it"* ]]
}

@test "debasher::_validate_program_fifo_kinds refuses a control fifo between two nodes" {
    set_up_registries
    add_process a fbpprocess
    add_process b fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control
    add_fifo a/a_to_b "$(end_of a)" "$(end_of b)" control

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: fifo a/a_to_b is tagged --control, but it is neither fed from outside the program nor written by the Supervisor to a node"* ]]
}

@test "debasher::_validate_program_fifo_kinds refuses a fifo defined by its reader without a tag" {
    # a reads a fifo fed from outside, and forgot to tag it.
    set_up_registries
    add_process a fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control
    add_fifo a/a_in "$(end_of a)" outside "" "-inf"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: fifo a/a_in is defined by process a through the input option -inf: a fifo is defined by the process that writes it"* ]]
}

@test "debasher::_validate_program_fifo_kinds refuses a tagged fifo fed from outside defined through an output option" {
    set_up_registries
    add_process a fbpprocess
    add_fifo a/a_trigger "$(end_of a)" outside control "-outtrigger"

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: fifo a/a_trigger is tagged --control and fed from outside the program, so process a reads it, but defines it through the output option -outtrigger"* ]]
}

@test "debasher::_validate_program_fifo_kinds refuses a fifo tag in a general program" {
    set_up_registries
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"
    add_fifo p/p_in "$(end_of p)" outside external

    run debasher::_validate_program_fifo_kinds
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: fifo p/p_in is tagged --external, which only a 'resident' program may use"* ]]
}

@test "debasher::_register_resident_task_ports gives each node of the chaos reference program its ports, and the Supervisor its business channels" {
    set_up_registries
    add_process fanin fbpprocess
    add_process loop fbpprocess
    add_process sink fbpprocess
    add_process sup supervisor
    add_fifo sup/sup_trig_fanin "$(end_of sup)" "$(end_of fanin)" control -outtrig_fanin -trigger
    add_fifo sup/sup_manual "$(end_of sup)" outside control -manual
    add_fifo fanin/fanin_ext "$(end_of fanin)" outside external -ext
    add_fifo fanin/fanin_to_loop "$(end_of fanin)" "$(end_of loop)" "" -outloop -from_fanin
    add_fifo loop/loop_to_fanin "$(end_of loop)" "$(end_of fanin)" "" -outfanin -loop_in
    add_fifo fanin/fanin_to_sink "$(end_of fanin)" "$(end_of sink)" "" -outsink -from_fanin
    add_fifo fanin/fanin_hb "$(end_of fanin)" "$(end_of sup)" "" -outhb -hb_fanin
    add_fifo loop/loop_hb "$(end_of loop)" "$(end_of sup)" "" -outhb -hb_loop
    add_fifo sink/sink_hb "$(end_of sink)" "$(end_of sup)" "" -outhb -hb_sink

    debasher::_register_resident_task_ports
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of fanin)]}" = "input=ext,loop_in,trigger;output=outhb,outloop,outsink;control=trigger;external=ext;supervisor=outhb" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of loop)]}" = "input=from_fanin;output=outfanin,outhb;control=;external=;supervisor=outhb" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of sink)]}" = "input=from_fanin;output=outhb;control=;external=;supervisor=outhb" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of sup)]}" = "nodes=fanin=hb_fanin,loop=hb_loop,sink=hb_sink;trigger=outtrig_fanin;manual_trigger=manual;startup=;hold=fanin/fanin_to_loop,fanin/fanin_to_sink,loop/loop_to_fanin" ]
}

@test "debasher::_register_resident_task_ports gives each task of an array its own ports, and a node with none an entry" {
    set_up_registries
    add_process start fbpprocess
    add_process worker fbpprocess 2
    add_process idle fbpprocess
    add_fifo start/start_trigger "$(end_of start)" outside control --trigger
    add_fifo start/start_out_0 "$(end_of start)" "$(end_of worker 0)" "" -outf0 -inf
    add_fifo start/start_out_1 "$(end_of start)" "$(end_of worker 1)" "" -outf1 -inf
    add_fifo worker/worker_out_0 "$(end_of worker 0)" outside "" -outf
    add_fifo worker/worker_out_1 "$(end_of worker 1)" "$(end_of worker 0)" "" -outg -peer

    debasher::_register_resident_task_ports
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of start)]}" = "input=trigger;output=outf0,outf1;control=trigger;external=;supervisor=" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of worker 0)]}" = "input=inf,peer;output=outf;control=;external=;supervisor=" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of worker 1)]}" = "input=inf;output=outg;control=;external=;supervisor=" ]
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of idle)]}" = "input=;output=;control=;external=;supervisor=" ]
}

@test "debasher::_register_resident_task_ports names a task of an array in the Supervisor's ports by its index" {
    set_up_registries
    add_process start fbpprocess
    add_process worker fbpprocess 2
    add_process sup supervisor
    add_fifo sup/sup_trig "$(end_of sup)" "$(end_of start)" control -outtrig -trigger
    add_fifo start/start_hb "$(end_of start)" "$(end_of sup)" "" -outhb -hb_start
    add_fifo worker/worker_hb_0 "$(end_of worker 0)" "$(end_of sup)" "" -outhb -hb_worker0
    add_fifo worker/worker_hb_1 "$(end_of worker 1)" "$(end_of sup)" "" -outhb -hb_worker1

    debasher::_register_resident_task_ports
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of sup)]}" = "nodes=start=hb_start,worker:0=hb_worker0,worker:1=hb_worker1;trigger=outtrig;manual_trigger=;startup=;hold=" ]
}

@test "debasher::_register_resident_task_ports gives the Supervisor the startup deadline of each node that sets one" {
    set_up_registries
    add_process slow fbpprocess
    add_process worker fbpprocess 2
    add_process quick fbpprocess
    add_process sup supervisor
    DEBASHER_INITIAL_PROCESS_SPEC["slow"]="slow cpus=1; mem=32; time=00:10:00; startup_timeout_s=120"
    DEBASHER_INITIAL_PROCESS_SPEC["worker"]="worker cpus=1 mem=32 time=00:10:00 startup_timeout_s=45"
    DEBASHER_INITIAL_PROCESS_SPEC["quick"]="quick cpus=1 mem=32 time=00:10:00"
    add_fifo slow/slow_hb "$(end_of slow)" "$(end_of sup)" "" -outhb -hb_slow
    add_fifo worker/worker_hb_0 "$(end_of worker 0)" "$(end_of sup)" "" -outhb -hb_worker0
    add_fifo worker/worker_hb_1 "$(end_of worker 1)" "$(end_of sup)" "" -outhb -hb_worker1
    add_fifo quick/quick_hb "$(end_of quick)" "$(end_of sup)" "" -outhb -hb_quick

    debasher::_register_resident_task_ports
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of sup)]}" = "nodes=quick=hb_quick,slow=hb_slow,worker:0=hb_worker0,worker:1=hb_worker1;trigger=;manual_trigger=;startup=slow=120,worker:0=45,worker:1=45;hold=" ]
}

@test "debasher::_register_resident_task_ports gives the Supervisor every channel between two nodes, a task of an array or a self-loop too, and no other fifo" {
    set_up_registries
    add_process start fbpprocess
    add_process worker fbpprocess 2
    add_process counter fbpprocess
    add_process sup supervisor
    add_fifo sup/sup_trig "$(end_of sup)" "$(end_of start)" control -outtrig -trigger
    add_fifo start/start_ext "$(end_of start)" outside external -ext
    add_fifo start/start_out_0 "$(end_of start)" "$(end_of worker 0)" "" -outf0 -inf
    add_fifo start/start_out_1 "$(end_of start)" "$(end_of worker 1)" "" -outf1 -inf
    add_fifo worker/worker_out_0 "$(end_of worker 0)" outside "" -outf
    add_fifo worker/worker_out_1 "$(end_of worker 1)" "$(end_of worker 0)" "" -outg -peer
    add_fifo counter/counter_self "$(end_of counter)" "$(end_of counter)" "" -outself -self
    add_fifo start/start_hb "$(end_of start)" "$(end_of sup)" "" -outhb -hb_start

    debasher::_register_resident_task_ports
    [ "${DEBASHER_RESIDENT_TASK_PORTS[$(end_of sup)]}" = "nodes=start=hb_start;trigger=outtrig;manual_trigger=;startup=;hold=counter/counter_self,start/start_out_0,start/start_out_1,worker/worker_out_1" ]
}

@test "debasher::_register_resident_task_ports refuses a Supervisor with two manual triggers" {
    set_up_registries
    add_process a fbpprocess
    add_process sup supervisor
    add_fifo sup/sup_manual "$(end_of sup)" outside control -manual
    add_fifo sup/sup_manual2 "$(end_of sup)" outside control -manual2

    run debasher::_register_resident_task_ports
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: the Supervisor sup has more than one manual trigger fed from outside the program (manual,manual2)"* ]]
}

@test "debasher::_register_resident_task_ports refuses a fifo of the Supervisor that is not a trigger" {
    set_up_registries
    add_process a fbpprocess
    add_process sup supervisor
    add_fifo sup/sup_to_a "$(end_of sup)" "$(end_of a)" "" -outa -in

    run debasher::_register_resident_task_ports
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: the Supervisor sup defines fifo sup/sup_to_a, but the only fifos a Supervisor defines are its triggers to nodes and its manual trigger fed from outside the program, both tagged --control"* ]]
}

@test "debasher::_register_resident_task_ports refuses a node with two outputs read by the Supervisor" {
    set_up_registries
    add_process a fbpprocess
    add_process sup supervisor
    add_fifo a/a_hb "$(end_of a)" "$(end_of sup)" "" -outhb -hb_a
    add_fifo a/a_hb2 "$(end_of a)" "$(end_of sup)" "" -outhb2 -hb_a2

    run debasher::_register_resident_task_ports
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Error: node a has more than one output read by the Supervisor (outhb,outhb2)"* ]]
}

@test "debasher::_register_resident_task_ports is a no-op for a general program" {
    set_up_registries
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"
    add_process a fbpprocess
    add_fifo a/a_out "$(end_of a)" outside

    debasher::_register_resident_task_ports
    [ "${#DEBASHER_RESIDENT_TASK_PORTS[@]}" -eq 0 ]
}

@test "debasher::define_fifo_opt records the tag of the fifo" {
    set_up_registries
    DEBASHER_PROGRAM_OUTDIR="${BATS_TEST_TMPDIR}"
    tagproc_define_opts() {
        local optlist=""
        define_fifo_opt "-trigger" "tagproc_trigger" optlist --control
        define_fifo_opt "-ext" "tagproc_ext" optlist --external
        define_fifo_opt "-out" "tagproc_out" optlist
    }
    tagproc_define_opts

    [ "${DEBASHER_FIFO_KINDS["tagproc/tagproc_trigger"]}" = "control" ]
    [ "${DEBASHER_FIFO_KINDS["tagproc/tagproc_ext"]}" = "external" ]
    [ -z "${DEBASHER_FIFO_KINDS["tagproc/tagproc_out"]+x}" ]
    [ "${DEBASHER_FIFO_OWNER_OPTS["tagproc/tagproc_trigger"]}" = "-trigger" ]
    [ "${DEBASHER_FIFO_OWNER_OPTS["tagproc/tagproc_out"]}" = "-out" ]
}

@test "debasher::define_fifo_opt refuses both tags on one fifo, and an unknown flag" {
    set_up_registries
    DEBASHER_PROGRAM_OUTDIR="${BATS_TEST_TMPDIR}"
    bothproc_define_opts() {
        local optlist=""
        define_fifo_opt "-x" "bothproc_x" optlist --control --external
    }
    run bothproc_define_opts
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"define_fifo_opt: Error, a fifo takes at most one of --control and --external"* ]]

    unknownproc_define_opts() {
        local optlist=""
        define_fifo_opt "-x" "unknownproc_x" optlist --bogus
    }
    run unknownproc_define_opts
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"define_fifo_opt: Error, unknown flag --bogus"* ]]
}

@test "debasher::define_opt_from_proc_out refuses to connect to an option that is not an output" {
    run debasher::define_opt_from_proc_out "-from_fanin" "fanin" "-to_loop" optlist
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"connected process option should start with -out or --out"* ]]

    local optlist=""
    debasher::define_opt_from_proc_out "-from_fanin" "fanin" "-outloop" optlist
    [ -n "${optlist}" ]
}

# --- resuming a resident program -------------------------------------------

# $1: status that debasher::_get_process_status reports for every process,
# by name, as "<process>=<status> ..."
fake_statuses() {
    FAKE_STATUSES="$1"
    debasher::_get_process_status() {
        local entry
        for entry in ${FAKE_STATUSES}; do
            if [ "${entry%%=*}" = "$2" ]; then
                echo "${entry#*=}"
                return 0
            fi
        done
    }
}

@test "debasher::_define_rerun_processes_due_to_resident_resume marks every stopped process of a resident program" {
    declare -gA DEBASHER_RERUN_PROCESSES=()
    DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_RESIDENT}"
    DEBASHER_PROGRAM_PROCESSES=([halted]=1 [partial]=1 [running]=1 [crashed]=1 [new]=1)
    fake_statuses "halted=${DEBASHER_FINISHED_PROCESS_STATUS} partial=${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS} running=${DEBASHER_INPROGRESS_PROCESS_STATUS} crashed=${DEBASHER_UNFINISHED_PROCESS_STATUS} new=${DEBASHER_TODO_PROCESS_STATUS}"

    debasher::_define_rerun_processes_due_to_resident_resume "/unused"

    [ "${DEBASHER_RERUN_PROCESSES[halted]}" = "${DEBASHER_RESIDENT_RESUME_RERUN_REASON}" ]
    [ "${DEBASHER_RERUN_PROCESSES[partial]}" = "${DEBASHER_RESIDENT_RESUME_RERUN_REASON}" ]
    # Also an array with only some tasks finished, which the engine reports
    # as unfinished
    [ "${DEBASHER_RERUN_PROCESSES[crashed]}" = "${DEBASHER_RESIDENT_RESUME_RERUN_REASON}" ]
    # Not to be touched (running) or launched anyway (new)
    [ -z "${DEBASHER_RERUN_PROCESSES[running]:-}" ]
    [ -z "${DEBASHER_RERUN_PROCESSES[new]:-}" ]
}

@test "debasher::_define_rerun_processes_due_to_resident_resume is a no-op for a general program" {
    declare -gA DEBASHER_RERUN_PROCESSES=()
    DEBASHER_PROGRAM_PROCESSES=([done]=1)
    fake_statuses "done=${DEBASHER_FINISHED_PROCESS_STATUS}"

    debasher::_define_rerun_processes_due_to_resident_resume "/unused"

    [ "${#DEBASHER_RERUN_PROCESSES[@]}" -eq 0 ]
}
