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
# A mirrored fifo (declared with define_fifo_opt/define_fifo_opt_generator's
# --mirror flag, engine/debasher_lib_opts.sh) lets a fifo's traffic be
# observed without stealing data from its real reader: the owning process's
# own writer argument is transparently redirected to a shim fifo, and the
# background tap below bridges every line from that shim into both the real
# fifo (so the real reader is unaffected) and a mirror log file on disk.
#
# It is a debugging aid for general programs. Resident programs keep their
# own message log inside their processes and do not use it: declaring
# --mirror in one is refused (see debasher::_check_fifo_mirror_allowed).
#
# The `--mirror` flag itself, and the DEBASHER_FIFO_MIRRORED bookkeeping it
# populates, stay defined in debasher_lib_opts.sh (woven into fifo option
# definition itself); only the tap process and its path helpers live here.

########
# FIFO MIRRORING path helpers. A mirrored fifo's real path (returned by
# debasher::_get_absolute_fifoname in debasher_lib_opts.sh) is untouched and
# still handed to the fifo's real reader; only the writer's own resolved
# option value gets swapped for the shim path (see
# debasher::_start_fifo_mirror_taps_for_process), which a background tap
# bridges into [mirror log file, real fifo].
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
# Background loop bridging a mirrored fifo's shim fifo to both its real
# fifo and its mirror log file, one line at a time. The real fifo and
# the mirror file are each opened once, before the loop, and kept open
# for the tap's entire lifetime -- never closed between messages -- so
# every line is forwarded with two builtin printfs, no external process
# forked per line (previously a piped tee per line).
#
# This is safe for every known reader of a mirrored real fifo: a reader
# that reopens the real fifo per line (this codebase's own
# data/programs/debasher_echo.sh's stream_echo idiom) tolerates a
# persistent writer fine, verified with a real fifo -- it only needs a
# writer present at the moment it opens, not a close between messages.
# A reader with its own single persistent open (e.g. FBPProcess's
# reader thread) requires exactly this shape and cannot recover from an
# intermediate EOF at all. Re-opening the real fifo per line, as this
# tap used to do, is the one thing that breaks that second kind of
# reader, which is why this rewrite removes it instead of preserving it.
#
# A reader that reopens the real fifo per line is, by construction,
# fully detached (zero readers) during the gap between one close and
# the next open -- and unlike a fresh open() (which blocks until a
# reader appears), a write on this tap's own already-open fd during
# that exact gap raises SIGPIPE, verified with a real fifo: killing the
# tap outright the moment its timing loses that race. SIGPIPE is
# ignored for this reason, and each forwarded write is retried (on the
# very same fd, no close/reopen needed -- also verified: an existing
# writer fd starts working again as soon as a new reader attaches) until
# it succeeds, rather than treated as fatal.
#
# The shim fifo is opened once too, for reading and writing, and never
# closed until the tap ends. Opening it anew for each line would lose
# lines: a writer that sends several lines in one open (printf with
# several lines, cat of a file) and closes before the tap has read them
# all leaves the rest in a fifo that, once the tap closes its own read
# end, nobody holds, and the kernel discards what a fifo held when its
# last descriptor is closed. Holding a write end of its own also keeps
# the tap's reads from ever seeing EOF between writers, and a writer's
# open from blocking. Opening a fifo for reading and writing does not
# block on Linux (POSIX leaves it undefined).
debasher::_run_fifo_mirror_tap()
{
    local shimfifo=$1
    local realfifo=$2
    local mirrorfile=$3

    trap '' PIPE

    # High fd numbers (not 3/4): fd 3 is reserved by bats-core itself
    # for test status reporting, and this tap's own bats tests run it
    # as a real background job under bats, so clobbering fd 3 here
    # would corrupt the test harness's own channel, not just this
    # process's -- avoided by staying well clear of low fd numbers
    # any shell/test tooling might already be using.
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
        printf '%s\n' "${line}" >&9
        until printf '%s\n' "${line}" >&8 2>/dev/null; do
            "${SLEEP}" 0.02
        done
    done
}

########
# Starts one background mirror tap per mirrored fifo referenced in
# DEBASHER_DESERIALIZED_ARGS (already populated by the caller),
# rewriting each matching real-fifo argument to the tap's shim path
# instead, so the process function's own argv is the only thing that
# changes: the real fifo path stays exactly what was persisted to the
# ".opts" file and what any connected reader resolved at DAG-definition
# time. Populates DEBASHER_FIFO_MIRROR_TAP_PIDS/
# DEBASHER_FIFO_MIRROR_TAP_SHIMS for debasher::_stop_fifo_mirror_taps to
# join on afterwards.
#
# Deliberately does NOT consult DEBASHER_PROGRAM_FIFOS/
# DEBASHER_FIFO_MIRRORED: this runs inside the process's own generated
# script, which, for both the builtin and Slurm schedulers, executes
# as a separate bash process from the one that ran every process's
# _define_opts (and so populated those in-memory arrays) at DAG-load
# time; they're empty here even though the shim fifo/mirror log files
# _prepare_fifos_owned_by_process created for a mirrored fifo (which
# DOES run in that original process) are still there on disk. Treating
# "a shim fifo exists at the path this real fifo argument maps to" as
# the signal instead works across that process boundary for free, since
# it's a plain filesystem check.
#
# Only ever substitutes the argument immediately following a "-out"/
# "--out"-prefixed flag (DEBASHER_DESERIALIZED_ARGS is a flat "flag,
# value, flag, value, ..." sequence, see debasher::_print_opts_as_
# qstrings): a fifo's real path is identical in both the owner's
# argv (whose flag names the "-outf"-style option --mirror was declared
# on) and any connected reader's argv (whose flag is its own "-inf"-
# style connection), without this check, a reader would see its own
# input argument redirected to the writer's shim and read nothing real
# ever gets forwarded to. This mirrors the same "-out"/"--out" naming
# convention frontend/src/models/option.ts's getOptionDirection already
# uses, and that script_generation.py only ever emits --mirror for
# (direction == "output").
debasher::_start_fifo_mirror_taps_for_process()
{
    local processname=$1
    local fifodir=$(debasher::_get_absolute_fifodir)

    DEBASHER_FIFO_MIRROR_TAP_PIDS=()
    DEBASHER_FIFO_MIRROR_TAP_SHIMS=()

    local n=${#DEBASHER_DESERIALIZED_ARGS[@]}
    local i
    for ((i = 0; i + 1 < n; i++)); do
        local flag="${DEBASHER_DESERIALIZED_ARGS[i]}"
        case "${flag}" in
            -out*|--out*)
                ;;
            *)
                continue
                ;;
        esac

        local realfifo="${DEBASHER_DESERIALIZED_ARGS[i+1]}"
        case "${realfifo}" in
            "${fifodir}"/*)
                local augm_fifoname="${realfifo#${fifodir}/}"
                local shimfifo=$(debasher::_get_fifo_shim_name "${augm_fifoname}")

                if [ -p "${shimfifo}" ]; then
                    local mirrorfile=$(debasher::_get_fifo_mirror_filename "${augm_fifoname}")

                    DEBASHER_DESERIALIZED_ARGS[i+1]="${shimfifo}"

                    debasher::_run_fifo_mirror_tap "${shimfifo}" "${realfifo}" "${mirrorfile}" &
                    DEBASHER_FIFO_MIRROR_TAP_PIDS+=($!)
                    DEBASHER_FIFO_MIRROR_TAP_SHIMS+=("${shimfifo}")
                fi
                ;;
        esac
    done
}

########
# Stops every mirror tap started by
# debasher::_start_fifo_mirror_taps_for_process, unblocking each one's
# read via its own stop token and waiting for it to exit. Returns
# non-zero if any tap exited abnormally, so the caller can fail the
# owning process instead of silently losing mirrored output.
debasher::_stop_fifo_mirror_taps()
{
    local failed=0
    local i
    for i in "${!DEBASHER_FIFO_MIRROR_TAP_PIDS[@]}"; do
        echo "${DEBASHER_FIFO_MIRROR_STOP_TOKEN}" > "${DEBASHER_FIFO_MIRROR_TAP_SHIMS[i]}" 2>/dev/null
        if ! wait "${DEBASHER_FIFO_MIRROR_TAP_PIDS[i]}"; then
            echo "Error: fifo mirror tap for ${DEBASHER_FIFO_MIRROR_TAP_SHIMS[i]} exited abnormally" >&2
            failed=1
        fi
    done
    return ${failed}
}
