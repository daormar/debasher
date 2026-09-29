"""
The Supervisor wiring of a resident program (see "Script generation and
import of a resident program" in doc/design_doc_webui.md): the channels
between the Supervisor and the nodes, which the program model never holds.
Script generation derives them from whether the program has a Supervisor,
from its nodes and from which of them are initiators, and adds them to a
copy of the program as options and connections (SupervisorWiring), so that
the options of the wiring are written by the same rules as those of the
user. Their labels are fixed, and no option of the user may take them.
"""

import uuid

from .models import Program, ProgramEdge, ProgramOption, ProgramProcess

# The labels of the Supervisor wiring on a node, which no option of the user
# may take.
HEARTBEAT_LABEL = "-outhb"
TRIGGER_LABEL = "-trigger"
RESERVED_NODE_LABELS = (HEARTBEAT_LABEL, TRIGGER_LABEL)

# The labels of the Supervisor wiring on the Supervisor that do not depend
# on a node.
MANUAL_LABEL = "-manual"
NO_HOLD_FIFOS_LABEL = "-no_hold_fifos"

_TASK_INDEXED_MODES = {"array", "generator"}


def heartbeat_label(process_name: str) -> str:
    """The input of the Supervisor that reads the heartbeat channel of a node.
    The name of the process comes first, never last: "-hb_smith" would end
    in "ith" and be taken for a fanout family."""
    return f"-{process_name}_hb"


def trigger_label(process_name: str) -> str:
    """The output of the Supervisor that is the trigger port to an initiator."""
    return f"-out{process_name}_trig"


def _task_suffix(mode: str) -> str:
    """What a fifo name of a task adds, so that each task has its own."""
    if mode == "array":
        return "_${idx}"
    if mode == "generator":
        return "_${task_idx}"
    return ""


def _option(label, direction, description, **fields) -> ProgramOption:
    return ProgramOption(
        id=str(uuid.uuid4()),
        label=label,
        direction=direction,
        dataType=fields.pop("dataType", "string"),
        description=description,
        value=fields.pop("value", ""),
        commandLine=fields.pop("commandLine", False),
        **fields,
    )


def _connect(edges, source_process, source_option, target_process, target_option) -> None:
    """Connects two options of the copy of the program, as the frontend would:
    an edge, and the value of the target that names its source."""
    target_option.value = f"[{source_process.name};{source_option.label}]"
    edges.append(
        ProgramEdge(
            id=str(uuid.uuid4()),
            sourceProcessId=source_process.id,
            sourceOptionId=source_option.id,
            targetProcessId=target_process.id,
            targetOptionId=target_option.id,
        )
    )


def _is_fanout_label(label: str) -> bool:
    return label.endswith("ith") and label[: -len("ith")].lstrip("-") != ""


def _count_source(program: Program, node: ProgramProcess) -> ProgramOption:
    """
    The command line option that counts the tasks of an array or generator
    node: the one that counts the fanout family that the node is connected
    to, directly or through the tasks of another array. Raises ValueError
    when the node reaches no such family, since the Supervisor could not
    count its heartbeat channels.
    """
    processes_by_id = {process.id: process for process in program.processes}
    seen = {node.id}
    pending = [node]
    while pending:
        current = pending.pop()
        for edge in program.edges:
            if current.id not in (edge.sourceProcessId, edge.targetProcessId):
                continue
            if edge.sourceProcessId == current.id:
                other = processes_by_id.get(edge.targetProcessId)
                other_option_id = edge.targetOptionId
            else:
                other = processes_by_id.get(edge.sourceProcessId)
                other_option_id = edge.sourceOptionId
            if other is None or other.id in seen:
                continue
            if other.optionsHandler.mode in _TASK_INDEXED_MODES:
                seen.add(other.id)
                pending.append(other)
                continue
            other_option = next((o for o in other.options if o.id == other_option_id), None)
            if other_option is None or not _is_fanout_label(other_option.label):
                continue
            count = next((o for o in other.options if o.id == other_option.countSourceOptionId), None)
            if count is not None and count.commandLine:
                return count
    raise ValueError(
        f'Process "{node.name}" is an {node.optionsHandler.mode} node of a resident program '
        "with a Supervisor, but it reaches no fanout family counted by a command line "
        "option, directly or through the tasks of another array: the Supervisor could "
        "not tell how many heartbeat channels to read. Connect it to a fanout family "
        "whose count source is a command line option."
    )


class SupervisorWiring:
    """
    The Supervisor wiring of a copy of a resident program, added to it as
    options and connections: to each node its heartbeat channel, to each
    initiator its control port, and to the Supervisor, if there is one, the
    other ends of both, its manual trigger port, -no_hold_fifos and the
    command line options that count its fanout families.
    """

    def __init__(self, program: Program):
        self.program = program
        self.supervisor = next((p for p in program.processes if p.nodeKind == "Supervisor"), None)
        self.nodes = [p for p in program.processes if p.nodeKind != "Supervisor"]
        self.edges = list(program.edges)
        self.supervisor_options: list[ProgramOption] = []
        # The command line options of the Supervisor that count its fanout
        # families, by label: two families counted by the same option share
        # it.
        self.count_options: dict[str, ProgramOption] = {}

    def count_option(self, node: ProgramProcess) -> ProgramOption:
        """The option of the Supervisor that counts the tasks of `node`, an
        array or generator node."""
        count = _count_source(self.program, node)
        if count.label not in self.count_options:
            self.count_options[count.label] = _option(
                count.label,
                "input",
                count.description,
                dataType=count.dataType,
                commandLine=True,
                mandatory=count.mandatory,
            )
        return self.count_options[count.label]

    def add_heartbeat(self, node: ProgramProcess) -> None:
        """The heartbeat channel of a node: an output of the node, read by an
        input of the Supervisor, or by a fanout family of it for an array or
        generator node, one for each task."""
        heartbeat = _option(
            HEARTBEAT_LABEL,
            "output",
            "heartbeat channel to the Supervisor",
            channel="fifo",
            value=f"{node.name}_hb{_task_suffix(node.optionsHandler.mode)}",
        )
        node.options.append(heartbeat)
        if self.supervisor is None:
            return
        if node.optionsHandler.mode in _TASK_INDEXED_MODES:
            reader = _option(
                heartbeat_label(node.name) + "ith",
                "input",
                f"heartbeat channel of the i'th task of {node.name}",
                countSourceOptionId=self.count_option(node).id,
            )
        else:
            reader = _option(heartbeat_label(node.name), "input", f"heartbeat channel of {node.name}")
        self.supervisor_options.append(reader)
        _connect(self.edges, node, heartbeat, self.supervisor, reader)

    def add_control_port(self, node: ProgramProcess) -> None:
        """The control port of an initiator: connected to a trigger port of
        the Supervisor, a fanout family of it for an array or generator
        initiator, or, without a Supervisor, written from outside the
        program."""
        suffix = _task_suffix(node.optionsHandler.mode)
        if self.supervisor is None:
            node.options.append(
                _option(
                    TRIGGER_LABEL,
                    "input",
                    "control port of this initiator, written from outside the program",
                    channel="fifo",
                    fifoTag="control",
                    value=f"{node.name}_trigger{suffix}",
                )
            )
            return
        control = _option(TRIGGER_LABEL, "input", "control port of this initiator")
        node.options.append(control)
        if node.optionsHandler.mode in _TASK_INDEXED_MODES:
            trigger = _option(
                trigger_label(node.name) + "ith",
                "output",
                f"trigger port to the i'th task of {node.name}",
                channel="fifo",
                fifoTag="control",
                value=f"{self.supervisor.name}_{node.name}_trig_${{i}}",
                countSourceOptionId=self.count_option(node).id,
            )
        else:
            trigger = _option(
                trigger_label(node.name),
                "output",
                f"trigger port to {node.name}",
                channel="fifo",
                fifoTag="control",
                value=f"{self.supervisor.name}_{node.name}_trig",
            )
        self.supervisor_options.append(trigger)
        _connect(self.edges, self.supervisor, trigger, node, control)

    def finish(self) -> None:
        """Gives the Supervisor its options, the ports of its own after
        those that face the nodes, and the program its connections."""
        if self.supervisor is not None:
            self.supervisor.options = [
                *self.supervisor_options,
                _option(
                    MANUAL_LABEL,
                    "input",
                    "manual trigger port, written from outside the program",
                    channel="fifo",
                    fifoTag="control",
                    value=f"{self.supervisor.name}_manual",
                ),
                _option(
                    NO_HOLD_FIFOS_LABEL,
                    "input",
                    "do not hold the FIFOs of the business channels",
                    dataType="None",
                    commandLine=True,
                ),
                *self.count_options.values(),
            ]
        self.program.edges = self.edges
