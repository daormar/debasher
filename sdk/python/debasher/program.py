"""
A program as the SDK describes it: the processes it adds, each with the
specifications of its use there, as the `_program` method of a module
adds them with `add_debasher_process`, and what the program is run with.
`to_model()` writes the topology file that the editor would save for the
program, with the texts of the files it names, and loads it as the web UI
loads an artifact (`api.topology.join`); `write()` saves the program model
as the editor does (`api/persistence.py`): the artifact, the topology
file `program.yaml` and the files of the processes where the description
has them, and the generated module beside it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from api import topology
from api.script_generation import RESIDENT_COMP_SPEC_NAMES as NODE_SPECS

from .errors import DefinitionError
from .process import Node, Option, Process, Source, Supervisor, check_program_name


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
    initiator: bool = False
    node_specs: dict[str, float | int | str] | None = None


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
    such as `load_debasher_module` lines), the environment that the
    backend gives the tools of the engine (`env_vars`, of which only
    `DEBASHER_MOD_DIR` is read) and the shared directories. The execution
    options of the editor are given by name: scheduler,
    builtin_sched_cpus, builtin_sched_mem, dflt_nodes, dflt_throttle,
    rerun_outdated_procs, conda_support, docker_support. A resident
    program (`resident=True`) adds nodes and a Supervisor instead of
    processes, and may ask for periodic snapshots of its runs
    (`snapshot_every_secs`).
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
        self.execution = topology.TopologyExecution(
            scheduler=scheduler,
            builtin_sched_cpus=builtin_sched_cpus,
            builtin_sched_mem=builtin_sched_mem,
            dflt_nodes=dflt_nodes,
            dflt_throttle=dflt_throttle,
            rerun_outdated_procs=rerun_outdated_procs,
            conda_support=conda_support,
            docker_support=docker_support,
            snapshot_every_secs=snapshot_every_secs,
        )
        self._members: list[_Member] = []

    def __repr__(self) -> str:
        return f'Program("{self.name}")'

    @property
    def processes(self) -> list[Process]:
        """The processes added to the program, in the order they were
        added."""
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
        initiator: bool = False,
        **node_specs,
    ) -> Process:
        """
        Adds `process` to the program with the computational specifications
        of its use there (`cpus`, `mem` in megabytes, `time` as
        `hh:mm:ss`; 1 CPU, 256 megabytes and 01:00:00 for those not
        given, as the editor gives a new process), its explicit
        dependencies (`processdeps`, as the engine writes them,
        `afterok:count`), whether it is rerun on every
        run (`force`), and where it goes on the canvas (`position`, else
        the layout of the editor). A node of a resident program takes the
        specifications of a node too, under the names of the engine
        (`input_log_max_mb`, `heartbeat_timeout_s`, ...), and whether it is
        an initiator, where a round starts (`initiator`), which depends on
        how the program connects it. Returns the process.
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
        if initiator and not isinstance(process, Node):
            raise DefinitionError(
                f'Process "{process.name}" is not a Node: only a node of a resident program is an initiator.'
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
        self._members.append(
            _Member(process, cpus, mem, time, processdeps, force, position, initiator, node_specs or None)
        )
        return process

    # --- the topology file ---------------------------------------------------

    def _member_by_name(self, name: str) -> _Member | None:
        return next((member for member in self._members if member.process.name == name), None)

    def _source_name(self, target: Option, source: Source) -> str:
        """The source `source` of the input `target` as the topology file
        names it, "<process>.<label>", which has to be an output of a
        process of the program."""
        if isinstance(source, Option):
            if not any(member.process is source.process for member in self._members):
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
            output = member.process._find(label)
            if output is None:
                raise DefinitionError(
                    f'Option "{target.label}" of process "{target.process.name}" reads '
                    f'"{label}" of process "{process_name}", which has no such option.'
                )
        if output.direction != "output":
            raise DefinitionError(
                f'Option "{target.label}" of process "{target.process.name}" reads '
                f'"{output.label}" of process "{output.process.name}", which is an input.'
            )
        return f"{output.process.name}.{output.label}"

    def _option(self, process: Process, option: Option) -> topology.TopologyOption:
        """A received option as the topology file keeps it, with the keys of
        its place in the interface or of its kind of value."""
        interface, task_options = process._interface, process._task_options
        keys: dict = {"type": "flag" if option.data_type == "None" else option.data_type,
                      "description": option.description}
        if option.label in interface.cmdline:
            keys |= {"cmdline": True, "mandatory": interface.cmdline[option.label]}
        elif option.label in interface.external:
            keys |= {"value": interface.external[option.label], "channel": "fifo", "fifo_tag": "external"}
        else:
            value = task_options.values[option.label]
            if isinstance(value, str):
                keys["value"] = value
            elif value is not True:
                keys |= {
                    "value": value.value,
                    "channel": value.channel,
                    "subpath": value.subpath,
                    "mirror": value.mirror,
                    "from_spec": value.from_spec,
                }
                if value.sources:
                    sources = [self._source_name(option, source) for source in value.sources]
                    keys["from"] = sources[0] if len(sources) == 1 else sources
                    if value.display == "label":
                        keys["display"] = "label"
        if option.label in task_options.count:
            keys["count_source"] = task_options.count[option.label]
        return topology.TopologyOption(**keys)

    @staticmethod
    def _shaping_option(data_type: str, description: str) -> topology.TopologyOption:
        return topology.TopologyOption(type=data_type, description=description, cmdline=True, shaping=True)

    @staticmethod
    def _read(process: Process, path: Path, what: str) -> str:
        """The text of a file of `process`; `what` says which file for the
        error."""
        try:
            return path.read_text()
        except OSError as error:
            raise DefinitionError(f'Process "{process.name}": cannot read its {what} {path}: {error.strerror}.')

    @staticmethod
    def _file_relative(process: Process, path: Path) -> str:
        """
        Where the artifact keeps a file of `process` that the SDK read
        (its process file, its tasks file, a method file): the path
        relative to the base directory of the process (the directory of
        the file that creates it, or its base_dir) when the file is below
        it, which the program written into that directory leaves as it is,
        and the name of the file alone when it is outside it, so that the
        program written is self-contained.
        """
        try:
            relative = path.resolve().relative_to(process.base_dir.resolve())
        except ValueError:
            return path.name
        return str(relative)

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

    def _node_kind(self, process: Process, text: str) -> str | None:
        """The node kind of a node, read from its file, which has to fit the
        parts of a node of the web UI; None for a process of a general
        program."""
        from api.resident_node_code import decompose_heredoc

        if isinstance(process, Supervisor):
            return "Supervisor"
        if not isinstance(process, Node):
            return None
        decomposed = decompose_heredoc(text.rstrip("\n"))
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
        return decomposed.kind

    def _process(self, member: _Member, files: dict[str, str]) -> topology.TopologyProcess:
        """The process of `member` as the topology file keeps it, adding the
        texts of the files it names to `files`."""
        process = member.process
        process.check_parts()
        keys: dict = {"description": process.description}
        kind = None
        if process.alias:
            keys |= {"alias": process.alias, "alias_opt_map": dict(process.alias_opt_map)}
        elif process.script_path is not None:
            path = self._script_relative(process)
            files[path] = self._read(process, process.script_path, "script")
            keys |= {"script": path, "alias_opt_map": dict(process.alias_opt_map)}
        elif process.code_path is not None:
            path = self._file_relative(process, process.code_path)
            files[path] = self._read(process, process.code_path, "node file" if isinstance(process, Node) else "code file")
            keys["code"] = path
            kind = self._node_kind(process, files[path])
        else:
            kind = self._node_kind(process, "")
        if process.tasks_path is not None:
            path = self._file_relative(process, process.tasks_path)
            files[path] = self._read(process, process.tasks_path, "tasks file")
            keys |= {"mode": process.mode, "tasks": path}
        methods = {}
        for method, method_path in process.method_paths.items():
            path = self._file_relative(process, method_path)
            files[path] = self._read(process, method_path, "method file")
            methods[method] = path
        options = {option.label: self._option(process, option) for option in process.options}
        options |= {
            label: self._shaping_option(data_type, description)
            for label, (data_type, description) in process._interface.shaping.items()
        }
        specs = {name: value for name, value in (("cpus", member.cpus), ("mem", member.mem), ("time", member.time)) if value is not None}
        return topology.TopologyProcess(
            **keys,
            methods=methods,
            conda_envs=dict(process.conda_envs),
            docker_imgs=list(process.docker_imgs),
            specs=topology.TopologySpecs(
                **specs, processdeps=member.processdeps, force=member.force, **(member.node_specs or {})
            ),
            kind=kind,
            initiator=member.initiator,
            position=topology.TopologyPosition(x=member.position[0], y=member.position[1]) if member.position else None,
            options=options,
        )

    def to_topology(self) -> tuple[topology.Topology, dict[str, str]]:
        """
        The topology file that the editor would save for the program, and
        the texts of the files it names, by their paths in the artifact.
        Raises DefinitionError for what the SDK refuses.
        """
        files: dict[str, str] = {}
        processes = {member.process.name: self._process(member, files) for member in self._members}
        return (
            topology.Topology(
                schema_version=topology.SCHEMA_VERSION,
                name=self.name,
                type="resident" if self.resident else None,
                description=self.description,
                preamble=self.preamble,
                env=self.env_vars,
                shared_dirs=self.shared_dirs,
                execution=self.execution,
                program_options=self.program_options,
                processes=processes,
            ),
            files,
        )

    def to_model(self):
        """
        The program as the program model of the web UI (`api.models.Program`),
        as `write()` saves it: the topology file of the program loaded as the
        web UI loads an artifact. Raises DefinitionError for what the SDK or
        loading refuses; what script generation refuses is found when the
        program is written.
        """
        top, files = self.to_topology()
        try:
            return topology.join(top, files)
        except topology.TopologyError as error:
            raise DefinitionError(str(error)) from error

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
        Writes the program into `home_dir`, as Save does in the editor: its
        artifact, the topology file `program.yaml` and the process files,
        the tasks files and the method files where the description had
        them, relative to its directory (each written only when its content
        differs, so a program written into the directory of the description
        leaves its files as they are), the generated module `<name>.sh`,
        and a copy of every script (external alias), replacing an older
        copy. Returns the path of the module. A program that the SDK or
        script generation refuses leaves the directory as it was.
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
