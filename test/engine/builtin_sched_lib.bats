#!/usr/bin/env bats
#
# Unit tests for debasher_builtin_sched::_launch
# (engine/debasher_builtin_sched_lib.sh), the built-in scheduler's own
# launch function. It is also what debasher_launch_process (used by a
# Supervisor to relaunch a downed node) calls, so a relaunch behaves
# exactly like the original launch. The tests use a tiny fake process
# script that records what it saw in its environment; _launch itself
# writes its PID to the .id file.

setup() {
    : "${ENGINE_BUILDDIR:?ENGINE_BUILDDIR must point at the built engine/ dir}"
    debasher_pkglibdir="${ENGINE_BUILDDIR}"

    # Tool-path variables the real preamble provides (see
    # test/engine/lib_programs.bats for why they are set by hand here).
    BASENAME="$(command -v basename)"
    PYTHON="$(command -v python3)"
    RM="$(command -v rm)"
    CAT="$(command -v cat)"
    MV="$(command -v mv)"
    debasher_pythondir="/fake/pythondir"
    debasher_pkgpythondir="/fake/pkgpythondir"
    debasher_libexecdir="/fake/libexecdir"

    source "${ENGINE_BUILDDIR}/debasher_lib.sh"
    source "${ENGINE_BUILDDIR}/debasher_builtin_sched_lib.sh"

    OUTDIR="${BATS_TEST_TMPDIR}/outdir"
    EXECDIR="${OUTDIR}/__exec__/proc"
    mkdir -p "${EXECDIR}"

    SCRIPT="${EXECDIR}/proc"
    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
# Short delay before doing anything, so that a .id found right after
# _launch returns was written by _launch, not by the script.
sleep 0.02
{
    echo "pid=$$"
    echo "pgid=$(ps -o pgid= -p $$ | tr -d ' ')"
    echo "task=${BUILTIN_ARRAY_TASK_ID}"
    echo "libexec=${DEBASHER_LIBEXECDIR}"
} > "$(dirname "$0")/seen.tmp"
mv "$(dirname "$0")/seen.tmp" "$(dirname "$0")/seen.txt"
EOF
    chmod +x "${SCRIPT}"
}

# The launched script keeps running after _launch returns, so wait for
# its own report instead of reading it right away.
wait_for_report() {
    local i
    for i in $(seq 1 100); do
        [ -f "${EXECDIR}/seen.txt" ] && return 0
        sleep 0.05
    done
    return 1
}

@test "_launch writes the launched process's own PID into its .id file" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report
    # The PID that _launch records must be the script's own $$, the leader
    # of its process group, which debasher::_stop_pid kills as a group.
    [ "$(cat "${EXECDIR}/proc.id")" = "$(grep '^pid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" ]
}

@test "_launch returns with the new PID already in the .id file, replacing a stale one" {
    echo 999999 > "${EXECDIR}/proc.id"
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    # Checked right away, before the script has done anything (it sleeps
    # first): the new PID is there as soon as _launch returns.
    local pid
    pid="$(cat "${EXECDIR}/proc.id")"
    [ -n "${pid}" ]
    [ "${pid}" != "999999" ]
    [ ! -e "${EXECDIR}/proc.id.tmp" ]
    wait_for_report
    [ "${pid}" = "$(grep '^pid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" ]
}

@test "_launch does not wait for a script that is slow to start" {
    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
sleep 2
EOF
    chmod +x "${SCRIPT}"
    local start=${SECONDS}
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    [ $((SECONDS - start)) -lt 2 ]
    local pid
    pid="$(cat "${EXECDIR}/proc.id")"
    kill -0 "${pid}"
    kill -9 -- "-${pid}"
    wait "${pid}" 2>/dev/null || true
}

@test "_launch kills the previous incarnation named by a stale but still-alive .id file" {
    # A relaunch triggered by a missed heartbeat does not prove the old
    # incarnation is actually gone: leave a real, still-running process
    # behind it, in its own process group (as a real launch would).
    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
sleep 100
EOF
    chmod +x "${SCRIPT}"
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    OLD_PID="$(cat "${EXECDIR}/proc.id")"
    kill -0 "${OLD_PID}"

    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
sleep 0.02
{
    echo "pid=$$"
} > "$(dirname "$0")/seen.tmp"
mv "$(dirname "$0")/seen.tmp" "$(dirname "$0")/seen.txt"
EOF
    chmod +x "${SCRIPT}"

    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report

    run kill -0 "${OLD_PID}"
    [ "$status" -ne 0 ]
}

@test "_launch names the .id file after the task index for an array task and exports the index" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc 3
    wait_for_report
    [ -f "${EXECDIR}/proc_3.id" ]
    [ ! -f "${EXECDIR}/proc.id" ]
    grep -q '^task=3$' "${EXECDIR}/seen.txt"
}

@test "_launch exports task 0 for a process that is not an array" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report
    grep -q '^task=0$' "${EXECDIR}/seen.txt"
}

@test "_launch tells the launched process where libexec is" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report
    grep -q '^libexec=/fake/libexecdir$' "${EXECDIR}/seen.txt"
}

@test "_launch starts the process as the leader of its own process group" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report
    [ "$(grep '^pid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" = "$(grep '^pgid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" ]
}

@test "_launch leaves BUILTIN_ARRAY_TASK_ID unset in the caller" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc 2
    wait_for_report
    [ -z "${BUILTIN_ARRAY_TASK_ID+x}" ]

    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    [ -z "${BUILTIN_ARRAY_TASK_ID+x}" ]
}

@test "_print_script_trap emits a trap that ignores TERM" {
    [ "$(debasher_builtin_sched::_print_script_trap)" = "trap '' TERM" ]
}

@test "a launched script survives SIGTERM to its own process group, unlike one without the trap" {
    # _create_script puts _print_script_trap's line first, before anything
    # else runs (see debasher_builtin_sched::_create_script): a graceful
    # stop signals the whole group (the same group debasher_stop already
    # reaches with SIGKILL, see debasher::_stop_pid), not a lone PID, so it
    # reaches a resident process's own Python interpreter wherever it sits
    # in the fork tree; without this, that broadcast would kill the
    # process-group leader itself before it ever gets to write .finished.
    cat > "${SCRIPT}" <<EOF
#!/bin/bash
$(debasher_builtin_sched::_print_script_trap)
sleep 5 &
child=\$!
wait "\${child}"
echo "pid=\$\$" > "$(dirname "${SCRIPT}")/seen.tmp"
mv "$(dirname "${SCRIPT}")/seen.tmp" "$(dirname "${SCRIPT}")/seen.txt"
EOF
    chmod +x "${SCRIPT}"

    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    local pid
    pid=$(cat "${EXECDIR}/proc.id")
    [ -n "${pid}" ]

    kill -TERM -- "-${pid}"

    # If the trap had not protected it, this signal would have killed the
    # wrapper itself at once, and it would never reach the line that
    # writes seen.txt: its own child dying from the same broadcast (no
    # trap of its own) is what lets "wait" return and the script go on,
    # the same way a resident process's Python interpreter exiting
    # cleanly (see FBPProcess's own SIGTERM handler) lets the real script
    # go on to _signal_process_completion and write .finished.
    wait_for_report
    [ "$(grep '^pid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" = "${pid}" ]
}

@test "_get_process_comp_specs returns the computational specs of the process" {
    source "${ENGINE_BUILDDIR}/debasher_lib_process_spec.sh"
    declare -gA DEBASHER_INITIAL_PROCESS_SPEC
    DEBASHER_INITIAL_PROCESS_SPEC[proc]="proc cpus=1; mem=32; time=00:01:00; out_backlog_fail_mb=16 ||| force=yes"
    [ "$(debasher::_get_process_comp_specs proc)" = "cpus=1; mem=32; time=00:01:00; out_backlog_fail_mb=16" ]
}

@test "the spec check refuses a resident limit that is not a positive number, and accepts one that is" {
    source "${ENGINE_BUILDDIR}/debasher_lib_process_spec.sh"
    run debasher::_program_process_spec_is_ok "proc cpus=1; mem=32; time=00:01:00; out_backlog_fail_mb=0 ||| "
    [ "$status" -ne 0 ]
    [[ "$output" == *"out_backlog_fail_mb"*"positive number"* ]]

    run debasher::_program_process_spec_is_ok "proc cpus=1; mem=32; time=00:01:00; gil_switch_interval_ms=0.5 ||| "
    [ "$status" -eq 0 ]

    run debasher::_program_process_spec_is_ok "proc cpus=1 mem=32 time=00:01:00 input_log_max_mb=big ||| "
    [ "$status" -ne 0 ]
}

@test "the spec check accepts a known scheduler for the batch runs of a launcher node, and refuses another" {
    source "${ENGINE_BUILDDIR}/debasher_lib_process_spec.sh"
    run debasher::_program_process_spec_is_ok "proc cpus=1; mem=32; time=00:01:00; batch_sched=BUILTIN ||| "
    [ "$status" -eq 0 ]

    run debasher::_program_process_spec_is_ok "proc cpus=1; mem=32; time=00:01:00; batch_sched=SLURM ||| "
    [ "$status" -eq 0 ]

    run debasher::_program_process_spec_is_ok "proc cpus=1; mem=32; time=00:01:00; batch_sched=PBS ||| "
    [ "$status" -ne 0 ]
    [[ "$output" == *"batch_sched"*"BUILTIN or SLURM"* ]]
}

# --- process registration and task selection ------------------------------

@test "_update_processname_to_idx_info registers a process once, without errors on a second call" {
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX=() DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME=()

    run bash -c "$(declare -p DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME); $(declare -f debasher_builtin_sched::_update_processname_to_idx_info);
        debasher_builtin_sched::_update_processname_to_idx_info a
        debasher_builtin_sched::_update_processname_to_idx_info b
        debasher_builtin_sched::_update_processname_to_idx_info a
        echo \"\${DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[a]} \${DEBASHER_BUILTIN_SCHED_PROCESSNAME_TO_IDX[b]} \${#DEBASHER_BUILTIN_SCHED_IDX_TO_PROCESSNAME[@]}\""
    [ "${status}" -eq 0 ]
    [ "${output}" = "0 1 2" ]
}

@test "_get_max_num_tasks allows every task of an array without a throttle" {
    # debasher_lib.sh declares it with a bare declare, local to setup()
    declare -g DEBASHER_ARRAY_TASK_NOTHROTTLE=0
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE=(["arr"]="${DEBASHER_ARRAY_TASK_NOTHROTTLE}")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["arr"]=7)

    run debasher_builtin_sched::_get_max_num_tasks "${OUTDIR}" arr
    [ "${status}" -eq 0 ]
    [ "${output}" = "7" ]
}

# --- knapsack constraints -------------------------------------------------

@test "_print_knapsack_pred_spec pairs the two ends of a fifo and skips a fifo with an external end" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0" ["e/g"]="e${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0" ["e/g"]="${DEBASHER_EXTERNAL_FIFO_END}")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["w"]=1 ["r"]=1 ["e"]=1)
    debasher_builtin_sched::_get_knapsack_name() {
        echo "k_$1"
    }

    run debasher_builtin_sched::_print_knapsack_pred_spec
    [ "${status}" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]
    [[ " ${lines[*]} " == *"k_r k_w"* ]]
    [[ " ${lines[*]} " == *"k_w k_r"* ]]
    [[ "${output}" != *"unary operator"* ]]
}

@test "_hold_back_fifo_ends_without_peer leaves out an end whose other end waits for a process to end" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["r"]="afterok:x")
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["w"]=1 ["r"]=1 ["x"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["w"]="TO-DO" ["r"]="TO-DO" ["x"]="TO-DO")
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["w"]="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}" ["x"]="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ -z "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[w]+x}" ]
    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[x]+x}" ]
}

@test "_hold_back_fifo_ends_without_peer keeps both ends when both are candidates, and an end whose other end runs" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=()
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0" ["v/g"]="v${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0" ["v/g"]="s${sep}0")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["w"]=1 ["r"]=1 ["v"]=1 ["s"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["w"]="TO-DO" ["r"]="TO-DO" ["v"]="IN-PROGRESS" ["s"]="TO-DO")
    local none="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["w"]="${none}" ["r"]="${none}" ["s"]="${none}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[w]+x}" ]
    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[r]+x}" ]
    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[s]+x}" ]
}

@test "_hold_back_fifo_ends_without_peer follows a chain of fifos and keeps an end whose other end is outside" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["c"]="afterok:x")
    # a -> b -> c, and c waits for a dependency; e writes out of the program
    declare -gA DEBASHER_PROGRAM_FIFOS=(["a/f"]="a${sep}0" ["b/g"]="b${sep}0" ["e/h"]="e${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["a/f"]="b${sep}0" ["b/g"]="c${sep}0" ["e/h"]="${DEBASHER_EXTERNAL_FIFO_END}")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["a"]=1 ["b"]=1 ["c"]=1 ["e"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["a"]="TO-DO" ["b"]="TO-DO" ["c"]="TO-DO" ["e"]="TO-DO")
    local none="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["a"]="${none}" ["b"]="${none}" ["e"]="${none}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ -z "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[a]+x}" ]
    [ -z "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[b]+x}" ]
    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[e]+x}" ]
}

@test "_hold_back_fifo_ends_without_peer removes only the task of an array whose other end cannot start" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["r1"]="afterok:x")
    declare -gA DEBASHER_PROGRAM_FIFOS=(["arr/f0"]="arr${sep}0" ["arr/f1"]="arr${sep}1")
    declare -gA DEBASHER_FIFO_READERS=(["arr/f0"]="r0${sep}0" ["arr/f1"]="r1${sep}0")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["arr"]=3 ["r0"]=1 ["r1"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["arr"]="TO-DO" ["r0"]="TO-DO" ["r1"]="TO-DO")
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["arr"]="0 1 2" ["r0"]="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[arr]}" = "0 2" ]
    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[r0]+x}" ]
}

@test "_hold_back_fifo_ends_without_peer keeps an end whose other end only waits for it to start" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["w"]=1 ["r"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["w"]="TO-DO" ["r"]="TO-DO")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["r"]="after:w")
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["w"]="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ -n "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[w]+x}" ]
}

@test "_hold_back_fifo_ends_without_peer leaves out an end whose other end does not fit in the free resources" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    DEBASHER_BUILTIN_SCHED_CPUS=2
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    debasher_builtin_sched::_get_available_cpus() { echo 1; }
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_CPUS=(["w"]=1 ["r"]=2)
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["w"]=1 ["r"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["w"]="TO-DO" ["r"]="TO-DO")
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["r"]="after:w")
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["w"]="${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ -z "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[w]+x}" ]
}

# --- aftercorr task by task -------------------------------------------------

# Marks the task with the given index of the given process, an array of
# three tasks, as finished, as the script of the task does
mark_task_finished() {
    local finished_file
    finished_file=$(debasher::_get_task_finished_filename "${OUTDIR}" "$1" "$2")
    mkdir -p "$(dirname "${finished_file}")"
    debasher::_signal_process_completion "${OUTDIR}" "$1" "$2" 3
}

# A producer p with three tasks, still running, and an array c of the given
# size that depends on it with the given dependencies
setup_aftercorr() {
    local c_size=$1
    local c_deps=$2
    declare -g SEQ="$(command -v seq)"
    declare -g DEBASHER_ARRAY_TASK_NOTHROTTLE=0
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=(["p"]=3 ["c"]=${c_size} ["s"]=1 ["x"]=1)
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE=(["c"]=${DEBASHER_ARRAY_TASK_NOTHROTTLE})
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["c"]="${c_deps}" ["s"]="aftercorr:p")
    declare -gA DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=(["p"]="${DEBASHER_INPROGRESS_PROCESS_STATUS}" ["c"]="${DEBASHER_TODO_PROCESS_STATUS}" ["s"]="${DEBASHER_TODO_PROCESS_STATUS}" ["x"]="${DEBASHER_FINISHED_PROCESS_STATUS}")
    declare -gA BUILTIN_SCHED_EXECUTABLE_PROCESSES=()
}

@test "_dep_holds holds aftercorr for a task once the task of the producer with its index has finished" {
    setup_aftercorr 3 "aftercorr:p"
    mark_task_finished p 1

    debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p c 1
    run debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p c 0
    [ "${status}" -ne 0 ]
    # Without a task, it waits for the whole producer, as afterok
    run debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p c
    [ "${status}" -ne 0 ]
}

@test "_dep_holds makes a task with no counterpart wait for the whole producer under aftercorr" {
    setup_aftercorr 5 "aftercorr:p"
    mark_task_finished p 0

    # The producer has no task 4, and s is not an array
    run debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p c 4
    [ "${status}" -ne 0 ]
    run debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p s 0
    [ "${status}" -ne 0 ]

    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["p"]=${DEBASHER_FINISHED_PROCESS_STATUS}
    debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p c 4
    debasher_builtin_sched::_dep_holds "${OUTDIR}" aftercorr p s 0
}

@test "_dep_holds keeps afterok on the whole producer even for a task whose counterpart has finished" {
    setup_aftercorr 3 "afterok:p"
    mark_task_finished p 1

    run debasher_builtin_sched::_dep_holds "${OUTDIR}" afterok p c 1

    [ "${status}" -ne 0 ]
}

@test "_has_aftercorr_dep finds an aftercorr dependency in any position of the dependencies" {
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=(["a"]="aftercorr:p" ["b"]="afterok:x,aftercorr:p" ["c"]="afterok:x?aftercorr:p" ["d"]="afterok:x,afterany:p" ["e"]="none")

    debasher_builtin_sched::_has_aftercorr_dep a
    debasher_builtin_sched::_has_aftercorr_dep b
    debasher_builtin_sched::_has_aftercorr_dep c
    run debasher_builtin_sched::_has_aftercorr_dep d
    [ "${status}" -ne 0 ]
    run debasher_builtin_sched::_has_aftercorr_dep e
    [ "${status}" -ne 0 ]
}

@test "_update_executable_array_process offers only the tasks whose counterpart has finished" {
    setup_aftercorr 3 "aftercorr:p"
    mark_task_finished p 0
    mark_task_finished p 2

    debasher_builtin_sched::_update_executable_array_process "${OUTDIR}" c "${DEBASHER_TODO_PROCESS_STATUS}"

    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[c]}" = "0 2" ]
}

@test "_update_executable_array_process applies the throttle to the tasks whose dependencies hold" {
    setup_aftercorr 3 "aftercorr:p"
    DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE["c"]=1
    mark_task_finished p 2

    debasher_builtin_sched::_update_executable_array_process "${OUTDIR}" c "${DEBASHER_TODO_PROCESS_STATUS}"

    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[c]}" = "2" ]
}

@test "_update_executable_array_process checks the other dependencies of a task along with aftercorr" {
    setup_aftercorr 3 "aftercorr:p,afterok:x"
    mark_task_finished p 1

    debasher_builtin_sched::_update_executable_array_process "${OUTDIR}" c "${DEBASHER_TODO_PROCESS_STATUS}"
    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[c]}" = "1" ]

    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["x"]=${DEBASHER_TODO_PROCESS_STATUS}
    BUILTIN_SCHED_EXECUTABLE_PROCESSES=()
    debasher_builtin_sched::_update_executable_array_process "${OUTDIR}" c "${DEBASHER_TODO_PROCESS_STATUS}"
    [ -z "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[c]+x}" ]
}

@test "_update_executable_array_process launches the tasks of a producer that has failed whose counterpart finished" {
    setup_aftercorr 3 "aftercorr:p"
    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["p"]=${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}
    mark_task_finished p 0
    mark_task_finished p 1

    debasher_builtin_sched::_update_executable_array_process "${OUTDIR}" c "${DEBASHER_TODO_PROCESS_STATUS}"

    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[c]}" = "0 1" ]
}

@test "_hold_back_fifo_ends_without_peer keeps an end whose other end is a task whose counterpart has finished" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    setup_aftercorr 3 "aftercorr:p"
    mark_task_finished p 1
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f0"]="w${sep}0" ["w/f1"]="w${sep}1")
    declare -gA DEBASHER_FIFO_READERS=(["w/f0"]="c${sep}0" ["w/f1"]="c${sep}1")
    DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE["w"]=2
    DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE["w"]=${DEBASHER_ARRAY_TASK_NOTHROTTLE}
    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["w"]=${DEBASHER_TODO_PROCESS_STATUS}
    BUILTIN_SCHED_EXECUTABLE_PROCESSES=(["w"]="0 1")

    debasher_builtin_sched::_hold_back_fifo_ends_without_peer "${OUTDIR}"

    [ "${BUILTIN_SCHED_EXECUTABLE_PROCESSES[w]}" = "1" ]
}

# --- status of an array -----------------------------------------------------

# An array arr of three tasks, launched under the built-in scheduler, whose
# script has its header after a context with a function that sets
# DEBASHER_NUM_TASKS, as the engine functions of a real one do; no task runs
setup_array_status() {
    declare -g GREP="$(command -v grep)" AWK="$(command -v awk)"
    declare -g DEBASHER_SCHEDULER="${DEBASHER_BUILTIN_SCHEDULER}"
    debasher::_id_exists() { return 1; }
    ARR_EXECDIR="${OUTDIR}/__exec__/arr"
    mkdir -p "${ARR_EXECDIR}"
    {
        echo "some_engine_func () "
        echo "{ "
        echo "    DEBASHER_NUM_TASKS=7"
        echo "}"
        echo "DEBASHER_PROCESS_NAME=arr"
        echo "DEBASHER_NUM_TASKS=3"
    } > "${ARR_EXECDIR}/arr"
}

# Leaves the .id file of the task with the given index, as its launch does
launch_arr_task() {
    echo "$((900000 + $1))" > "$(debasher::_get_array_taskid_filename "${OUTDIR}" arr "$1")"
}

@test "_get_num_array_tasks reads the number of tasks from the header of the process script, before any task has finished" {
    setup_array_status

    run debasher::_get_num_array_tasks "${OUTDIR}" arr
    [ "${status}" -eq 0 ]
    [ "${output}" = "3" ]

    run debasher::_get_num_array_tasks "${OUTDIR}" never_launched
    [ "${output}" = "0" ]
}

@test "an array whose every task was launched and failed is UNFINISHED, not UNFINISHED_BUT_RUNNABLE" {
    setup_array_status
    launch_arr_task 0
    launch_arr_task 1
    launch_arr_task 2

    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_PROCESS_STATUS}" ]
}

@test "an array with tasks not launched yet and none running is UNFINISHED_BUT_RUNNABLE, whether or not one has finished" {
    setup_array_status
    launch_arr_task 0
    launch_arr_task 1

    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ]

    mark_task_finished arr 0
    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ]
}

@test "an array with every task launched, some finished and the others failed is UNFINISHED" {
    setup_array_status
    launch_arr_task 0
    launch_arr_task 1
    launch_arr_task 2
    mark_task_finished arr 1

    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_PROCESS_STATUS}" ]
}

@test "an array whose every task has finished is FINISHED" {
    setup_array_status
    local idx
    for idx in 0 1 2; do
        launch_arr_task "${idx}"
        mark_task_finished arr "${idx}"
    done

    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_FINISHED_PROCESS_STATUS}" ]
}

# --- tasks that will not be launched ----------------------------------------

# A run of the built-in scheduler with no task running and no fifo, in which
# a test registers processes with register_process; launching or
# cancelling a task writes a process script with just its header
setup_cancellation() {
    declare -g GREP="$(command -v grep)" AWK="$(command -v awk)" SEQ="$(command -v seq)"
    declare -g DEBASHER_SCHEDULER="${DEBASHER_BUILTIN_SCHEDULER}"
    declare -g DEBASHER_ARRAY_TASK_NOTHROTTLE=0
    DEBASHER_BUILTIN_SCHED_CPUS=${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}
    DEBASHER_BUILTIN_SCHED_MEM=${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE=() DEBASHER_BUILTIN_SCHED_PROCESS_DEPS=()
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE=() DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS=()
    declare -gA DEBASHER_BUILTIN_SCHED_PROCESS_LAUNCHED_TASKS=() DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS=()
    declare -gA DEBASHER_PROGRAM_FIFOS=() DEBASHER_FIFO_READERS=()
    debasher::_id_exists() { return 1; }
    debasher::_get_numtasks_for_process() { echo "${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[$1]}"; }
    debasher_builtin_sched::_create_script() {
        mkdir -p "$2/__exec__/$3"
        echo "DEBASHER_NUM_TASKS=$4" > "$2/__exec__/$3/$3"
    }
}

# Registers a process with the given number of tasks, dependencies and
# status
register_process() {
    DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE["$1"]=$2
    DEBASHER_BUILTIN_SCHED_PROCESS_DEPS["$1"]=$3
    DEBASHER_BUILTIN_SCHED_PROCESS_THROTTLE["$1"]=${DEBASHER_ARRAY_TASK_NOTHROTTLE}
    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["$1"]=$4
    mkdir -p "${OUTDIR}/__exec__/$1"
}

# Leaves a task of an array process as one that was launched and failed
fail_task() {
    debasher_builtin_sched::_create_script "" "${OUTDIR}" "$1" "${DEBASHER_BUILTIN_SCHED_PROCESS_ARRAY_SIZE[$1]}"
    echo "$((800000 + $2))" > "$(debasher::_get_array_taskid_filename "${OUTDIR}" "$1" "$2")"
}

@test "_dep_can_no_longer_hold rules out afterok on a failed producer and afternotok on a finished one, never after, afterany or none" {
    setup_cancellation
    register_process failed 1 "" "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"
    register_process finished 1 "" "${DEBASHER_FINISHED_PROCESS_STATUS}"
    register_process running 1 "" "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
    register_process c 1 "" "${DEBASHER_TODO_PROCESS_STATUS}"

    debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" afterok failed c
    debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" afternotok finished c
    local deptype producer
    for deptype in after afterany none; do
        for producer in failed finished running; do
            run debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" "${deptype}" "${producer}" c
            [ "${status}" -ne 0 ]
        done
    done
    run debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" afterok running c
    [ "${status}" -ne 0 ]
    run debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" afternotok failed c
    [ "${status}" -ne 0 ]
}

@test "_dep_can_no_longer_hold rules out aftercorr for a task whose counterpart failed or was cancelled, and on a failed producer for a task with no counterpart" {
    setup_cancellation
    register_process p 3 "" "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
    register_process c 4 "aftercorr:p" "${DEBASHER_TODO_PROCESS_STATUS}"
    fail_task p 1
    debasher::_signal_task_cancellation "${OUTDIR}" p 2 3 "afterok:x"

    run debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" aftercorr p c 0
    [ "${status}" -ne 0 ]
    debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" aftercorr p c 1
    debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" aftercorr p c 2
    # Task 3 has no counterpart: it waits for the whole producer, still running
    run debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" aftercorr p c 3
    [ "${status}" -ne 0 ]

    DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS["p"]=${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}
    debasher_builtin_sched::_dep_can_no_longer_hold "${OUTDIR}" aftercorr p c 3
}

@test "_deps_can_no_longer_hold needs one dependency ruled out with a comma, and all of them with a question mark, and prints the cause" {
    setup_cancellation
    register_process failed 1 "" "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"
    register_process finished 1 "" "${DEBASHER_FINISHED_PROCESS_STATUS}"
    register_process all 1 "afterok:finished,afterok:failed" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process any 1 "afterok:finished?afterok:failed" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process none_left 1 "afternotok:finished?afterok:failed" "${DEBASHER_TODO_PROCESS_STATUS}"

    run debasher_builtin_sched::_deps_can_no_longer_hold "${OUTDIR}" all
    [ "${status}" -eq 0 ]
    [ "${output}" = "afterok:failed" ]

    run debasher_builtin_sched::_deps_can_no_longer_hold "${OUTDIR}" any
    [ "${status}" -ne 0 ]

    run debasher_builtin_sched::_deps_can_no_longer_hold "${OUTDIR}" none_left
    [ "${status}" -eq 0 ]
    [ "${output}" = "afternotok:finished?afterok:failed" ]
}

@test "_cancel_tasks_that_cannot_launch cancels only the task whose counterpart failed, records the cause and keeps the array runnable" {
    setup_cancellation
    register_process p 3 "" "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
    register_process c 3 "aftercorr:p" "${DEBASHER_TODO_PROCESS_STATUS}"
    fail_task p 1

    debasher_builtin_sched::_cancel_tasks_that_cannot_launch "" "${OUTDIR}" 2> "${BATS_TEST_TMPDIR}/stderr"

    [ "${DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS[c]}" = "1" ]
    [ "$(cat "$(debasher::_get_task_cancelled_filename "${OUTDIR}" c 1)")" = "Cancelled task idx: 1 ; Total: 3 ; Cause: aftercorr:p (task 1)" ]
    [ "$(debasher_builtin_sched::_get_array_task_status "${OUTDIR}" c 1)" = "${DEBASHER_BUILTIN_SCHED_CANCELLED_TASK_STATUS}" ]
    [ "$(debasher_builtin_sched::_get_array_task_status "${OUTDIR}" c 0)" = "${DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS}" ]
    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[c]}" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ]
    grep -q "PROCESS: c (TASK_IDX: 1) ; CANCELLED: aftercorr:p (task 1)" "${BATS_TEST_TMPDIR}/stderr"
}

@test "_cancel_tasks_that_cannot_launch follows a chain: a process whose every task is cancelled fails, and so rules out afterok on it but lets afterany hold" {
    setup_cancellation
    register_process p 1 "" "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"
    register_process c 2 "afterok:p" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process d 1 "afterok:c" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process e 1 "afterany:c" "${DEBASHER_TODO_PROCESS_STATUS}"

    debasher_builtin_sched::_cancel_tasks_that_cannot_launch "" "${OUTDIR}" 2> /dev/null

    [ "${DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS[c]}" = "0 1" ]
    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[c]}" = "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}" ]
    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[d]}" = "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}" ]
    [ "$(cat "$(debasher::_get_process_cancelled_filename "${OUTDIR}" d)")" = "Cancelled task idx: 0 ; Total: 1 ; Cause: afterok:c" ]
    [ -z "${DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS[e]}" ]
    debasher_builtin_sched::_dep_holds "${OUTDIR}" afterany c e
    # after holds once every task of the producer was cancelled
    debasher_builtin_sched::_dep_holds "${OUTDIR}" after c e
}

@test "_cancel_tasks_that_cannot_launch cancels the end of a fifo whose other end is cancelled" {
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"
    setup_cancellation
    register_process x 1 "" "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"
    register_process w 1 "" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process r 1 "afterok:x" "${DEBASHER_TODO_PROCESS_STATUS}"
    declare -gA DEBASHER_PROGRAM_FIFOS=(["w/f"]="w${sep}0")
    declare -gA DEBASHER_FIFO_READERS=(["w/f"]="r${sep}0")

    debasher_builtin_sched::_cancel_tasks_that_cannot_launch "" "${OUTDIR}" 2> /dev/null

    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[r]}" = "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}" ]
    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[w]}" = "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}" ]
    [ "$(cat "$(debasher::_get_process_cancelled_filename "${OUTDIR}" w)")" = "Cancelled task idx: 0 ; Total: 1 ; Cause: fifo w/f (other end r, task 0, cancelled)" ]
}

@test "_cancel_tasks_that_cannot_launch leaves alone a task that waits for a producer still running, and processes that ended" {
    setup_cancellation
    register_process p 1 "" "${DEBASHER_INPROGRESS_PROCESS_STATUS}"
    register_process c 1 "afterok:p" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process f 1 "" "${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"
    register_process done_already 1 "afterok:f" "${DEBASHER_FINISHED_PROCESS_STATUS}"

    debasher_builtin_sched::_cancel_tasks_that_cannot_launch "" "${OUTDIR}" 2> /dev/null

    [ -z "${DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS[c]}" ]
    [ -z "${DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS[done_already]}" ]
    [ "${DEBASHER_BUILTIN_SCHED_CURR_PROCESS_STATUS[c]}" = "${DEBASHER_TODO_PROCESS_STATUS}" ]
}

@test "_get_fixed_process_status takes as failed a process that ended without finishing after running or having tasks cancelled, and only then" {
    setup_cancellation
    local unf="${DEBASHER_UNFINISHED_PROCESS_STATUS}" failed="${DEBASHER_BUILTIN_SCHED_FAILED_PROCESS_STATUS}"

    [ "$(debasher_builtin_sched::_get_fixed_process_status p "${DEBASHER_INPROGRESS_PROCESS_STATUS}" "${unf}")" = "${failed}" ]
    # Unfinished from an earlier run, and nothing of it handled in this one
    [ "$(debasher_builtin_sched::_get_fixed_process_status p "${unf}" "${unf}")" = "${unf}" ]
    DEBASHER_BUILTIN_SCHED_PROCESS_CANCELLED_TASKS["p"]="0"
    [ "$(debasher_builtin_sched::_get_fixed_process_status p "${DEBASHER_TODO_PROCESS_STATUS}" "${unf}")" = "${failed}" ]
    [ "$(debasher_builtin_sched::_get_fixed_process_status p "${DEBASHER_TODO_PROCESS_STATUS}" "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}")" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ]
}

@test "an array whose tasks were all launched or cancelled is UNFINISHED, and runnable while some are neither" {
    setup_array_status
    launch_arr_task 0
    mark_task_finished arr 0
    debasher::_signal_task_cancellation "${OUTDIR}" arr 1 3 "afterok:x"

    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS}" ]

    debasher::_signal_task_cancellation "${OUTDIR}" arr 2 3 "afterok:x"
    run debasher::_get_process_status "${OUTDIR}" arr
    [ "${output}" = "${DEBASHER_UNFINISHED_PROCESS_STATUS}" ]
}

@test "a finished task counts as finished whatever an older cancellation marker says" {
    setup_cancellation
    register_process arr 3 "" "${DEBASHER_FINISHED_PROCESS_STATUS}"
    debasher::_signal_task_cancellation "${OUTDIR}" arr 1 3 "afterok:x"
    mark_task_finished arr 1

    [ "$(debasher_builtin_sched::_get_array_task_status "${OUTDIR}" arr 1)" = "${DEBASHER_BUILTIN_SCHED_FINISHED_TASK_STATUS}" ]
}

@test "_reset_task_cancellations removes the cancellation markers of a process, so that its tasks wait to be launched again" {
    setup_cancellation
    register_process arr 3 "" "${DEBASHER_TODO_PROCESS_STATUS}"
    register_process single 1 "" "${DEBASHER_TODO_PROCESS_STATUS}"
    debasher::_signal_task_cancellation "${OUTDIR}" arr 1 3 "afterok:x"
    debasher::_signal_task_cancellation "${OUTDIR}" single 0 1 "afterok:x"

    debasher::_reset_task_cancellations "${OUTDIR}" arr
    debasher::_reset_task_cancellations "${OUTDIR}" single

    [ "$(debasher_builtin_sched::_get_array_task_status "${OUTDIR}" arr 1)" = "${DEBASHER_BUILTIN_SCHED_TODO_TASK_STATUS}" ]
    [ ! -e "$(debasher::_get_process_cancelled_filename "${OUTDIR}" single)" ]
}

# --- skipping a task --------------------------------------------------------

@test "_execute_funct_plus_postfunct counts a skipped task as finished without running the process or its post method" {
    local marks="${BATS_TEST_TMPDIR}/marks"
    debasher::_get_opts_for_process_and_task() {
        echo "-x${DEBASHER_ARG_SEP}1"
    }
    debasher_builtin_sched::_write_opts_file() { :; }
    debasher::_signal_process_completion() {
        echo "completion $2 $3" >> "${marks}"
    }
    skipped() {
        echo "process" >> "${marks}"
    }
    skipped_skip() {
        return 0
    }
    skipped_post() {
        echo "post" >> "${marks}"
    }

    run debasher_builtin_sched::_execute_funct_plus_postfunct "" "${OUTDIR}" skipped 1 0
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"skipped by its skip method; counted as finished"* ]]
    [ "$(cat "${marks}")" = "completion skipped 0" ]
}

# --- errors and warnings of the logs of a run -------------------------------

@test "_filter_errwarns_in_script_log_files_pref lists the errors and warnings of the logs of a built-in run" {
    GREP="$(command -v grep)"
    AWK="$(command -v awk)"
    DEBASHER_SCHEDULER="${DEBASHER_BUILTIN_SCHEDULER}"
    DEBASHER_PROGRAM_OUTDIR="${OUTDIR}"
    printf '%s\n' "Process started" "Error: something failed" "Warning: something odd" > "${EXECDIR}/proc.sched_out"

    run debasher::_filter_errwarns_in_script_log_files_pref "E> " "W> " "md"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[${EXECDIR}/proc.sched_out](file://${EXECDIR}/proc.sched_out)"* ]]
    [[ "${output}" == *"E> Error: something failed"* ]]
    [[ "${output}" == *"W> Warning: something odd"* ]]
}

# debasher_builtin_sched::check_program_comp_res checks, as debasher_exec
# --validate does, what the scheduler checks before it launches anything:
# the resources of each process against its limits.
write_procspec() {
    PROCSPEC="${BATS_TEST_TMPDIR}/program.procspec"
    printf '%s\n' \
        "small cpus=1 mem=32 time=00:01:00 |||  ; processdeps=none" \
        "big cpus=4 mem=64 time=00:01:00 |||  ; processdeps=afterok:small" > "${PROCSPEC}"
    DEBASHER_PROCESS_OPT_LIST_LEN[small]=1
    DEBASHER_PROCESS_OPT_LIST_LEN[big]=1
}

@test "check_program_comp_res accepts processes within the limits of the scheduler" {
    write_procspec
    run debasher_builtin_sched::check_program_comp_res "${PROCSPEC}" 4 64
    [ "$status" -eq 0 ]
    [ -z "$output" ]

    run debasher_builtin_sched::check_program_comp_res "${PROCSPEC}" \
        "${DEBASHER_BUILTIN_SCHED_UNLIMITED_CPUS}" "${DEBASHER_BUILTIN_SCHED_UNLIMITED_MEM}"
    [ "$status" -eq 0 ]
}

@test "check_program_comp_res refuses a process above the limits, naming it" {
    write_procspec
    run debasher_builtin_sched::check_program_comp_res "${PROCSPEC}" 2 64
    [ "$status" -eq 1 ]
    [[ "$output" == *"number of cpus for process big exceeds limit (cpus: 4"* ]]

    run debasher_builtin_sched::check_program_comp_res "${PROCSPEC}" 4 32
    [ "$status" -eq 1 ]
    [[ "$output" == *"amount of memory for process big exceeds limit (mem: 64"* ]]
}
