#!/usr/bin/env bats
#
# Unit tests for engine/debasher_lib_resident_tools.sh, what the tools that
# act on a running resident program from outside it share: the discovery of
# the nodes, the files of a node, the trigger they write into the control
# ports of every node, and the check that a round closed at a node. Real files and fifos in a scratch
# output directory, no running program: the tools themselves are exercised
# by real runs in test_stop_resident.py and test_snapshot_resident.py.

# A test that hangs fails instead of hanging the whole suite: a write into a
# fifo with no reader is exactly what some of these tests guard against.
BATS_TEST_TIMEOUT=30

setup() {
    : "${ENGINE_BUILDDIR:?ENGINE_BUILDDIR must point at the built engine/ dir}"
    debasher_pkglibdir="${ENGINE_BUILDDIR}"

    # Normally supplied by the tool-path preamble the Makefile suffix rule
    # prepends, absent here since this sources the plain .sh sources
    # directly (see lib_programs.bats for why).
    SLEEP="$(command -v sleep)"
    CAT="$(command -v cat)"
    TIMEOUT="$(command -v timeout)"

    source "${ENGINE_BUILDDIR}/debasher_lib.sh"
    source "${ENGINE_BUILDDIR}/debasher_lib_resident_tools.sh"

    outdir="${BATS_TEST_TMPDIR}/out"
    mkdir -p "${outdir}/__exec__/solo" "${outdir}/__exec__/arr"
}

# --- the files of a node ------------------------------------------------

@test "a plain node names its process and has no task index" {
    [ "$(debasher::_resident_tool_node_processname solo)" = "solo" ]
    [ -z "$(debasher::_resident_tool_node_task_idx solo)" ]
}

@test "a task of an array names its process and its index" {
    [ "$(debasher::_resident_tool_node_processname arr:2)" = "arr" ]
    [ "$(debasher::_resident_tool_node_task_idx arr:2)" = "2" ]
}

@test "the execdir entry of a task carries its index, that of a plain node does not" {
    [ "$(debasher::_resident_tool_node_execdir_entry "${outdir}" solo checkpoints)" = "${outdir}/__exec__/solo/checkpoints" ]
    [ "$(debasher::_resident_tool_node_execdir_entry "${outdir}" arr:2 checkpoints)" = "${outdir}/__exec__/arr/checkpoints_2" ]
}

# --- debasher::_resident_tool_trigger_json -------------------------------

@test "the trigger carries its command and its epoch" {
    run debasher::_resident_tool_trigger_json start_snapshot 1700000000123
    [ "${status}" -eq 0 ]
    [ "${output}" = '{"type": "INTERACT", "payload": {"command": "start_snapshot", "args": {"epoch": 1700000000123}}}' ]
}

# --- debasher::_resident_tool_node_has_checkpoint_since ------------------

@test "a checkpoint of the round itself means it closed" {
    mkdir -p "${outdir}/__exec__/solo/checkpoints"
    touch "${outdir}/__exec__/solo/checkpoints/500.json"
    debasher::_resident_tool_node_has_checkpoint_since "${outdir}" solo 500
}

@test "a checkpoint of a newer round is as good as one of the round itself" {
    mkdir -p "${outdir}/__exec__/solo/checkpoints"
    touch "${outdir}/__exec__/solo/checkpoints/400.json" "${outdir}/__exec__/solo/checkpoints/600.json"
    debasher::_resident_tool_node_has_checkpoint_since "${outdir}" solo 500
}

@test "only older checkpoints mean the round has not closed" {
    mkdir -p "${outdir}/__exec__/solo/checkpoints"
    touch "${outdir}/__exec__/solo/checkpoints/400.json" "${outdir}/__exec__/solo/checkpoints/499.json"
    run debasher::_resident_tool_node_has_checkpoint_since "${outdir}" solo 500
    [ "${status}" -eq 1 ]
}

@test "a checkpoint still being written does not count" {
    mkdir -p "${outdir}/__exec__/solo/checkpoints"
    touch "${outdir}/__exec__/solo/checkpoints/500.json.tmp"
    run debasher::_resident_tool_node_has_checkpoint_since "${outdir}" solo 500
    [ "${status}" -eq 1 ]
}

@test "a node with no checkpoints directory has not closed the round" {
    run debasher::_resident_tool_node_has_checkpoint_since "${outdir}" solo 500
    [ "${status}" -eq 1 ]
}

@test "the checkpoints of a task are its own, not those of another task" {
    mkdir -p "${outdir}/__exec__/arr/checkpoints_0" "${outdir}/__exec__/arr/checkpoints_1"
    touch "${outdir}/__exec__/arr/checkpoints_0/500.json"
    debasher::_resident_tool_node_has_checkpoint_since "${outdir}" arr:0 500
    run debasher::_resident_tool_node_has_checkpoint_since "${outdir}" arr:1 500
    [ "${status}" -eq 1 ]
}

# --- debasher::_resident_tool_trigger_every_node -------------------------

@test "the trigger reaches the control port of every node that has one" {
    local fifo="${BATS_TEST_TMPDIR}/solo_trigger"
    mkfifo "${fifo}"
    echo "${fifo}" > "${outdir}/__exec__/solo/control_ports"
    : > "${outdir}/__exec__/arr/control_ports_0"
    local -a nodes=(solo arr:0)

    cat "${fifo}" > "${BATS_TEST_TMPDIR}/received" &
    local reader=$!

    local deadline=$(( $(date +%s) + 10 ))
    debasher::_resident_tool_trigger_every_node "${outdir}" nodes start_snapshot 777 "${deadline}"
    wait "${reader}"

    [ "$(cat "${BATS_TEST_TMPDIR}/received")" = "$(debasher::_resident_tool_trigger_json start_snapshot 777)" ]
}

@test "a node that never writes its control_ports file is an error at the deadline" {
    local -a nodes=(solo)
    local deadline=$(( $(date +%s) + 1 ))
    run debasher::_resident_tool_trigger_every_node "${outdir}" nodes start_snapshot 777 "${deadline}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"solo never wrote its control_ports file"* ]]
}

@test "a control port with no reader is an error, not a hang" {
    local fifo="${BATS_TEST_TMPDIR}/solo_trigger"
    mkfifo "${fifo}"
    echo "${fifo}" > "${outdir}/__exec__/solo/control_ports"
    local -a nodes=(solo)

    local deadline=$(( $(date +%s) + 10 ))
    run debasher::_resident_tool_trigger_every_node "${outdir}" nodes start_snapshot 777 "${deadline}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"could not write the start_snapshot trigger to ${fifo}"* ]]
}

# --- debasher::_resident_tool_find_supervisor_and_nodes ------------------

# The program of these tests, with no module loaded: the processes named in
# the arguments (solo, arr and sup by default), their roles and their
# scripts with the number of tasks, as the scheduler writes it. "never" has
# no script. The array is declared again as a global: declared by
# debasher_lib.sh, sourced inside setup(), it is local to setup().
_set_up_program() {
    unset DEBASHER_PROGRAM_PROCESSES
    declare -gA DEBASHER_PROGRAM_PROCESSES=()
    local -a names=("$@")
    [ $# -gt 0 ] || names=(solo arr sup)
    local name
    for name in "${names[@]}"; do
        DEBASHER_PROGRAM_PROCESSES["${name}"]=1
    done
    debasher::_classify_resident_process_role() {
        case "$1" in
            sup|sup2) echo supervisor ;;
            solo|arr|never) echo fbpprocess ;;
            *) echo other ;;
        esac
    }
    mkdir -p "${outdir}/__exec__/sup"
    echo "DEBASHER_NUM_TASKS=1" > "${outdir}/__exec__/solo/solo"
    echo "DEBASHER_NUM_TASKS=3" > "${outdir}/__exec__/arr/arr"
    echo "DEBASHER_NUM_TASKS=1" > "${outdir}/__exec__/sup/sup"
}

@test "a process of one task is a node by its name, each task of one of several is a node of its own" {
    _set_up_program
    local supervisor
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(date +%s)" supervisor nodes
    [ "${supervisor}" = "sup" ]
    [ "$(printf '%s\n' "${nodes[@]}" | sort | tr '\n' ' ')" = "arr:0 arr:1 arr:2 solo " ]
}

@test "a task not started yet counts, since the number of tasks comes from the script" {
    _set_up_program
    # No .id for any task: none of them has started
    local supervisor
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(date +%s)" supervisor nodes
    [[ " ${nodes[*]} " == *" arr:2 "* ]]
}

@test "-x leaves out every task of a process, or one task" {
    _set_up_program
    local supervisor
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "solo,arr:1" "$(date +%s)" supervisor nodes
    [ "$(printf '%s\n' "${nodes[@]}" | sort | tr '\n' ' ')" = "arr:0 arr:2 " ]
    debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "arr" "$(date +%s)" supervisor nodes
    [ "${nodes[*]}" = "solo" ]
}

@test "a program without a Supervisor gives an empty one" {
    _set_up_program solo
    local supervisor=previous
    local -a nodes=()
    debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(date +%s)" supervisor nodes
    [ -z "${supervisor}" ]
    [ "${nodes[*]}" = "solo" ]
}

@test "two Supervisors are an error" {
    _set_up_program sup sup2
    local supervisor
    local -a nodes=()
    run debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(date +%s)" supervisor nodes
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"at most one Supervisor process"* ]]
}

@test "a process that is neither a node nor a Supervisor is an error" {
    _set_up_program plain
    local supervisor
    local -a nodes=()
    run debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(date +%s)" supervisor nodes
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"plain does not derive from FBPProcess or Supervisor"* ]]
}

@test "a script that does not come before the deadline is an error" {
    _set_up_program never
    local supervisor
    local -a nodes=()
    run debasher::_resident_tool_find_supervisor_and_nodes "${outdir}" "" "$(( $(date +%s) + 1 ))" supervisor nodes
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"never was never launched"* ]]
}

# --- debasher::_resident_tool_some_node_is_running -----------------------

@test "whether some node is running is asked of the processes of the nodes given" {
    debasher::_process_is_in_progress() {
        echo "$2" >> "${BATS_TEST_TMPDIR}/asked"
        [ "$2" = "arr" ]
    }
    local -a nodes=(solo arr:1)
    debasher::_resident_tool_some_node_is_running "${outdir}" nodes
    [ "$(cat "${BATS_TEST_TMPDIR}/asked" | tr '\n' ' ')" = "solo arr " ]

    local -a idle=(solo)
    run debasher::_resident_tool_some_node_is_running "${outdir}" idle
    [ "${status}" -eq 1 ]
}
