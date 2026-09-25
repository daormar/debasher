#!/usr/bin/env bats
#
# Unit tests for engine/debasher_lib_resident_tools.sh, what the tools that
# act on a running resident program from outside it share: the files of a
# node, the trigger they write into the control ports of every node, and the
# check that a round closed at a node. Real files and fifos in a scratch
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
    DEBASHER_RESIDENT_TOOL_NODES=(solo arr:0)

    cat "${fifo}" > "${BATS_TEST_TMPDIR}/received" &
    local reader=$!

    local deadline=$(( $(date +%s) + 10 ))
    debasher::_resident_tool_trigger_every_node "${outdir}" start_snapshot 777 "${deadline}"
    wait "${reader}"

    [ "$(cat "${BATS_TEST_TMPDIR}/received")" = "$(debasher::_resident_tool_trigger_json start_snapshot 777)" ]
}

@test "a node that never writes its control_ports file is an error at the deadline" {
    DEBASHER_RESIDENT_TOOL_NODES=(solo)
    local deadline=$(( $(date +%s) + 1 ))
    run debasher::_resident_tool_trigger_every_node "${outdir}" start_snapshot 777 "${deadline}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"solo never wrote its control_ports file"* ]]
}

@test "a control port with no reader is an error, not a hang" {
    local fifo="${BATS_TEST_TMPDIR}/solo_trigger"
    mkfifo "${fifo}"
    echo "${fifo}" > "${outdir}/__exec__/solo/control_ports"
    DEBASHER_RESIDENT_TOOL_NODES=(solo)

    local deadline=$(( $(date +%s) + 10 ))
    run debasher::_resident_tool_trigger_every_node "${outdir}" start_snapshot 777 "${deadline}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"could not write the start_snapshot trigger to ${fifo}"* ]]
}
