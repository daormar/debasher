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

######################################
# RESIDENT PROGRAM-RELATED FUNCTIONS #
######################################

########
# Like debasher::_search_heredoc_provider, but fixed to the Python
# heredoc forms specifically (DEBASHER_PROCESS_FUNCNAME_PYEXEC /
# DEBASHER_PROCESS_VARNAME_PYEXEC), not any other heredoc language.
# Echoes "<name> func" or "<name> var" and returns 0 if found; returns
# 1 with no output otherwise (including when the process is a heredoc
# process in a different language).
debasher::_get_python_heredoc_provider()
{
    local processname=$1

    debasher::_search_heredoc_provider "${processname}" "${DEBASHER_PROCESS_FUNCNAME_PYEXEC}" "${DEBASHER_PROCESS_VARNAME_PYEXEC}"
}

########
# Echoes the raw Python source of a process's Python heredoc (function
# or legacy variable provider). A "resident" program (see
# doc/design_doc_resident.md) requires every one of its processes to
# provide its code this way, so its source can be located and analyzed
# without ever running it or needing a real file on disk. Returns 1,
# with no output, if the process has no Python heredoc provider at all
# (a regular/alias/ext_alias process, or a heredoc in a different
# language).
debasher::_get_resident_process_source()
{
    local processname=$1

    local provider_info
    provider_info=$(debasher::_get_python_heredoc_provider "${processname}") || return 1

    local provider kind
    read -r provider kind <<< "${provider_info}"

    if [ "${kind}" = "func" ]; then
        "${provider}"
    else
        echo "${!provider}"
    fi
}

########
# Classifies a resident program's process as "supervisor", "fbpprocess" or
# "unknown", from the base of the classes of its Python heredoc source (see
# debasher::_get_resident_process_source), with debasher_node_source.py of
# the runtime library. Returns 1, with an error on stderr, if the process is
# not a Python heredoc process at all, or if its source is not valid Python.
debasher::_classify_resident_process_role()
{
    local processname=$1

    local source
    if ! source=$(debasher::_get_resident_process_source "${processname}"); then
        echo "Error: process ${processname} does not provide its code as a Python heredoc, required for a resident program" >&2
        return 1
    fi

    printf '%s' "${source}" | "${PYTHON}" "${debasher_pythondir}/debasher_node_source.py" classify
}

########
# Checks the name of the class of a resident program's process, and the line
# that starts it, against its Python heredoc source (see
# debasher::_get_resident_process_source), with debasher_node_source.py of
# the runtime library: the class that derives from a class of the runtime
# library is the node, there is exactly one, it is named after its process
# in CamelCase and hides nothing that the code of the node could need, and
# the code has the line <Name>().run(). Returns 1, with an error on stderr,
# if the name breaks one of its rules, or if the process is not a Python
# heredoc process at all.
debasher::_check_resident_class_name()
{
    local processname=$1

    local source
    if ! source=$(debasher::_get_resident_process_source "${processname}"); then
        echo "Error: process ${processname} does not provide its code as a Python heredoc, required for a resident program" >&2
        return 1
    fi

    printf '%s' "${source}" | "${PYTHON}" "${debasher_pythondir}/debasher_node_source.py" check-class-name "${processname}"
}

########
# Validates every process of a "resident" program (see
# doc/design_doc_resident.md): each one must classify (via
# debasher::_classify_resident_process_role) as either "supervisor" or
# "fbpprocess", with its class named and its node started as
# debasher::_check_resident_class_name requires, and at most one process
# may be a "supervisor" (a supervisor is optional, like ext2/3/4
# journaling, but never more than one). A no-op, returning 0
# immediately, when DEBASHER_PROGRAM_TYPE is not "resident". Exits with
# an error message on the first violation found.
debasher::_validate_resident_program_processes()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        return 0
    fi

    local processname
    local supervisor_processname=""

    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local role
        role=$(debasher::_classify_resident_process_role "${processname}") || return 1
        DEBASHER_RESIDENT_PROCESS_ROLES["${processname}"]="${role}"

        case "${role}" in
            supervisor)
                if [ -n "${supervisor_processname}" ]; then
                    echo "Error: a resident program can have at most one Supervisor process, but both ${supervisor_processname} and ${processname} are" >&2
                    return 1
                fi
                supervisor_processname="${processname}"
                ;;
            fbpprocess)
                :
                ;;
            *)
                echo "Error: process ${processname} does not derive from FBPProcess or Supervisor, required for a resident program" >&2
                return 1
                ;;
        esac

        debasher::_check_resident_class_name "${processname}" || return 1
    done
}

########
# Checks the flags of the program's fifos (see DEBASHER_FIFO_KINDS and
# DEBASHER_FIFO_MIRRORED) once every process has defined its options and
# the other end of every fifo is known (see
# debasher::_register_fifos_read_by_process). A general program may not use
# the tags, and a resident program may not use --mirror. In a resident
# program the tags have to be used as they say, and a round has to be able
# to reach every node (see the design doc's "Channel kinds declared with the
# fifo"). Prints an error and returns 1 on the first violation found.
debasher::_validate_program_fifo_flags()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        local augm_fifoname
        for augm_fifoname in "${!DEBASHER_FIFO_KINDS[@]}"; do
            echo "Error: fifo ${augm_fifoname} is tagged --${DEBASHER_FIFO_KINDS[${augm_fifoname}]}, which only a '${DEBASHER_PROGRAM_TYPE_RESIDENT}' program may use" >&2
            return 1
        done
        return 0
    fi

    # The mirror tap sits between the writer and the real fifo and holds the
    # fifo's write end itself, while the runtime of a resident program needs
    # both ends of a channel to hold the fifo, and keeps its own input log
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_FIFO_MIRRORED[@]}"; do
        echo "Error: fifo ${augm_fifoname} is declared with --mirror, which a '${DEBASHER_PROGRAM_TYPE_RESIDENT}' program may not use: its nodes keep their own input log" >&2
        return 1
    done

    debasher::_validate_resident_channels
}

########
# The name of a node for a message: the process name, or
# <process>:<idx> for a task of a process with several tasks (as
# debasher_stop_resident's -x names it). $1 is a node as the fifo registries store it,
# <process><DEBASHER_ASSOC_ARRAY_ELEM_SEP><idx>.
debasher::_resident_node_display_name()
{
    local node=$1
    local processname="${node%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
    local idx="${node#*${DEBASHER_ASSOC_ARRAY_ELEM_SEP}}"
    if [ "$(debasher::_get_numtasks_for_process "${processname}")" -eq 1 ]; then
        echo "${processname}"
    else
        echo "${processname}:${idx}"
    fi
}

########
# Builds the graph of the business channels of a resident program, task
# by task, from the fifo registries and tags, and checks it:
#
# 1. Every tagged fifo is used as its tag says: one tagged --external has
#    its other end outside the program, and one tagged --control either has
#    its other end outside or is owned by the Supervisor and read by a node.
#    The owner of a fifo writes it, through an output option ("-out..."),
#    except a tagged fifo fed from outside, which it reads through an input
#    option.
# 2. Every node (every task of every FBPProcess) can be reached from an
#    initiator, a node that reads a fifo tagged --control, through the
#    fifos without a tag, each from its owner, which writes it, to the node
#    at its other end, which reads it.
#
# A fifo without a tag whose other end is outside the program is a channel
# to someone outside (a node that writes its results out), and so is one
# whose other end is the Supervisor (a heartbeat channel): neither is an
# edge of the graph. Needs DEBASHER_RESIDENT_PROCESS_ROLES, filled by
# debasher::_validate_resident_program_processes.
debasher::_validate_resident_channels()
{
    # Every task of every business node
    local -A is_node=()
    debasher::_collect_resident_business_nodes is_node

    # Edges of the graph, and the initiators, which start the walk
    local -A successors=()
    local -A reached=()
    local -a queue=()
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        debasher::_add_resident_fifo_to_graph is_node successors reached queue "${augm_fifoname}" || return 1
        debasher::_check_resident_fifo_owner_opt "${augm_fifoname}" || return 1
    done

    debasher::_walk_resident_graph_from_initiators successors reached queue
    debasher::_check_every_resident_node_reached is_node reached
}

########
# Fills the associative array named $1 with every task of every FBPProcess,
# as <process><DEBASHER_ASSOC_ARRAY_ELEM_SEP><idx>.
debasher::_collect_resident_business_nodes()
{
    local -n is_node_ref=$1

    local processname idx num_tasks
    for processname in "${!DEBASHER_RESIDENT_PROCESS_ROLES[@]}"; do
        [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${processname}]}" = "fbpprocess" ] || continue
        num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
        for (( idx = 0; idx < num_tasks; idx++ )); do
            is_node_ref["${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${idx}"]=1
        done
    done
}

########
# Adds the fifo $5 to the graph of the business channels, given by the
# names of its arrays: $1, the associative array of the nodes; $2, the
# associative array of the successors of each node; $3, the associative
# array of the nodes reached; $4, the indexed array of the queue of the
# walk. A fifo without a tag between two nodes is an edge from its owner to
# its reader; a fifo tagged --control makes an initiator of the node that
# reads it (from outside the program, its owner; from the Supervisor, its
# reader), which is marked reached and goes into the queue. Fails, with an
# error, for a fifo tagged --external that a process of the program reads,
# and for one tagged --control that is neither fed from outside nor written
# by the Supervisor to a node.
debasher::_add_resident_fifo_to_graph()
{
    local -n is_node_ref=$1
    local -n successors_ref=$2
    local -n reached_ref=$3
    local -n queue_ref=$4
    local augm_fifoname=$5

    local owner="${DEBASHER_PROGRAM_FIFOS[${augm_fifoname}]}"
    local reader="${DEBASHER_FIFO_READERS[${augm_fifoname}]}"
    local kind="${DEBASHER_FIFO_KINDS[${augm_fifoname}]:-}"
    local owner_proc="${owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
    local reader_proc="${reader%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
    local initiator
    case "${kind}" in
        "")
            if [ -n "${is_node_ref[${owner}]+x}" ] && [ -n "${is_node_ref[${reader}]+x}" ]; then
                successors_ref["${owner}"]+=" ${reader}"
            fi
            ;;
        "${DEBASHER_FIFO_KIND_EXTERNAL}")
            if [ "${reader}" != "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
                echo "Error: fifo ${augm_fifoname} is tagged --external, but process ${reader_proc} of the program reads it: a fifo fed from outside the program has no other end inside it" >&2
                return 1
            fi
            ;;
        "${DEBASHER_FIFO_KIND_CONTROL}")
            if [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
                initiator="${owner}"
            elif [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${owner_proc}]:-}" = "supervisor" ] && [ -n "${is_node_ref[${reader}]+x}" ]; then
                initiator="${reader}"
            else
                echo "Error: fifo ${augm_fifoname} is tagged --control, but it is neither fed from outside the program nor written by the Supervisor to a node" >&2
                return 1
            fi
            if [ -n "${is_node_ref[${initiator}]+x}" ] && [ -z "${reached_ref[${initiator}]+x}" ]; then
                reached_ref["${initiator}"]=1
                queue_ref+=("${initiator}")
            fi
            ;;
    esac
}

########
# Fails, with an error, when the option through which the owner of the fifo
# $1 defines it does not say what the owner does with it: a fifo is written
# by its owner, through an output option ("-out..."), except a tagged fifo
# fed from outside the program, which its owner reads through an input
# option.
debasher::_check_resident_fifo_owner_opt()
{
    local augm_fifoname=$1

    local owner="${DEBASHER_PROGRAM_FIFOS[${augm_fifoname}]}"
    local reader="${DEBASHER_FIFO_READERS[${augm_fifoname}]}"
    local kind="${DEBASHER_FIFO_KINDS[${augm_fifoname}]:-}"
    local owner_proc="${owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}"
    local owner_opt="${DEBASHER_FIFO_OWNER_OPTS[${augm_fifoname}]:-}"
    if [ -n "${kind}" ] && [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
        if debasher::_str_is_output_option "${owner_opt}"; then
            echo "Error: fifo ${augm_fifoname} is tagged --${kind} and fed from outside the program, so process ${owner_proc} reads it, but defines it through the output option ${owner_opt}" >&2
            return 1
        fi
    elif ! debasher::_str_is_output_option "${owner_opt}"; then
        echo "Error: fifo ${augm_fifoname} is defined by process ${owner_proc} through the input option ${owner_opt}: a fifo is defined by the process that writes it, through an output option (-out...), unless it is fed from outside the program and tagged --external or --control" >&2
        return 1
    fi
}

########
# Marks in the associative array named $2 every node that a round can reach
# from the initiators in the indexed array named $3, the queue of the walk,
# walking breadth first the edges of the associative array named $1, the
# successors of each node.
debasher::_walk_resident_graph_from_initiators()
{
    local -n successors_ref=$1
    local -n reached_ref=$2
    local -n queue_ref=$3

    local head=0 node next
    while [ "${head}" -lt "${#queue_ref[@]}" ]; do
        node="${queue_ref[head]}"
        head=$((head + 1))
        for next in ${successors_ref[${node}]:-}; do
            if [ -z "${reached_ref[${next}]+x}" ]; then
                reached_ref["${next}"]=1
                queue_ref+=("${next}")
            fi
        done
    done
}

########
# Fails, with an error that names them sorted, when a node of the
# associative array named $1 is not in the associative array named $2, the
# nodes reached: no round could reach it.
debasher::_check_every_resident_node_reached()
{
    local -n is_node_ref=$1
    local -n reached_ref=$2

    local -a unreached=()
    local node
    for node in "${!is_node_ref[@]}"; do
        if [ -z "${reached_ref[${node}]+x}" ]; then
            unreached+=("$(debasher::_resident_node_display_name "${node}")")
        fi
    done
    if [ "${#unreached[@]}" -gt 0 ]; then
        local sorted
        sorted=$(printf '%s\n' "${unreached[@]}" | "${SORT}" | "${TR}" '\n' ' ')
        echo "Error: no round can reach ${sorted% }: a round starts at a node that reads a fifo tagged --control and goes on through the fifos without a tag, from their owner to the node at the other end" >&2
        return 1
    fi
}

########
# Prints the role of the process of a node end as the fifo registries store
# it, <process><DEBASHER_ASSOC_ARRAY_ELEM_SEP><idx> (see
# DEBASHER_RESIDENT_PROCESS_ROLES), or nothing for the end outside the
# program.
debasher::_resident_node_role()
{
    local node=$1
    echo "${DEBASHER_RESIDENT_PROCESS_ROLES[${node%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}]:-}"
}

########
# Prints the blank-separated words of $1 sorted and separated by commas.
debasher::_sorted_comma_list()
{
    local words=$1
    [ -n "${words// /}" ] || return 0
    local sorted
    sorted=$(printf '%s\n' ${words} | "${SORT}")
    echo "${sorted//$'\n'/,}"
}

########
# Fills DEBASHER_RESIDENT_TASK_PORTS with the ports of every task of every
# FBPProcess of a resident program, and of the Supervisor, taken from the
# fifo registries and tags (see the design doc's "Ports from the engine"). A
# port is the name of the option without its leading dashes, as the
# process's own options name it. The wrapper of each task exports its entry
# as DEBASHER_PROCESS_PORTS. For a node, which of its options are input,
# output, control and external ports, and which output port goes to the
# Supervisor:
#
#   input=<ports>;output=<ports>;control=<ports>;external=<ports>;supervisor=<port>
#
# For the Supervisor, the heartbeat channel of each node, as <node>=<port>
# with the node named as debasher::_resident_node_display_name names it,
# its initiator ports (the output ports to the initiators it triggers), the
# input port of a manual trigger fed from outside, and the startup deadline of each node that gives
# one in its computational specifications (startup_timeout_s), as
# <node>=<seconds>, and the fifos of the business channels, those without a
# tag between two nodes, which it holds open so that what they hold outlives
# the crash of both nodes of a channel, as names relative to the fifo
# directory of the program, <owner process>/<fifo>:
#
#   nodes=<node>=<port>,...;initiators=<ports>;manual_trigger=<port>;startup=<node>=<seconds>,...;hold=<fifos>
#
# each list sorted and separated by commas, and possibly empty. A no-op when
# the program is not resident. Needs the checks of
# debasher::_validate_resident_channels to have passed, and
# DEBASHER_RESIDENT_PROCESS_ROLES. Returns 1, with an error, if a task has
# more than one output port read by the Supervisor (a node has a single
# heartbeat channel), or none while the program has a Supervisor (the node
# would run unsupervised, with nothing to say so, as a task of an array
# beyond those the Supervisor connects to would), if the Supervisor has more
# than one task, more than one manual trigger, or one with no initiator port,
# or if it defines a fifo that is neither.
debasher::_register_resident_task_ports()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        return 0
    fi

    # The ports found so far, blank-separated, by
    # <node><DEBASHER_ASSOC_ARRAY_ELEM_SEP><field>
    local -A ports=()
    # The fifos of the business channels, blank-separated
    local held=""

    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        debasher::_add_resident_fifo_ports ports held "${augm_fifoname}" || return 1
    done

    # The Supervisor, if there is one: every node then needs a heartbeat
    # channel to it
    local supervisor
    supervisor=$(debasher::_get_resident_supervisor)

    # One entry for every task, also for one with no port at all, so that
    # every node of the program takes its ports from here
    local processname idx num_tasks node entry
    for processname in "${!DEBASHER_RESIDENT_PROCESS_ROLES[@]}"; do
        [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${processname}]}" = "fbpprocess" ] || continue
        num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
        for (( idx = 0; idx < num_tasks; idx++ )); do
            node="${processname}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${idx}"
            entry=$(debasher::_resident_node_ports_entry ports "${node}" "${supervisor}") || return 1
            DEBASHER_RESIDENT_TASK_PORTS["${node}"]="${entry}"
        done
    done

    # The same for the Supervisor, if there is one. It has a single task:
    # every task would get every held fifo and the heartbeat channels would
    # be split among them, and debasher_stop_resident waits for the
    # .finished of the process, not of a task
    if [ -n "${supervisor}" ]; then
        num_tasks=$(debasher::_get_numtasks_for_process "${supervisor}")
        if [ "${num_tasks}" -ne 1 ]; then
            echo "Error: the Supervisor ${supervisor} has ${num_tasks} tasks, but a resident program has a single Supervisor of a single task" >&2
            return 1
        fi
        node="${supervisor}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}0"
        ports["${node}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}hold"]="${held}"
        entry=$(debasher::_resident_supervisor_ports_entry ports "${node}") || return 1
        DEBASHER_RESIDENT_TASK_PORTS["${node}"]="${entry}"
    fi
}

########
# $1: name of the associative array of the ports, by
# <node><DEBASHER_ASSOC_ARRAY_ELEM_SEP><field>; $2: node, $3: field, $4:
# option, or a value already written as a port (<node>=<port>). Adds the
# port, the option without its leading dashes, to that array.
debasher::_add_resident_task_port()
{
    local -n task_ports_ref=$1
    local port="${4#-}"
    task_ports_ref["$2${DEBASHER_ASSOC_ARRAY_ELEM_SEP}$3"]+=" ${port#-}"
}

########
# Adds to the associative array of the ports named $1 (see
# debasher::_add_resident_task_port) the ports that the fifo $3 gives the
# processes at its two ends, and the fifo to the blank-separated list named
# $2 when it is a business channel. Fails, with an error, for a fifo that
# the Supervisor defines and that is neither a trigger to a node nor its
# manual trigger.
debasher::_add_resident_fifo_ports()
{
    local ports_name=$1
    local -n held_ref=$2
    local augm_fifoname=$3

    local owner="${DEBASHER_PROGRAM_FIFOS[${augm_fifoname}]}"
    local reader="${DEBASHER_FIFO_READERS[${augm_fifoname}]}"
    local kind="${DEBASHER_FIFO_KINDS[${augm_fifoname}]:-}"
    local owner_opt="${DEBASHER_FIFO_OWNER_OPTS[${augm_fifoname}]}"
    local reader_opt="${DEBASHER_FIFO_READER_OPTS[${augm_fifoname}]:-}"
    local owner_role reader_role
    owner_role=$(debasher::_resident_node_role "${owner}")
    reader_role=$(debasher::_resident_node_role "${reader}")

    # A node at the owner's end
    if [ "${owner_role}" = "fbpprocess" ]; then
        debasher::_add_resident_owner_port "${ports_name}" "${owner}" "${owner_opt}" "${reader}" "${reader_role}" "${kind}"
    fi

    # A node at the other end reads it: an input port, and a control port
    # too if the fifo is tagged --control
    if [ "${reader_role}" = "fbpprocess" ]; then
        debasher::_add_resident_task_port "${ports_name}" "${reader}" input "${reader_opt}"
        if [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ]; then
            debasher::_add_resident_task_port "${ports_name}" "${reader}" control "${reader_opt}"
        fi
    fi

    # A business channel: a fifo without a tag between two nodes
    if [ -z "${kind}" ] && [ "${owner_role}" = "fbpprocess" ] && [ "${reader_role}" = "fbpprocess" ]; then
        held_ref+=" ${augm_fifoname}"
    fi

    # The Supervisor's end. It reads the heartbeat channel of a node, the
    # one fifo without a tag that a node writes to it (the checks of
    # debasher::_validate_resident_channels refuse a tagged one), and
    # defines only its initiator ports and its manual trigger
    if [ "${reader_role}" = "supervisor" ]; then
        debasher::_add_resident_heartbeat_port "${ports_name}" "${owner}" "${reader}" "${reader_opt}"
    fi
    if [ "${owner_role}" = "supervisor" ]; then
        debasher::_add_resident_supervisor_control_port "${ports_name}" "${augm_fifoname}" "${owner}" "${owner_opt}" "${reader}" "${kind}" || return 1
    fi
}

########
# Adds to the associative array of the ports named $1 (see
# debasher::_add_resident_task_port) the port of the node $2 at the owner's
# end of a fifo, which it defines through the option $3 and whose other end
# is $4, of role $5, with the tag $6: an output port, unless the fifo is
# tagged and fed from outside the program, in which case the owner reads it;
# an output read by the Supervisor is its heartbeat channel too.
debasher::_add_resident_owner_port()
{
    local ports_name=$1
    local owner=$2
    local owner_opt=$3
    local reader=$4
    local reader_role=$5
    local kind=$6

    if [ -n "${kind}" ] && [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
        # The tag, "control" or "external", is also the name of the field
        debasher::_add_resident_task_port "${ports_name}" "${owner}" input "${owner_opt}"
        debasher::_add_resident_task_port "${ports_name}" "${owner}" "${kind}" "${owner_opt}"
    else
        debasher::_add_resident_task_port "${ports_name}" "${owner}" output "${owner_opt}"
        if [ "${reader_role}" = "supervisor" ]; then
            debasher::_add_resident_task_port "${ports_name}" "${owner}" supervisor "${owner_opt}"
        fi
    fi
}

########
# Adds to the associative array of the ports named $1 (see
# debasher::_add_resident_task_port) the port of the Supervisor $3 for the
# fifo $2 that it defines through the option $4, whose other end is $5, with
# the tag $6: its manual trigger, tagged --control and fed from outside, or
# an initiator port, tagged --control and read by a node. Fails, with an
# error, for any other fifo.
debasher::_add_resident_supervisor_control_port()
{
    local ports_name=$1
    local augm_fifoname=$2
    local owner=$3
    local owner_opt=$4
    local reader=$5
    local kind=$6

    if [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ] && [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
        debasher::_add_resident_task_port "${ports_name}" "${owner}" manual_trigger "${owner_opt}"
    elif [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ]; then
        debasher::_add_resident_task_port "${ports_name}" "${owner}" initiators "${owner_opt}"
    else
        echo "Error: the Supervisor ${owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*} defines fifo ${augm_fifoname}, but the only fifos a Supervisor defines are its initiator ports, read by nodes, and its manual trigger fed from outside the program, both tagged --control" >&2
        return 1
    fi
}

########
# Adds to the ports of the Supervisor $3, in the associative array of the
# ports named $1 (see debasher::_add_resident_task_port), the heartbeat
# channel of the node $2, read through the option $4, as <node>=<port>, and the startup deadline of the node when its
# computational specifications give one (startup_timeout_s), as
# <node>=<seconds>.
debasher::_add_resident_heartbeat_port()
{
    local ports_name=$1
    local node=$2
    local supervisor_node=$3
    local reader_opt=$4

    local hb_port="${reader_opt#-}"
    local node_label=$(debasher::_resident_node_display_name "${node}")
    debasher::_add_resident_task_port "${ports_name}" "${supervisor_node}" nodes "${node_label}=${hb_port#-}"
    local startup
    startup=$(debasher::extract_attr_from_process_comp_specs "$(debasher::extract_process_comp_specs "${DEBASHER_INITIAL_PROCESS_SPEC[${node%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*}]:-}")" startup_timeout_s)
    if [ "${startup}" != "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        debasher::_add_resident_task_port "${ports_name}" "${supervisor_node}" startup "${node_label}=${startup}"
    fi
}

########
# Prints the name of the Supervisor of the resident program, or nothing
# when it has none.
debasher::_get_resident_supervisor()
{
    local processname supervisor=""
    for processname in "${!DEBASHER_RESIDENT_PROCESS_ROLES[@]}"; do
        if [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${processname}]}" = "supervisor" ]; then
            supervisor="${processname}"
        fi
    done
    echo "${supervisor}"
}

########
# Prints the entry of DEBASHER_RESIDENT_TASK_PORTS of the node $2, from the
# associative array of the ports named $1 (see
# debasher::_add_resident_task_port): input=...;output=...;control=...;
# external=...;supervisor=... (see debasher::_register_resident_task_ports).
# $3 is the Supervisor of the program, or empty. Fails, with an error, for a
# node with more than one output read by the Supervisor, or with none in a
# program with a Supervisor.
debasher::_resident_node_ports_entry()
{
    local -n node_ports_ref=$1
    local node=$2
    local supervisor=$3

    local field list entry=""
    for field in input output control external supervisor; do
        list=$(debasher::_sorted_comma_list "${node_ports_ref[${node}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${field}]:-}")
        if [ "${field}" = "supervisor" ] && [[ "${list}" == *,* ]]; then
            echo "Error: node $(debasher::_resident_node_display_name "${node}") has more than one output read by the Supervisor (${list}), but a node has a single heartbeat channel" >&2
            return 1
        fi
        if [ "${field}" = "supervisor" ] && [ -z "${list}" ] && [ -n "${supervisor}" ]; then
            echo "Error: node $(debasher::_resident_node_display_name "${node}") has no output read by the Supervisor ${supervisor}, but in a program with a Supervisor every node has a heartbeat channel: without one, the node would run unsupervised" >&2
            return 1
        fi
        entry+=";${field}=${list}"
    done
    echo "${entry#;}"
}

########
# Prints the entry of DEBASHER_RESIDENT_TASK_PORTS of the Supervisor task
# $2, from the associative array of the ports named $1 (see
# debasher::_add_resident_task_port): nodes=...;initiators=...;
# manual_trigger=...;startup=...;hold=... (see
# debasher::_register_resident_task_ports). Fails, with an error, for a
# Supervisor with more than one manual trigger, or with one and no initiator
# port.
debasher::_resident_supervisor_ports_entry()
{
    local -n supervisor_ports_ref=$1
    local node=$2

    local field list entry=""
    local initiators=""
    for field in nodes initiators manual_trigger startup hold; do
        list=$(debasher::_sorted_comma_list "${supervisor_ports_ref[${node}${DEBASHER_ASSOC_ARRAY_ELEM_SEP}${field}]:-}")
        if [ "${field}" = "initiators" ]; then
            initiators="${list}"
        fi
        if [ "${field}" = "manual_trigger" ] && [[ "${list}" == *,* ]]; then
            echo "Error: the Supervisor ${node%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*} has more than one manual trigger fed from outside the program (${list})" >&2
            return 1
        fi
        # A trigger that arrives there would have nowhere to go
        if [ "${field}" = "manual_trigger" ] && [ -n "${list}" ] && [ -z "${initiators}" ]; then
            echo "Error: the Supervisor ${node%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*} has a manual trigger fed from outside the program (${list}) but no initiator port, so nothing it receives there can reach a node: make one of the nodes an initiator, or remove the manual trigger port" >&2
            return 1
        fi
        entry+=";${field}=${list}"
    done
    echo "${entry#;}"
}
