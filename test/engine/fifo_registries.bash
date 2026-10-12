# Helpers shared by the bats files that check the fifo registries of a
# program, loaded with "load fifo_registries".
#
# The registries are filled by hand, as debasher_exec leaves them once every
# process has defined its options and the other end of every fifo is known.

set_up_registries() {
    declare -gA DEBASHER_PROGRAM_FIFOS=() DEBASHER_FIFO_READERS=() DEBASHER_FIFO_KINDS=()
    declare -gA DEBASHER_FIFO_MIRRORED=() DEBASHER_RESIDENT_PROCESS_ROLES=()
    declare -gA DEBASHER_FIFO_OWNER_OPTS=() DEBASHER_FIFO_READER_OPTS=()
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
        DEBASHER_FIFO_READERS["$1"]="${DEBASHER_EXTERNAL_FIFO_END}"
    else
        DEBASHER_FIFO_READERS["$1"]="$3"
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
        DEBASHER_FIFO_READER_OPTS["$1"]="${6:--in}"
    fi
}
