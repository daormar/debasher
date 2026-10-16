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
from .process import Option, Process, Source, check_program_name

# Every id of the program model is derived from the names, so that writing
# the same program twice gives the same metadata.
_ID_NAMESPACE = uuid.UUID("6f1c2b7e-3a9d-4d0e-9c1f-2b5a8e4d7c10")


def _id(*names: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, "/".join(names)))


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
    conda_support, docker_support.
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
    ):
        check_program_name(name)
        self.name = name
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
    ) -> Process:
        """
        Adds `process` to the program with the computational specifications
        of its use there (`cpus`, `mem` in megabytes, `time` as
        `hh:mm:ss`), its explicit dependencies (`processdeps`, as the
        engine writes them, `afterok:count`), whether it is rerun on every
        run (`force`), and where it goes on the canvas (`position`, else
        the layout of the editor). Returns the process.
        """
        for member in self._members:
            if member.process is process:
                raise DefinitionError(f'Process "{process.name}" is added twice to program "{self.name}".')
            if member.process.name == process.name:
                raise DefinitionError(
                    f'Program "{self.name}" already has a process named "{process.name}".'
                )
        self._members.append(_Member(process, cpus, mem, time, processdeps, force, position))
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
        """The text of a file of `process`, `what` saying which for the
        error; None for no file."""
        if path is None:
            return None
        try:
            return path.read_text()
        except OSError as error:
            raise DefinitionError(f'Process "{process.name}": cannot read its {what} {path}: {error.strerror}.')

    def _read_code(self, process: Process) -> str:
        if process.script_path is not None:
            # The copy of a script is for the editor to show, kept as import
            # keeps that of an external alias, without its final newline
            return (self._read(process, process.script_path, "script") or "").rstrip("\n")
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

    def _process_model(self, member: _Member, positions):
        from api.models import AdditionalSpecs, AliasOptMapping, ComputationalSpecs, Position, ProgramProcess

        process = member.process
        x, y = positions[process.name]
        return ProgramProcess(
            id=_id(self.name, process.name),
            name=process.name,
            description=process.description,
            position=Position(x=x, y=y),
            options=[self._option_model(member, option) for option in process.options],
            optionsHandler=self._options_handler(process),
            language=process.language,
            code=self._read_code(process),
            computationalSpecs=ComputationalSpecs(cpus=member.cpus, mem=member.mem, time=member.time),
            additionalSpecs=AdditionalSpecs(
                force=member.force,
                processdeps=member.processdeps,
                alias=process.alias,
                aliasOptMap=[AliasOptMapping(fromLabel=a, toLabel=b) for a, b in process.alias_opt_map.items()],
                externalAlias=self._script_relative(process),
            ),
            additionalMethods=self._additional_methods(process),
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
