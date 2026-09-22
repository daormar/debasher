#!/usr/bin/env bats
#
# Unit tests for debasher_builtin_sched::_launch
# (engine/debasher_builtin_sched_lib.sh), the built-in scheduler's own
# launch function. It is also what debasher_launch_process (used by a
# Supervisor to relaunch a downed node) calls, so a relaunch behaves
# exactly like the original launch. The tests use a tiny fake process
# script that, like a real generated one, writes its own PID to the file
# named by BUILTIN_SCHED_PID_FILENAME and then records what it saw in its
# environment.

setup() {
    : "${ENGINE_BUILDDIR:?ENGINE_BUILDDIR must point at the built engine/ dir}"
    debasher_pkglibdir="${ENGINE_BUILDDIR}"

    # Tool-path variables the real preamble provides (see
    # test/engine/lib_programs.bats for why they are set by hand here).
    BASENAME="$(command -v basename)"
    PYTHON="$(command -v python3)"
    RM="$(command -v rm)"
    CAT="$(command -v cat)"
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
# Short delay before publishing the PID, so a launch that fails to wait
# for the new PID (returning at once because a stale file is still
# there) is caught deterministically instead of by a race.
sleep 0.02
echo $$ > "${BUILTIN_SCHED_PID_FILENAME}"
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
    [ "$(cat "${EXECDIR}/proc.id")" = "$(grep '^pid=' "${EXECDIR}/seen.txt" | cut -d= -f2)" ]
}

@test "_launch does not return until the new process has replaced a stale .id file" {
    echo 999999 > "${EXECDIR}/proc.id"
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    # Checked right away, on purpose: without removing the stale file
    # first, the wait inside _launch returns at once (the file already
    # exists) and the old PID would still be there.
    [ "$(cat "${EXECDIR}/proc.id")" != "999999" ]
    wait_for_report
}

@test "_launch kills the previous incarnation named by a stale but still-alive .id file" {
    # A relaunch triggered by a missed heartbeat does not prove the old
    # incarnation is actually gone: leave a real, still-running process
    # behind it, in its own process group (as a real launch would).
    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
echo $$ > "${BUILTIN_SCHED_PID_FILENAME}"
sleep 100
EOF
    chmod +x "${SCRIPT}"
    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    local i
    for i in $(seq 1 100); do
        [ -s "${EXECDIR}/proc.id" ] && break
        sleep 0.05
    done
    OLD_PID="$(cat "${EXECDIR}/proc.id")"
    kill -0 "${OLD_PID}"

    cat > "${SCRIPT}" <<'EOF'
#!/bin/bash
sleep 0.02
echo $$ > "${BUILTIN_SCHED_PID_FILENAME}"
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

@test "_launch writes the launched process's own .id even if the caller already exports a foreign BUILTIN_SCHED_PID_FILENAME" {
    # A process that itself was launched by _launch carries its own
    # BUILTIN_SCHED_PID_FILENAME; launching another process from there
    # (a relaunch) must not write the new PID into that foreign file.
    export BUILTIN_SCHED_PID_FILENAME="${BATS_TEST_TMPDIR}/foreign.id"
    echo "untouched" > "${BUILTIN_SCHED_PID_FILENAME}"

    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    wait_for_report

    [ -f "${EXECDIR}/proc.id" ]
    [ "$(cat "${BATS_TEST_TMPDIR}/foreign.id")" = "untouched" ]
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

@test "_launch leaves neither per-launch variable set in the caller" {
    debasher_builtin_sched::_launch "${OUTDIR}" proc 2
    wait_for_report
    [ -z "${BUILTIN_ARRAY_TASK_ID+x}" ]
    [ -z "${BUILTIN_SCHED_PID_FILENAME+x}" ]

    debasher_builtin_sched::_launch "${OUTDIR}" proc "${DEBASHER_BUILTIN_SCHED_NO_ARRAY_TASK}"
    [ -z "${BUILTIN_ARRAY_TASK_ID+x}" ]
    [ -z "${BUILTIN_SCHED_PID_FILENAME+x}" ]
}
