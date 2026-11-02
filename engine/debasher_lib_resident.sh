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
# Echoes the source of the (small, self-contained) Python program that
# classifies a resident process's role from its source, read from
# stdin: prints exactly one of "supervisor", "fbpprocess" or "unknown"
# to stdout. It looks for a top-level class definition whose bases
# resolve (following plain "import"/"from ... import ... as ..."
# aliasing) to the literal names "Supervisor" or "FBPProcess" (the
# two base classes of the engine for resident processes), or
# "ProgramLauncher" or "DirectoryWatcher", nodes of the runtime library
# that derive from FBPProcess (one launches a general program for each
# request, the other sends a request for each file that arrives). This
# is a static check: ast.parse never imports or executes the given
# source, unlike a real "issubclass" check, which is not used here
# since it would need to run
# inside each process's own conda/docker environment just to answer a
# type question, before the program has even been launched.
debasher::_resident_role_classifier_src()
{
    cat <<'EOF'
import ast
import sys

BASE_ROLES = {
    "Supervisor": "supervisor",
    "FBPProcess": "fbpprocess",
    "ProgramLauncher": "fbpprocess",
    "DirectoryWatcher": "fbpprocess",
}


def resolved_base_names(tree):
    """Local name -> canonical base name, following import aliasing."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in BASE_ROLES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def base_identifier(base_node):
    if isinstance(base_node, ast.Name):
        return base_node.id
    if isinstance(base_node, ast.Attribute):
        return base_node.attr
    return None


def classify(source):
    tree = ast.parse(source)

    aliases = resolved_base_names(tree)
    found_role = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base_identifier(base)
            if name is None:
                continue
            canonical = aliases.get(name, name)
            role = BASE_ROLES.get(canonical)
            if role == "supervisor":
                return "supervisor"
            if role == "fbpprocess" and found_role is None:
                found_role = "fbpprocess"
    return found_role or "unknown"


def main():
    try:
        print(classify(sys.stdin.read()))
    except SyntaxError as exc:
        print(f"Error: invalid Python source ({exc})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
EOF
}

########
# Classifies a resident program's process as "supervisor",
# "fbpprocess" or "unknown" by running debasher::_resident_role_classifier_src
# against the process's Python heredoc source (see
# debasher::_get_resident_process_source). Returns 1, with an error on
# stderr, if the process is not a Python heredoc process at all, or if
# its source is not valid Python.
debasher::_classify_resident_process_role()
{
    local processname=$1

    local source
    if ! source=$(debasher::_get_resident_process_source "${processname}"); then
        echo "Error: process ${processname} does not provide its code as a Python heredoc, required for a resident program" >&2
        return 1
    fi

    printf '%s' "${source}" | "${PYTHON}" -c "$(debasher::_resident_role_classifier_src)"
}

########
# Echoes the source of the (small, self-contained) Python program that
# checks the name of the class of a resident process, read from stdin,
# with the name of the process as its only argument. The class that
# derives from a class of the runtime library (resolved as
# debasher::_resident_role_classifier_src resolves it) is the node, and
# there is exactly one. It is named after its process, in CamelCase:
# every part of the process name between dots and underscores, with its
# first letter in upper case ("counter" -> "Counter", "org.ns.count_words"
# -> "OrgNsCountWords"), so that the name, which the runtime also gives
# to the logger of the node, follows from the process. And that name
# hides nothing that the code of the node could need: a class of the
# runtime library, a Python builtin, or a name that the heredoc binds at
# its top level, such as an import of its preamble. Prints nothing and
# exits 0 if the class passes, or prints the first violation to stderr
# and exits 1. Like the classifier, it only parses the source.
debasher::_resident_class_name_checker_src()
{
    cat <<'EOF'
import ast
import builtins
import sys

RUNTIME_CLASSES = ("FBPProcess", "Supervisor", "ProgramLauncher", "DirectoryWatcher")

# Nodes whose names live in a scope of their own, not in the module's
SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def camel_case(processname):
    parts = processname.replace(".", "_").split("_")
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def runtime_aliases(tree):
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in RUNTIME_CLASSES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def base_identifier(base_node):
    if isinstance(base_node, ast.Name):
        return base_node.id
    if isinstance(base_node, ast.Attribute):
        return base_node.attr
    return None


def node_classes(tree):
    aliases = runtime_aliases(tree)
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base_identifier(base)
            if name is not None and aliases.get(name, name) in RUNTIME_CLASSES:
                classes.append(node)
                break
    return classes


def bindings(node):
    """The names that `node`, a statement at the top level, binds in the module."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name, node.lineno
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            if alias.name != "*":
                yield alias.asname or alias.name.split(".")[0], node.lineno
        return
    if isinstance(node, SCOPES):
        return
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield node.id, node.lineno
    for child in ast.iter_child_nodes(node):
        yield from bindings(child)


def check(processname, source):
    tree = ast.parse(source)
    expected = camel_case(processname)

    if expected in RUNTIME_CLASSES:
        return (f"the class of process {processname} is named {expected}, after the process, "
                "which is a class of the runtime library that it would hide: rename the process")
    if expected in dir(builtins):
        return (f"the class of process {processname} is named {expected}, after the process, "
                "which is a Python builtin that it would hide: rename the process")

    classes = node_classes(tree)
    if len(classes) != 1:
        names = ", ".join(node.name for node in classes)
        return (f"process {processname} defines {len(classes)} classes deriving from a class of "
                f"the runtime library ({names}), but a node defines exactly one")
    node_class = classes[0]
    if node_class.name != expected:
        return (f"process {processname} names its class {node_class.name}, but the class of a "
                f"node is named after its process, in CamelCase: {expected}")

    for statement in tree.body:
        if statement is node_class:
            continue
        for name, line in bindings(statement):
            if name == expected:
                return (f"the class of process {processname}, {expected}, has the name of what "
                        f"its code also defines on line {line}, which it would hide")
    return None


def main():
    try:
        violation = check(sys.argv[1], sys.stdin.read())
    except SyntaxError as exc:
        print(f"Error: invalid Python source ({exc})", file=sys.stderr)
        sys.exit(1)
    if violation is not None:
        print(f"Error: {violation}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
EOF
}

########
# Checks the name of the class of a resident program's process by running
# debasher::_resident_class_name_checker_src against its Python heredoc
# source (see debasher::_get_resident_process_source). Returns 1, with an
# error on stderr, if the name breaks one of its rules, or if the process
# is not a Python heredoc process at all.
debasher::_check_resident_class_name()
{
    local processname=$1

    local source
    if ! source=$(debasher::_get_resident_process_source "${processname}"); then
        echo "Error: process ${processname} does not provide its code as a Python heredoc, required for a resident program" >&2
        return 1
    fi

    printf '%s' "${source}" | "${PYTHON}" -c "$(debasher::_resident_class_name_checker_src)" "${processname}"
}

########
# Validates every process of a "resident" program (see
# doc/design_doc_resident.md): each one must classify (via
# debasher::_classify_resident_process_role) as either "supervisor" or
# "fbpprocess", with its class named as
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
# Checks the tags of the program's fifos (see DEBASHER_FIFO_KINDS) once
# every process has defined its options and the other end of every fifo is
# known (see debasher::_register_fifos_read_by_process). A general program
# may not use them. In a resident program they have to be used as they say,
# and a round has to be able to reach every node (see the design doc's
# "Channel kinds declared with the fifo"). Prints an error and returns 1 on
# the first violation found.
debasher::_validate_program_fifo_kinds()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        local augm_fifoname
        for augm_fifoname in "${!DEBASHER_FIFO_KINDS[@]}"; do
            echo "Error: fifo ${augm_fifoname} is tagged --${DEBASHER_FIFO_KINDS[${augm_fifoname}]}, which only a '${DEBASHER_PROGRAM_TYPE_RESIDENT}' program may use" >&2
            return 1
        done
        return 0
    fi

    debasher::_validate_resident_channels
}

########
# The name of a node for a message: the process name, or
# <process>:<idx> for a task of an array (as debasher_stop_resident's -x
# names it). $1 is a node as the fifo registries store it,
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
    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"

    # Every task of every business node
    local -A is_node=()
    debasher::_collect_resident_business_nodes

    # Edges of the graph, and the initiators, which start the walk
    local -A successors=()
    local -A reached=()
    local -a queue=()
    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        debasher::_add_resident_fifo_to_graph "${augm_fifoname}" || return 1
        debasher::_check_resident_fifo_owner_opt "${augm_fifoname}" || return 1
    done

    debasher::_walk_resident_graph_from_initiators
    debasher::_check_every_resident_node_reached
}

########
# Fills is_node, an associative array of debasher::_validate_resident_channels
# (seen by dynamic scope), with every task of every FBPProcess, as
# <process><DEBASHER_ASSOC_ARRAY_ELEM_SEP><idx>.
debasher::_collect_resident_business_nodes()
{
    local processname idx num_tasks
    for processname in "${!DEBASHER_RESIDENT_PROCESS_ROLES[@]}"; do
        [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${processname}]}" = "fbpprocess" ] || continue
        num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
        for (( idx = 0; idx < num_tasks; idx++ )); do
            is_node["${processname}${sep}${idx}"]=1
        done
    done
}

########
# Adds the fifo $1 to the graph of debasher::_validate_resident_channels,
# whose is_node, successors, reached and queue it sees by dynamic scope: a
# fifo without a tag between two nodes is an edge from its owner to its
# reader; a fifo tagged --control makes an initiator of the node that reads
# it (from outside the program, its owner; from the Supervisor, its reader),
# which goes into the queue of the walk. Fails, with an error, for a fifo
# tagged --external that a process of the program reads, and for one tagged
# --control that is neither fed from outside nor written by the Supervisor
# to a node.
debasher::_add_resident_fifo_to_graph()
{
    local augm_fifoname=$1

    local owner="${DEBASHER_PROGRAM_FIFOS[${augm_fifoname}]}"
    local reader="${DEBASHER_FIFO_READERS[${augm_fifoname}]}"
    local kind="${DEBASHER_FIFO_KINDS[${augm_fifoname}]:-}"
    local owner_proc="${owner%%${sep}*}"
    local reader_proc="${reader%%${sep}*}"
    local initiator
    case "${kind}" in
        "")
            if [ -n "${is_node[${owner}]+x}" ] && [ -n "${is_node[${reader}]+x}" ]; then
                successors["${owner}"]+=" ${reader}"
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
            elif [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${owner_proc}]:-}" = "supervisor" ] && [ -n "${is_node[${reader}]+x}" ]; then
                initiator="${reader}"
            else
                echo "Error: fifo ${augm_fifoname} is tagged --control, but it is neither fed from outside the program nor written by the Supervisor to a node" >&2
                return 1
            fi
            if [ -n "${is_node[${initiator}]+x}" ] && [ -z "${reached[${initiator}]+x}" ]; then
                reached["${initiator}"]=1
                queue+=("${initiator}")
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
# Marks in reached, an associative array of
# debasher::_validate_resident_channels (seen by dynamic scope, with its
# successors and queue), every node that a round can reach from the
# initiators in the queue, walking the edges breadth first.
debasher::_walk_resident_graph_from_initiators()
{
    local head=0 node next
    while [ "${head}" -lt "${#queue[@]}" ]; do
        node="${queue[head]}"
        head=$((head + 1))
        for next in ${successors[${node}]:-}; do
            if [ -z "${reached[${next}]+x}" ]; then
                reached["${next}"]=1
                queue+=("${next}")
            fi
        done
    done
}

########
# Fails, with an error that names them sorted, when a node of is_node is not
# in reached, both associative arrays of
# debasher::_validate_resident_channels seen by dynamic scope: no round
# could reach it.
debasher::_check_every_resident_node_reached()
{
    local -a unreached=()
    local node
    for node in "${!is_node[@]}"; do
        if [ -z "${reached[${node}]+x}" ]; then
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
# the output ports to the initiators it triggers, the input port of a manual
# trigger fed from outside, and the startup deadline of each node that gives
# one in its computational specifications (startup_timeout_s), as
# <node>=<seconds>, and the fifos of the business channels, those without a
# tag between two nodes, which it holds open so that what they hold outlives
# the crash of both nodes of a channel, as names relative to the fifo
# directory of the program, <owner process>/<fifo>:
#
#   nodes=<node>=<port>,...;trigger=<ports>;manual_trigger=<port>;startup=<node>=<seconds>,...;hold=<fifos>
#
# each list sorted and separated by commas, and possibly empty. A no-op when
# the program is not resident. Needs the checks of
# debasher::_validate_resident_channels to have passed, and
# DEBASHER_RESIDENT_PROCESS_ROLES. Returns 1, with an error, if a task has
# more than one output port read by the Supervisor (a node has a single
# heartbeat channel), or none while the program has a Supervisor (the node
# would run unsupervised, with nothing to say so, as a task of an array
# beyond those the Supervisor connects to would), if the Supervisor has more
# than one manual trigger, or if it defines a fifo that is neither.
debasher::_register_resident_task_ports()
{
    if [ "${DEBASHER_PROGRAM_TYPE}" != "${DEBASHER_PROGRAM_TYPE_RESIDENT}" ]; then
        return 0
    fi

    local sep="${DEBASHER_ASSOC_ARRAY_ELEM_SEP}"

    # The ports found so far, blank-separated, by <node><sep><field>
    local -A ports=()
    # The fifos of the business channels, blank-separated
    local held=""

    local augm_fifoname
    for augm_fifoname in "${!DEBASHER_PROGRAM_FIFOS[@]}"; do
        debasher::_add_resident_fifo_ports "${augm_fifoname}" || return 1
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
            node="${processname}${sep}${idx}"
            entry=$(debasher::_resident_node_ports_entry "${node}" "${supervisor}") || return 1
            DEBASHER_RESIDENT_TASK_PORTS["${node}"]="${entry}"
        done
    done

    # The same for the Supervisor, if there is one
    for processname in "${!DEBASHER_RESIDENT_PROCESS_ROLES[@]}"; do
        [ "${DEBASHER_RESIDENT_PROCESS_ROLES[${processname}]}" = "supervisor" ] || continue
        num_tasks=$(debasher::_get_numtasks_for_process "${processname}")
        for (( idx = 0; idx < num_tasks; idx++ )); do
            node="${processname}${sep}${idx}"
            ports["${node}${sep}hold"]="${held}"
            entry=$(debasher::_resident_supervisor_ports_entry "${node}") || return 1
            DEBASHER_RESIDENT_TASK_PORTS["${node}"]="${entry}"
        done
    done
}

########
# $1: node, $2: field, $3: option, or a value already written as a port
# (<node>=<port>). Adds the port, the option without its leading dashes, to
# ports, the associative array of debasher::_register_resident_task_ports
# seen by dynamic scope.
debasher::_add_resident_task_port()
{
    local port="${3#-}"
    ports["$1${sep}$2"]+=" ${port#-}"
}

########
# Adds to ports and held, of debasher::_register_resident_task_ports (seen
# by dynamic scope), the ports that the fifo $1 gives the processes at its
# two ends, and the fifo to held when it is a business channel. Fails, with
# an error, for a fifo that the Supervisor defines and that is neither a
# trigger to a node nor its manual trigger.
debasher::_add_resident_fifo_ports()
{
    local augm_fifoname=$1

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
        debasher::_add_resident_owner_port "${owner}" "${owner_opt}" "${reader}" "${reader_role}" "${kind}"
    fi

    # A node at the other end reads it: an input port, and a control port
    # too if the fifo is tagged --control
    if [ "${reader_role}" = "fbpprocess" ]; then
        debasher::_add_resident_task_port "${reader}" input "${reader_opt}"
        if [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ]; then
            debasher::_add_resident_task_port "${reader}" control "${reader_opt}"
        fi
    fi

    # A business channel: a fifo without a tag between two nodes
    if [ -z "${kind}" ] && [ "${owner_role}" = "fbpprocess" ] && [ "${reader_role}" = "fbpprocess" ]; then
        held+=" ${augm_fifoname}"
    fi

    # The Supervisor's end. It reads the heartbeat channel of a node, the
    # one fifo without a tag that a node writes to it (the checks of
    # debasher::_validate_resident_channels refuse a tagged one), and
    # defines only its triggers
    if [ "${reader_role}" = "supervisor" ]; then
        debasher::_add_resident_heartbeat_port "${owner}" "${reader}" "${reader_opt}"
    fi
    if [ "${owner_role}" = "supervisor" ]; then
        debasher::_add_resident_supervisor_trigger_port "${augm_fifoname}" "${owner}" "${owner_opt}" "${reader}" "${kind}" || return 1
    fi
}

########
# Adds to ports (of debasher::_register_resident_task_ports, seen by
# dynamic scope) the port of the node $1 at the owner's end of a fifo, which
# it defines through the option $2 and whose other end is $3, of role $4,
# with the tag $5: an output port, unless the fifo is tagged and fed from
# outside the program, in which case the owner reads it; an output read by
# the Supervisor is its heartbeat channel too.
debasher::_add_resident_owner_port()
{
    local owner=$1
    local owner_opt=$2
    local reader=$3
    local reader_role=$4
    local kind=$5

    if [ -n "${kind}" ] && [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
        # The tag, "control" or "external", is also the name of the field
        debasher::_add_resident_task_port "${owner}" input "${owner_opt}"
        debasher::_add_resident_task_port "${owner}" "${kind}" "${owner_opt}"
    else
        debasher::_add_resident_task_port "${owner}" output "${owner_opt}"
        if [ "${reader_role}" = "supervisor" ]; then
            debasher::_add_resident_task_port "${owner}" supervisor "${owner_opt}"
        fi
    fi
}

########
# Adds to ports (of debasher::_register_resident_task_ports, seen by
# dynamic scope) the port of the Supervisor $2 for the fifo $1 that it
# defines through the option $3, whose other end is $4, with the tag $5: its
# manual trigger, tagged --control and fed from outside, or a trigger to a
# node, tagged --control. Fails, with an error, for any other fifo.
debasher::_add_resident_supervisor_trigger_port()
{
    local augm_fifoname=$1
    local owner=$2
    local owner_opt=$3
    local reader=$4
    local kind=$5

    if [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ] && [ "${reader}" = "${DEBASHER_EXTERNAL_FIFO_END}" ]; then
        debasher::_add_resident_task_port "${owner}" manual_trigger "${owner_opt}"
    elif [ "${kind}" = "${DEBASHER_FIFO_KIND_CONTROL}" ]; then
        debasher::_add_resident_task_port "${owner}" trigger "${owner_opt}"
    else
        echo "Error: the Supervisor ${owner%%${DEBASHER_ASSOC_ARRAY_ELEM_SEP}*} defines fifo ${augm_fifoname}, but the only fifos a Supervisor defines are its triggers to nodes and its manual trigger fed from outside the program, both tagged --control" >&2
        return 1
    fi
}

########
# Adds to the ports of the Supervisor $2 (in ports, seen by dynamic scope)
# the heartbeat channel of the node $1, read through the option $3, as
# <node>=<port>, and the startup deadline of the node when its
# computational specifications give one (startup_timeout_s), as
# <node>=<seconds>.
debasher::_add_resident_heartbeat_port()
{
    local node=$1
    local supervisor_node=$2
    local reader_opt=$3

    local hb_port="${reader_opt#-}"
    local node_label=$(debasher::_resident_node_display_name "${node}")
    debasher::_add_resident_task_port "${supervisor_node}" nodes "${node_label}=${hb_port#-}"
    local startup
    startup=$(debasher::extract_attr_from_process_comp_specs "$(debasher::extract_process_comp_specs "${DEBASHER_INITIAL_PROCESS_SPEC[${node%%${sep}*}]:-}")" startup_timeout_s)
    if [ "${startup}" != "${DEBASHER_ATTR_NOT_FOUND}" ]; then
        debasher::_add_resident_task_port "${supervisor_node}" startup "${node_label}=${startup}"
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
# Prints the entry of DEBASHER_RESIDENT_TASK_PORTS of the node $1, from
# ports (seen by dynamic scope): input=...;output=...;control=...;
# external=...;supervisor=... (see debasher::_register_resident_task_ports).
# $2 is the Supervisor of the program, or empty. Fails, with an error, for a
# node with more than one output read by the Supervisor, or with none in a
# program with a Supervisor.
debasher::_resident_node_ports_entry()
{
    local node=$1
    local supervisor=$2

    local field list entry=""
    for field in input output control external supervisor; do
        list=$(debasher::_sorted_comma_list "${ports[${node}${sep}${field}]:-}")
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
# $1, from ports (seen by dynamic scope): nodes=...;trigger=...;
# manual_trigger=...;startup=...;hold=... (see
# debasher::_register_resident_task_ports). Fails, with an error, for a
# Supervisor with more than one manual trigger.
debasher::_resident_supervisor_ports_entry()
{
    local node=$1

    local field list entry=""
    for field in nodes trigger manual_trigger startup hold; do
        list=$(debasher::_sorted_comma_list "${ports[${node}${sep}${field}]:-}")
        if [ "${field}" = "manual_trigger" ] && [[ "${list}" == *,* ]]; then
            echo "Error: the Supervisor ${node%%${sep}*} has more than one manual trigger fed from outside the program (${list})" >&2
            return 1
        fi
        entry+=";${field}=${list}"
    done
    echo "${entry#;}"
}
