# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

############################
# FIFO MIRROR-RELATED FUNCTIONS #
############################
#
# A fifo declared with --mirror (see define_fifo_opt and
# define_fifo_opt_generator) is observed without taking data from its
# reader. The task that owns it writes into a shim fifo instead, and a mirror
# tap, a background job of that task, copies each line from the shim into the
# real fifo, which its reader opens as usual, and into the mirror log of the
# fifo on disk.
#
# It is a debugging aid for general programs. Resident programs keep their
# own message log inside their processes and do not use it: declaring
# --mirror in one is refused (see debasher::_check_fifo_mirror_allowed).
#
# The --mirror flag and DEBASHER_FIFO_MIRRORED, which records the fifos that
# carry it, belong to the definition of the fifo options in
# debasher_lib_opts.sh; this file holds the paths of a mirror, the tap and
# its start and stop.

########
# The directory of the shim fifos and mirror logs of the run. The real path
# of a mirrored fifo (debasher::_get_absolute_fifoname) does not change: its
# reader gets it, and only the value that its owner gets is replaced by the
# path of the shim (see debasher::_start_fifo_mirror_taps_for_process).
debasher::_get_fifo_mirror_dir()
{
    echo "$(debasher::_get_absolute_fifodir)/.mirror"
}

########
debasher::_get_fifo_shim_name()
{
    local augm_fifoname=$1

    echo "$(debasher::_get_fifo_mirror_dir)/${augm_fifoname}.shim"
}

########
debasher::_get_fifo_mirror_filename()
{
    local augm_fifoname=$1

    echo "$(debasher::_get_fifo_mirror_dir)/${augm_fifoname}.log"
}

########
# Refuses a fifo declared with --mirror when the program is a resident
# one. Resident processes exchange messages through their own runtime
# (engine/debasher_runtime_lib.py and the modules behind it), which keeps
# its own input log and expects to talk to its neighbors directly; a
# mirror tap between a writer and the real fifo is not part of that
# design (it re-frames the traffic line by line and holds the real
# fifo's write end itself), so it is refused when the program is loaded
# instead of being left to misbehave while the program runs.
#
# $1 - Name of the public function that received --mirror, for the error
#      message.
#
# Returns 0 if mirroring is allowed; otherwise prints an error and
# returns 1.
debasher::_check_fifo_mirror_allowed()
{
    local funcname=$1

    if [ "${DEBASHER_PROGRAM_TYPE}" = "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        echo "${funcname}: Error, --mirror cannot be used in a '${DEBASHER_PROGRAM_TYPE_RESIDENT}' program" >&2
        return 1
    fi

    return 0
}

########
# The mirror tap of a fifo: copies each line from the shim fifo $1 into the
# real fifo $2 and appends it to the mirror log $3, until it reads the stop
# token. It runs in the background, started by the task that owns the fifo.
#
# The real fifo and the log are each opened once and kept open while the tap
# runs, and each line is written with builtins, with no process forked for
# it. Both kinds of reader of a fifo work with a writer that keeps the fifo
# open: one that opens it once and reads a stream, which would take a close
# between two lines for the end of the data, and one that opens it anew for
# each line, which only needs a writer present when it opens.
#
# Between two opens of that second kind of reader, the real fifo has no
# reader, and a write on a descriptor already open fails with SIGPIPE
# instead of blocking as an open would. The tap ignores SIGPIPE and retries
# the write of the line on the same descriptor until a reader is there again.
#
# The shim fifo is opened once too, for reading and writing, and kept open.
# Opening it anew for each line would lose lines: a writer that sends several
# lines in one open and closes before the tap has read them all would leave
# the rest in a fifo that nobody holds once the tap closes its own end, and
# the system discards what a fifo holds when its last descriptor is closed.
# Holding a write end of its own also keeps the reads of the tap from seeing
# an end of file between two writers, and the open of a writer from blocking.
# Opening a fifo for reading and writing does not block on Linux or on macOS
# (POSIX leaves it undefined).
debasher::_run_fifo_mirror_tap()
{
    local shimfifo=$1
    local realfifo=$2
    local mirrorfile=$3

    trap '' PIPE
    # The owning process's wrapper ignores SIGTERM and this tap, a
    # subshell of it, inherits that: it catches the signal again so that
    # debasher::_stop_fifo_mirror_taps can end it when it does not stop on
    # its token. Exiting closes its descriptors, so a reader still attached
    # to the real fifo sees EOF.
    trap 'exit 143' TERM

    # High descriptor numbers, clear of those that the shell and test tools
    # use: bats reports the status of its tests on descriptor 3, and the
    # tests of the tap run it as a background job under bats
    exec 7<>"${shimfifo}"
    exec 8>"${realfifo}"
    exec 9>>"${mirrorfile}"

    local line
    while :; do
        IFS= read -r line <&7 || {
            echo "Error: fifo mirror tap lost its shim fifo (${shimfifo}) unexpectedly" >&2
            exec 7<&- 8>&- 9>&-
            exit 1
        }
        if [ "${line}" = "${DEBASHER_FIFO_MIRROR_STOP_TOKEN}" ]; then
            exec 7<&- 8>&- 9>&-
            exit 0
        fi
        # A last line that the writer did not end with a newline is read
        # together with the stop token that follows it: it is forwarded as
        # it was written, with no newline, and the tap stops
        if [[ "${line}" == *"${DEBASHER_FIFO_MIRROR_STOP_TOKEN}" ]]; then
            line="${line%"${DEBASHER_FIFO_MIRROR_STOP_TOKEN}"}"
            printf '%s' "${line}" >&9
            until printf '%s' "${line}" >&8 2>/dev/null; do
                "${SLEEP}" 0.02
            done
            exec 7<&- 8>&- 9>&-
            exit 0
        fi
        printf '%s\n' "${line}" >&9
        until printf '%s\n' "${line}" >&8 2>/dev/null; do
            "${SLEEP}" 0.02
        done
    done
}

########
# Prints the shim fifo of the value $1 of an output option when that value is
# a mirrored fifo of the run, and returns 1 otherwise.
#
# The script of a task runs in a bash process of its own, where
# DEBASHER_FIFO_MIRRORED is empty: the arrays of the fifos are filled by the
# process that loads the program. So the shim fifo that the preparation of
# the owner creates for a mirrored fifo (see
# debasher::_prepare_fifos_owned_by_process) tells it, found on disk.
debasher::_get_shim_of_mirrored_fifo_value()
{
    local value=$1

    local fifodir=$(debasher::_get_absolute_fifodir)
    case "${value}" in
        "${fifodir}"/*)
            ;;
        *)
            return 1
            ;;
    esac
    local shimfifo=$(debasher::_get_fifo_shim_name "${value#${fifodir}/}")
    [ -p "${shimfifo}" ] || return 1
    echo "${shimfifo}"
}

########
# Starts the mirror tap of the real fifo $1, which the shim fifo $2 feeds,
# and records it in DEBASHER_FIFO_MIRROR_TAP_PIDS and
# DEBASHER_FIFO_MIRROR_TAP_SHIMS for debasher::_stop_fifo_mirror_taps.
debasher::_start_fifo_mirror_tap()
{
    local realfifo=$1
    local shimfifo=$2

    local augm_fifoname="${realfifo#$(debasher::_get_absolute_fifodir)/}"
    local mirrorfile=$(debasher::_get_fifo_mirror_filename "${augm_fifoname}")
    debasher::_run_fifo_mirror_tap "${shimfifo}" "${realfifo}" "${mirrorfile}" &
    DEBASHER_FIFO_MIRROR_TAP_PIDS+=($!)
    DEBASHER_FIFO_MIRROR_TAP_SHIMS+=("${shimfifo}")
}

########
# Starts a mirror tap for each mirrored fifo of the run that the task gets
# as the value of an output option in DEBASHER_DESERIALIZED_ARGS (a flat
# list of options and values, which the caller has filled), and replaces
# that value with the path of the shim fifo, so that the process function
# writes into the shim. The .opts file of the task, written before, keeps
# the real path, and so do the options of the reader.
#
# Only the value of an output option (-out* or --out*) is replaced: the
# owner gets a mirrored fifo through one, which define_fifo_opt checks, and
# the reader gets the same path through an input option of its own, which
# has to stay the real fifo.
debasher::_start_fifo_mirror_taps_for_process()
{
    DEBASHER_FIFO_MIRROR_TAP_PIDS=()
    DEBASHER_FIFO_MIRROR_TAP_SHIMS=()

    local n=${#DEBASHER_DESERIALIZED_ARGS[@]}
    local i
    for ((i = 0; i + 1 < n; i++)); do
        debasher::_str_is_output_option "${DEBASHER_DESERIALIZED_ARGS[i]}" || continue

        local realfifo="${DEBASHER_DESERIALIZED_ARGS[i+1]}"
        local shimfifo
        shimfifo=$(debasher::_get_shim_of_mirrored_fifo_value "${realfifo}") || continue

        DEBASHER_DESERIALIZED_ARGS[i+1]="${shimfifo}"
        debasher::_start_fifo_mirror_tap "${realfifo}" "${shimfifo}"
    done
}

########
# Waits until the process $1 has exited, or $2 seconds (an integer) have
# passed. Returns 0 if it exited, 1 otherwise.
debasher::_wait_for_pid_exit()
{
    local pid=$1
    local secs=$2
    local step
    for (( step = 0; step < secs * 20; step++ )); do
        kill -0 "${pid}" 2>/dev/null || return 0
        "${SLEEP}" 0.05
    done
    kill -0 "${pid}" 2>/dev/null || return 0
    return 1
}

########
# Stops every mirror tap started by
# debasher::_start_fifo_mirror_taps_for_process, and never blocks for
# good. Each tap is sent its stop token and given
# DEBASHER_FIFO_MIRROR_TAP_STOP_GRACE_SECS to exit. A tap that does not is
# stuck forwarding a line that nobody reads, typically because the reader
# of its real fifo finished or died before the owning process did: the
# tap retries that write until it succeeds and never gets to the token.
# It is then ended with SIGTERM (SIGKILL if that is not enough within
# the same time), with a warning and not an error: the owning process
# itself succeeded, and every line it wrote is in the mirror log, the
# ones that could not be forwarded included. The token is written from
# a background job, since that write can block (with the shim full
# behind a stuck tap, or with no tap left to read it); the job is killed
# once its tap is gone. Returns non-zero
# if a tap that stopped on its token exited abnormally, so the caller can
# fail the owning process instead of silently losing mirrored output.
debasher::_stop_fifo_mirror_taps()
{
    local grace="${DEBASHER_FIFO_MIRROR_TAP_STOP_GRACE_SECS}"
    local failed=0
    local i pid shim token_pid
    for i in "${!DEBASHER_FIFO_MIRROR_TAP_PIDS[@]}"; do
        pid="${DEBASHER_FIFO_MIRROR_TAP_PIDS[i]}"
        shim="${DEBASHER_FIFO_MIRROR_TAP_SHIMS[i]}"

        { printf '%s\n' "${DEBASHER_FIFO_MIRROR_STOP_TOKEN}" > "${shim}"; } 2>/dev/null &
        token_pid=$!

        if debasher::_wait_for_pid_exit "${pid}" "${grace}"; then
            if ! wait "${pid}"; then
                echo "Error: fifo mirror tap for ${shim} exited abnormally" >&2
                failed=1
            fi
        else
            echo "Warning: fifo mirror tap for ${shim} did not stop within ${grace}s (the reader of its real fifo is probably gone), terminating it; the lines it could not forward are in its mirror log" >&2
            kill -TERM "${pid}" 2>/dev/null || true
            if ! debasher::_wait_for_pid_exit "${pid}" "${grace}"; then
                kill -KILL "${pid}" 2>/dev/null || true
            fi
            wait "${pid}" 2>/dev/null || true
        fi

        kill -KILL "${token_pid}" 2>/dev/null || true
        wait "${token_pid}" 2>/dev/null || true
    done
    return ${failed}
}
