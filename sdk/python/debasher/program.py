"""
A program as the SDK describes it: the processes it adds, each with the
specifications of its use there, as the `_program` method of a module
adds them with `add_debasher_process`, and what the program is run with.
`write()` turns it into the program model of the web UI (`api/models.py`)
and saves it as the editor does (`api/persistence.py`): the program
metadata in `.debasher/program.json` and the generated module beside it.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import DefinitionError
from .layout import layout
from .process import Node, Option, Process, Source, Supervisor, check_program_name

# Every id of the program model is derived from the names, so that writing
# the same program twice gives the same metadata.
_ID_NAMESPACE = uuid.UUID("6f1c2b7e-3a9d-4d0e-9c1f-2b5a8e4d7c10")


def _id(*names: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, "/".join(names)))


# The computational specifications that only a node of a resident program
# reads, under the names of the engine: its limits (see "Limits of a node"
# in doc/design_doc_resident.md) and the other specifications of a node.
NODE_SPECS = (
    "input_log_max_mb",
    "out_backlog_max_mb",
    "out_backlog_fail_mb",
    "gil_switch_interval_ms",
    "startup_timeout_s",
    "max_concurrent_runs",
    "batch_sched",
    "heartbeat_timeout_s",
)


@dataclass
class _Member:
    """A process added to the program, with the specifications of its use."""

    process: Process
    cpus: float | None = None
    mem: float | None = None
    time: str | None = None
    processdeps: str | None = None
    force: bool = False
    position: tuple[float, float] | None = None
    node_specs: dict[str, float | int | str] | None = None


@dataclass
class _Edge:
    source: Option
    target: Option
    display: str


@dataclass
class _ScriptCopy:
    """An external alias to copy beside the module: its file, and its path
    relative to the home directory."""

    source: Path
    relative: Path


class Program:
    """
    A program: its name, which names its module (`<name>.sh`) and the file
    that defines it (`<name>.py`), its description, the options of its
    command line that a run is given (`program_options`, label to value,
    what "Set program options" of the editor holds), and what a module
    holds beside its processes: the `preamble` (Bash before the functions,
    such as `load_debasher_module` lines), the environment variables of
    the runs and the shared directories. The execution options of the
    editor are given by name: scheduler, builtin_sched_cpus,
    builtin_sched_mem, dflt_nodes, dflt_throttle, rerun_outdated_procs,
    conda_support, docker_support. A resident program (`resident=True`)
    adds nodes and a Supervisor instead of processes, and may ask for
    periodic snapshots of its runs (`snapshot_every_secs`).
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        program_options: dict[str, str] | None = None,
        preamble: str = "",
        env_vars: dict[str, str] | None = None,
        shared_dirs: list[str] | None = None,
        scheduler: str = "BUILTIN",
        builtin_sched_cpus: str = "",
        builtin_sched_mem: str = "",
        dflt_nodes: str = "",
        dflt_throttle: str = "",
        rerun_outdated_procs: bool = False,
        conda_support: bool = False,
        docker_support: bool = False,
        resident: bool = False,
        snapshot_every_secs: str = "",
    ):
        check_program_name(name)
        self.name = name
        self.resident = resident
        self.description = description
        self.program_options = dict(program_options or {})
        self.preamble = preamble
        self.env_vars = dict(env_vars or {})
        self.shared_dirs = list(shared_dirs or [])
        self.execution_options = {
            "scheduler": scheduler,
            "builtinSchedCpus": builtin_sched_cpus,
            "builtinSchedMem": builtin_sched_mem,
            "dfltNodes": dflt_nodes,
            "dfltThrottle": dflt_throttle,
            "rerunOutdatedProcs": rerun_outdated_procs,
            "condaSupport": conda_support,
            "dockerSupport": docker_support,
            "snapshotEverySecs": snapshot_every_secs,
        }
        self._members: list[_Member] = []

    def __repr__(self) -> str:
        return f'Program("{self.name}")'

    @property
    def processes(self) -> list[Process]:
        return [member.process for member in self._members]

    def add(
        self,
        process: Process,
        cpus: float | None = None,
        mem: float | None = None,
        time: str | None = None,
        processdeps: str | None = None,
        force: bool = False,
        position: tuple[float, float] | None = None,
        **node_specs,
    ) -> Process:
        """
        Adds `process` to the program with the computational specifications
        of its use there (`cpus`, `mem` in megabytes, `time` as
        `hh:mm:ss`), its explicit dependencies (`processdeps`, as the
        engine writes them, `afterok:count`), whether it is rerun on every
        run (`force`), and where it goes on the canvas (`position`, else
        the layout of the editor). A node of a resident program takes the
        specifications of a node too, under the names of the engine
        (`input_log_max_mb`, `heartbeat_timeout_s`, ...). Returns the
        process.
        """
        is_node = isinstance(process, (Node, Supervisor))
        if self.resident and not is_node:
            raise DefinitionError(
                f'Process "{process.name}" is not a node: a resident program adds nodes (Node) and a '
                "Supervisor only."
            )
        if is_node and not self.resident:
            raise DefinitionError(
                f'"{process.name}" is a node, which only a resident program adds (Program(..., resident=True)).'
            )
        unknown = sorted(set(node_specs) - set(NODE_SPECS))
        if unknown:
            raise DefinitionError(
                f'Process "{process.name}": unknown specification(s) {", ".join(unknown)} (the '
                "specifications of a node are " + ", ".join(NODE_SPECS) + ")."
            )
        if node_specs and not is_node:
            raise DefinitionError(
                f'Process "{process.name}" is given specifications of a node '
                f'({", ".join(sorted(node_specs))}), which only a node of a resident program reads.'
            )
        for member in self._members:
            if member.process is process:
                raise DefinitionError(f'Process "{process.name}" is added twice to program "{self.name}".')
            if member.process.name == process.name:
                raise DefinitionError(
                    f'Program "{self.name}" already has a process named "{process.name}".'
                )
        self._members.append(_Member(process, cpus, mem, time, processdeps, force, position, node_specs or None))
        return process

    # --- the model -----------------------------------------------------------

    def _member_by_name(self, name: str) -> _Member | None:
        return next((member for member in self._members if member.process.name == name), None)

    def _resolve_source(self, target: Option, source: Source) -> Option:
        """The output that `source` names, which has to be an output of a
        process of the program."""
        if isinstance(source, Option):
            member = next((m for m in self._members if m.process is source.process), None)
            if member is None:
                raise DefinitionError(
                    f'Option "{target.label}" of process "{target.process.name}" reads '
                    f'"{source.label}" of process "{source.process.name}", which program '
                    f'"{self.name}" does not add.'
                )
            output = source
        else:
            process_name, label = source
            member = self._member_by_name(process_name)
            if member is None:
                raise DefinitionError(
                    f'Option "{target.label}" of process "{target.process.name}" reads '
                    f'"{label}" of process "{process_name}", which program "{self.name}" '
                    "does not add."
                )
            try:
                output = member.process[label]
            except KeyError:
                raise DefinitionError(
                    f'Option "{target.label}" of process "{target.process.name}" reads '
                    f'"{label}" of process "{process_name}", which has no such option.'
                ) from None
        if output.direction != "output":
            raise DefinitionError(
                f'Option "{target.label}" of process "{target.process.name}" reads '
                f'"{output.label}" of process "{output.process.name}", which is an input.'
            )
        return output

    def _edges(self) -> list[_Edge]:
        edges = []
        for member in self._members:
            for option in member.process.options:
                for source in option.sources:
                    edges.append(_Edge(self._resolve_source(option, source), option, option.display))
        return edges

    def _positions(self) -> dict[str, tuple[float, float]]:
        names = [member.process.name for member in self._members]
        connections = [(edge.source.process.name, edge.target.process.name) for edge in self._edges()]
        positions = layout(names, connections)
        for member in self._members:
            if member.position is not None:
                positions[member.process.name] = (float(member.position[0]), float(member.position[1]))
        return positions

    def _option_model(self, member: _Member, option: Option):
        from api.models import ProgramOption

        process = member.process
        count_source_id = None
        if option.count_source is not None:
            count_source = option.count_source
            if isinstance(count_source, str):
                try:
                    count_source = process[count_source]
                except KeyError:
                    raise DefinitionError(
                        f'Option "{option.label}" of process "{process.name}" is counted by '
                        f'"{option.count_source}", which the process does not declare.'
                    ) from None
            if count_source.process is not process:
                raise DefinitionError(
                    f'Option "{option.label}" of process "{process.name}" is counted by '
                    f'"{count_source.label}" of process "{count_source.process.name}": the count '
                    "source of a family is an option of the same process."
                )
            count_source_id = _id(self.name, process.name, count_source.label)
        return ProgramOption(
            id=_id(self.name, process.name, option.label),
            label=option.label,
            direction=option.direction,
            dataType=option.data_type,
            channel=option.channel,
            subpath=option.subpath,
            mirror=option.mirror,
            fifoTag=option.fifo_tag,
            description=option.description,
            value=option.value,
            commandLine=option.command_line,
            mandatory=option.mandatory,
            fromProcessSpec=option.from_process_spec,
            countSourceOptionId=count_source_id,
            taskShaping=option.task_shaping,
        )

    @staticmethod
    def _read(process: Process, path: Path | None, what: str) -> str | None:
        """The text of a file of `process` as the program model keeps it,
        without the newlines that end it, as import keeps the code it
        reads from a module; `what` says which file for the error. None
        for no file."""
        if path is None:
            return None
        try:
            return path.read_text().rstrip("\n")
        except OSError as error:
            raise DefinitionError(f'Process "{process.name}": cannot read its {what} {path}: {error.strerror}.')

    def _read_code(self, process: Process) -> str:
        if process.script_path is not None:
            return self._read(process, process.script_path, "script") or ""
        return self._read(process, process.code_path, "code file") or ""

    def _options_handler(self, process: Process):
        from api.models import OptionsHandler

        tasks = self._read(process, process.tasks_path, "tasks file")
        if process.mode == "array":
            return OptionsHandler(mode="array", arrayCode=tasks)
        if process.mode == "generator":
            return OptionsHandler(mode="generator", generatorSizeCode=tasks)
        return OptionsHandler(mode=process.mode)

    def _additional_methods(self, process: Process):
        from api.models import AdditionalMethods

        return AdditionalMethods(
            **{field: self._read(process, path, "method file") for field, path in process.method_paths.items()}
        )

    @staticmethod
    def _script_relative(process: Process) -> str | None:
        """
        How the module refers to the script of `process`: the path as it
        was given when it is relative and stays below the directory of the
        description (it is copied under that same path beside the module),
        the name of the script alone when the path climbs out of it, and
        an absolute path as it is (which the engine takes with a warning
        about portability, and which is not copied).
        """
        given = process.script_given
        if given is None:
            return None
        if Path(given).is_absolute():
            return given
        if ".." in Path(given).parts:
            return Path(given).name
        return given

    def _node_parts(self, process: Process):
        """The node kind and the parts of the code of a node, from its file;
        None for a Supervisor and for a process of a general program."""
        from api.resident_node_code import decompose_heredoc

        if isinstance(process, Supervisor):
            return "Supervisor", None
        if not isinstance(process, Node):
            return None, None
        source = self._read(process, process.code_path, "node file")
        decomposed = decompose_heredoc(source)
        if decomposed.misfits:
            problems = "\n".join(
                f"  line {misfit.line}: {misfit.problem}; {misfit.fix}" if misfit.line is not None
                else f"  {misfit.problem}; {misfit.fix}"
                for misfit in decomposed.misfits
            )
            raise DefinitionError(
                f'Node "{process.name}": its file {process.code_path} does not fit the parts of a node '
                f"of the web UI:\n{problems}"
            )
        if decomposed.kind == "Supervisor":
            raise DefinitionError(
                f'Node "{process.name}": its file defines a Supervisor; a Supervisor is added with '
                "Supervisor(name), without a file."
            )
        return decomposed.kind, decomposed.code

    def _process_model(self, member: _Member, positions):
        from api.models import AdditionalSpecs, AliasOptMapping, ComputationalSpecs, Position, ProgramProcess

        process = member.process
        x, y = positions[process.name]
        kind, node_code = self._node_parts(process)
        return ProgramProcess(
            id=_id(self.name, process.name),
            name=process.name,
            description=process.description,
            position=Position(x=x, y=y),
            options=[self._option_model(member, option) for option in process.options],
            optionsHandler=self._options_handler(process),
            language=process.language,
            # The code of a node is its parts; script generation writes the
            # heredoc from them
            code="" if kind else self._read_code(process),
            computationalSpecs=ComputationalSpecs(
                cpus=member.cpus, mem=member.mem, time=member.time, **(member.node_specs or {})
            ),
            additionalSpecs=AdditionalSpecs(
                force=member.force,
                processdeps=member.processdeps,
                alias=process.alias,
                aliasOptMap=[AliasOptMapping(fromLabel=a, toLabel=b) for a, b in process.alias_opt_map.items()],
                externalAlias=self._script_relative(process),
            ),
            additionalMethods=self._additional_methods(process),
            nodeKind=kind,
            initiator=getattr(process, "initiator", False),
            nodeCode=node_code,
        )

    def to_model(self):
        """
        The program as the program model of the web UI (`api.models.Program`),
        as `write()` saves it. Raises DefinitionError for what the SDK
        refuses; what script generation refuses is found when the program
        is written.
        """
        from api.models import ExecutionOptions, Program as ProgramModel, ProgramEdge

        positions = self._positions()
        processes = [self._process_model(member, positions) for member in self._members]
        edges = [
            ProgramEdge(
                id=_id(self.name, "edge", edge.source.process.name, edge.source.label, edge.target.process.name, edge.target.label),
                sourceProcessId=_id(self.name, edge.source.process.name),
                sourceOptionId=_id(self.name, edge.source.process.name, edge.source.label),
                targetProcessId=_id(self.name, edge.target.process.name),
                targetOptionId=_id(self.name, edge.target.process.name, edge.target.label),
                display=edge.display,
            )
            for edge in self._edges()
        ]
        return ProgramModel(
            id=_id(self.name),
            name=self.name,
            programType="resident" if self.resident else "general",
            description=self.description,
            preamble=self.preamble,
            envVars=self.env_vars,
            outputDir="",
            executionOptions=ExecutionOptions(**self.execution_options),
            programOptions=self.program_options,
            sharedDirs=self.shared_dirs,
            processes=processes,
            edges=edges,
        )

    def _script_copies(self) -> list[_ScriptCopy]:
        """The scripts to copy beside the module: those the module refers
        to by a relative path."""
        copies = []
        for member in self._members:
            relative = self._script_relative(member.process)
            if relative is not None and not Path(relative).is_absolute():
                copies.append(_ScriptCopy(member.process.script_path, Path(relative)))
        return copies

    def write(self, home_dir: str | Path) -> Path:
        """
        Writes the program into `home_dir`, as Save does in the editor: the
        program metadata in `.debasher/program.json`, the generated module
        `<name>.sh`, and a copy of every script (external alias), replacing
        an older copy. Returns the path of the module. A program that
        the SDK or script generation refuses leaves the directory as it
        was.
        """
        from api import persistence

        home = Path(home_dir)
        model = self.to_model()
        copies = self._script_copies()
        for copy in copies:
            if not copy.source.is_file():
                raise DefinitionError(f"Script {copy.source} does not exist.")
        try:
            saved = persistence.save(str(home), model)
        except (ValueError, NotImplementedError) as error:
            raise DefinitionError(str(error)) from error
        for copy in copies:
            destination = home / copy.relative
            if destination.resolve() == copy.source.resolve():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copy.source, destination)
        return saved.script_path
