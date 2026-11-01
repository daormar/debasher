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
# The marker that the task of the owner creates next to the shim fifo $1 once
# its process function has returned (see debasher::_stop_fifo_mirror_taps)
debasher::_get_fifo_mirror_done_filename()
{
    echo "$1.done"
}

########
# The mirror tap of a fifo: copies each line from the shim fifo $1 into the
# mirror log $3 and then into the real fifo $2, until the end of the data in
# the shim. It runs in the background, started by the task that owns the
# fifo, whose process id is $4, and the files stay open while it runs.
#
# The shim is opened for reading only, and the task holds a write end of it
# while its process function runs (see
# debasher::_start_fifo_mirror_taps_for_process). So the shim has a writer
# between two opens of the owner, and the tap neither loses lines written
# through several opens nor sees the end of the data before the process
# function returns, or before the task ends, when it ends in any other way
# and the system closes its write end.
#
# The real fifo is opened once, and its reader sees a single writer for the
# whole task. A write blocks while a reader that is slow does not take the
# data, and fails with SIGPIPE when the fifo has no reader: a reader that
# opens it anew for each line has none between two of them. The tap ignores
# SIGPIPE and retries the write (see debasher::_forward_mirrored_line). When
# it gives the line up, it copies what is left in the shim into the log and
# ends with 2.
debasher::_run_fifo_mirror_tap()
{
    local shimfifo=$1
    local realfifo=$2
    local mirrorfile=$3
    local owner_pid=$4
    local donefile=$(debasher::_get_fifo_mirror_done_filename "${shimfifo}")

    trap '' PIPE

    # High descriptor numbers, clear of those that the shell and test tools
    # use: bats reports the status of its tests on descriptor 3, and the
    # tests of the tap run it as a background job under bats
    exec 7<"${shimfifo}" || exit 1
    exec 9>>"${mirrorfile}" || exit 1
    exec 8>"${realfifo}" || exit 1

    local line
    while IFS= read -r line <&7; do
        printf '%s\n' "${line}" >&9
        if ! debasher::_forward_mirrored_line "${owner_pid}" "${donefile}" "${line}"$'\n'; then
            "${CAT}" <&7 >&9
            exit 2
        fi
    done
    # A last line without a newline is forwarded as it was written
    if [ -n "${line}" ]; then
        printf '%s' "${line}" >&9
        debasher::_forward_mirrored_line "${owner_pid}" "${donefile}" "${line}" || exit 2
    fi
    exit 0
}

########
# Writes $3 into the real fifo of a mirror tap, open on descriptor 8, and
# retries while the write fails, which it does only when the fifo has no
# reader. Returns 1, giving the line up, when the task $1 is gone, or when
# the marker $2 says that its process function has returned and the write
# has failed for DEBASHER_FIFO_MIRROR_TAP_STOP_GRACE_SECS since: the reader
# is gone.
debasher::_forward_mirrored_line()
{
    local owner_pid=$1
    local donefile=$2
    local text=$3

    local tries_after_done=0
    until printf '%s' "${text}" >&8 2>/dev/null; do
        kill -0 "${owner_pid}" 2>/dev/null || return 1
        if [ -e "${donefile}" ]; then
            (( ++tries_after_done <= DEBASHER_FIFO_MIRROR_TAP_STOP_GRACE_SECS * 50 )) || return 1
        fi
        "${SLEEP}" 0.02
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
# DEBASHER_FIFO_MIRROR_TAP_SHIMS.
debasher::_start_fifo_mirror_tap()
{
    local realfifo=$1
    local shimfifo=$2

    local augm_fifoname="${realfifo#$(debasher::_get_absolute_fifodir)/}"
    local mirrorfile=$(debasher::_get_fifo_mirror_filename "${augm_fifoname}")
    "${RM}" -f "$(debasher::_get_fifo_mirror_done_filename "${shimfifo}")"
    debasher::_run_fifo_mirror_tap "${shimfifo}" "${realfifo}" "${mirrorfile}" "$$" &
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
#
# Once every tap has started, the task opens a write end of each shim, kept
# in DEBASHER_FIFO_MIRROR_TAP_FDS until debasher::_stop_fifo_mirror_taps
# closes it (see debasher::_run_fifo_mirror_tap). A tap started after one of
# them is open would hold it too, and keep the tap of that shim from ever
# seeing the end of its data.
debasher::_start_fifo_mirror_taps_for_process()
{
    DEBASHER_FIFO_MIRROR_TAP_PIDS=()
    DEBASHER_FIFO_MIRROR_TAP_SHIMS=()
    DEBASHER_FIFO_MIRROR_TAP_FDS=()

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

    local shimfifo fd
    for shimfifo in "${DEBASHER_FIFO_MIRROR_TAP_SHIMS[@]}"; do
        exec {fd}>"${shimfifo}"
        DEBASHER_FIFO_MIRROR_TAP_FDS+=("${fd}")
    done
}

########
# Stops the mirror taps of the task once its process function has returned:
# creates the marker of each shim, closes the write ends of the shims, which
# ends the data of each tap, and waits for every tap to end, for as long as
# it takes, as a writer with no mirror waits for its reader. A tap ends when
# its reader has taken every line, or gives the rest up when its reader is
# gone (see debasher::_forward_mirrored_line), with a warning, since every
# line is still in its mirror log. A tap whose real fifo no reader opens
# never ends, as a writer with no mirror would never end, and the task is
# left to debasher_stop. Returns 1 if a tap ended with an error, so that the
# caller fails the task.
debasher::_stop_fifo_mirror_taps()
{
    local shim
    for shim in "${DEBASHER_FIFO_MIRROR_TAP_SHIMS[@]}"; do
        : > "$(debasher::_get_fifo_mirror_done_filename "${shim}")"
    done
    local fd
    for fd in "${DEBASHER_FIFO_MIRROR_TAP_FDS[@]}"; do
        exec {fd}>&-
    done

    local failed=0
    local i pid status
    for i in "${!DEBASHER_FIFO_MIRROR_TAP_PIDS[@]}"; do
        pid="${DEBASHER_FIFO_MIRROR_TAP_PIDS[i]}"
        shim="${DEBASHER_FIFO_MIRROR_TAP_SHIMS[i]}"
        status=0
        wait "${pid}" || status=$?
        case ${status} in
            0)
                ;;
            2)
                echo "Warning: the reader of the fifo mirrored by ${shim} is gone, and did not take every line; every line is in its mirror log" >&2
                ;;
            *)
                echo "Error: fifo mirror tap for ${shim} exited abnormally" >&2
                failed=1
                ;;
        esac
    done
    return ${failed}
}
