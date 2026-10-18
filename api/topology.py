"""
The topology file of a program (see "The artifact: the topology file and
the process files" in doc/design_doc_webui.md): `program.yaml`, the part
of the artifact that holds what the program is and how it runs, beside one
file per process with its code.

This module has three parts:

- The model of the file (`Topology` and the models under it), Pydantic as
  the program model is, which refuses an unknown key, and its JSON Schema
  (`json_schema`). It is not the program model of `models.py`: it has no
  ids, names processes by name and options by label, and keeps the
  connections on the inputs that read them.
- Reading and writing the file (`loads`, `dumps`): YAML, with every scalar
  read as a string, since the values of the file are Bash words and names,
  and with a duplicate name or label refused.
- The conversion between the program model and the artifact in both
  directions: `split` takes the program model apart into the topology and
  the text of every file it names, and `join` builds the program model
  from a topology and the text of its files, with ids derived from the
  names, so that two loads of the same program give the same ids.

Nothing here touches the disk: persistence.py reads and writes the files.
"""

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .layout import layout
from .models import (
    AdditionalMethods,
    AdditionalSpecs,
    AliasOptMapping,
    ComputationalSpecs,
    CondaEnv,
    ExecutionOptions,
    FuncLanguage,
    GroupSource,
    NodeKind,
    OptionsHandler,
    Position,
    ProcessFiles,
    Program,
    ProgramEdge,
    ProgramOption,
    ProgramProcess,
    SeqAdditionalSpecs,
    SeqComputationalSpecs,
    SeqProcess,
)
from .resident_node_code import decompose_heredoc, node_heredoc

# The version of the schema that this module writes and the newest it reads.
# Raised when the meaning of a key changes or a key goes; a key added with a
# default does not raise it.
SCHEMA_VERSION = 1

TOPOLOGY_FILENAME = "program.yaml"

# Where the JSON Schema of the file is published, named on the first line
# of every topology file written here, for the editors that validate
# against a schema.
SCHEMA_URL = f"https://debasher.readthedocs.io/en/latest/_static/schema/program-{SCHEMA_VERSION}.json"

# The language of a process file, by its extension: the extensions that
# the engine reads for an external alias.
LANGUAGE_BY_EXTENSION = {
    "sh": "bash",
    "py": "python",
    "pl": "perl",
    "r": "r",
    "R": "r",
    "groovy": "groovy",
}

# The extension of the process file that saving chooses for a process of
# each language.
EXTENSION_BY_LANGUAGE = {
    "bash": "sh",
    "python": "py",
    "perl": "pl",
    "r": "R",
    "groovy": "groovy",
}

# The additional methods, by the name the file gives them, and the field of
# AdditionalMethods that holds the body of each.
METHOD_FIELDS = {
    "reset_outfiles": "resetOutfilesCode",
    "post": "postCode",
    "outdir_basename": "outdirBasenameCode",
    "skip": "skipCode",
    "conda_envs": "condaEnvsCode",
    "docker_imgs": "dockerImgsCode",
}

MethodName = Literal["reset_outfiles", "post", "outdir_basename", "skip", "conda_envs", "docker_imgs"]

# The extension of a tasks file and of a skip file in each of the languages
# that they may be written in: a Python function file of the engine, or a
# Bash body. Any other method file is a Bash body.
FUNC_EXTENSION_BY_LANGUAGE = {"bash": "sh", "python": "py"}

Language = Literal["bash", "python", "perl", "r", "groovy"]

# The data type of an option as the file spells it: `flag` for an option
# that takes no value, which the program model calls "None".
DataType = Literal["int", "float", "string", "file", "dir", "flag"]

# The namespace of the ids derived from names, shared with the SDK.
_ID_NAMESPACE = uuid.UUID("6f1c2b7e-3a9d-4d0e-9c1f-2b5a8e4d7c10")


def element_id(*names: str) -> str:
    """
    The id of an element of the program model derived from the names that
    identify it: the program name for the program, then the process name
    for a process, then the label for an option; "edge" and the two ends
    for an edge. The same names give the same id, so nothing reads an id
    as a name and two loads of the same program agree.
    """
    return str(uuid.uuid5(_ID_NAMESPACE, "/".join(names)))


class TopologyError(ValueError):
    """A topology file, or the files it names, that cannot be read: not
    YAML, a duplicate name or label, a schema version newer than this
    module reads, a key the schema does not have, a connection or a count
    source that names nothing, or the code of a node that does not fit the
    parts of a node. The message says where."""


# --- the model of the file ---------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TopologyOption(_Strict):
    type: DataType
    description: str = ""
    value: str = ""
    channel: Literal["none", "value_desc", "fifo", "shared_dir", "process_outdir"] = "none"
    subpath: str = ""
    mirror: bool = False
    fifo_tag: Optional[Literal["external"]] = None
    cmdline: bool = False
    # Absent, a command line option that is not a flag is mandatory and any
    # other option is not.
    mandatory: Optional[bool] = None
    shaping: bool = False
    from_spec: bool = False
    # The label of the count source option of a fanout family.
    count_source: Optional[str] = None
    # What a connected input reads, "<process>.<label>", or a list for a
    # fan-in.
    from_: Optional[str | list[str]] = Field(default=None, alias="from")
    # How the canvas draws the connections of the input: as label edges
    # when "label".
    display: Optional[Literal["line", "label"]] = None


class TopologySpecs(_Strict):
    # The computational and additional specifications of a process, by the
    # names of the engine.
    cpus: Optional[float] = None
    mem: Optional[float] = None
    time: Optional[str] = None
    processdeps: Optional[str] = None
    force: bool = False
    # The limits of a node of a resident program.
    input_log_max_mb: Optional[float] = None
    out_backlog_max_mb: Optional[float] = None
    out_backlog_fail_mb: Optional[float] = None
    gil_switch_interval_ms: Optional[float] = None
    startup_timeout_s: Optional[float] = None
    max_concurrent_runs: Optional[int] = None
    batch_sched: Optional[str] = None
    heartbeat_timeout_s: Optional[float] = None


class TopologySeqSpecs(_Strict):
    cpus: Optional[float] = None
    mem: Optional[float] = None
    time: Optional[str] = None
    sched: Optional[Literal["BUILTIN", "SLURM"]] = None


class TopologyGroup(_Strict):
    # A process that "Add program" brought in (see GroupSource).
    program: str
    id: str
    size: int
    dir: str


class TopologyPosition(_Strict):
    x: float
    y: float


class TopologyProcess(_Strict):
    description: str = ""
    # The path of the process file, which the editor writes from the code
    # of the process; or the path of a script that the module runs as it
    # is, the external alias of the engine, which the editor shows and does
    # not write; or the name of a process whose code this one runs under
    # its own name. A process with none takes its code from a module that
    # the preamble loads.
    code: Optional[str] = None
    script: Optional[str] = None
    alias: Optional[str] = None
    alias_opt_map: dict[str, str] = {}
    # Given when the extension of the file does not say it.
    language: Optional[Language] = None
    # The options handler: absent for the standard mode.
    mode: Optional[Literal["array", "generator", "manual"]] = None
    tasks: Optional[str] = None
    methods: dict[MethodName, str] = {}
    # The Conda environments of the process, name to YAML file, and its
    # Docker images, as data; a process that gives them names no
    # conda_envs or docker_imgs method file.
    conda_envs: dict[str, str] = {}
    docker_imgs: list[str] = []
    specs: TopologySpecs = TopologySpecs()
    group: Optional[TopologyGroup] = None
    # Only in a resident program.
    kind: Optional[NodeKind] = None
    initiator: bool = False
    position: Optional[TopologyPosition] = None
    options: dict[str, TopologyOption] = {}


class TopologySeqProcess(_Strict):
    description: str = ""
    code: Optional[str] = None
    script: Optional[str] = None
    alias: Optional[str] = None
    alias_opt_map: dict[str, str] = {}
    language: Optional[Language] = None
    specs: TopologySeqSpecs = TopologySeqSpecs()
    group: Optional[TopologyGroup] = None


class TopologyExecution(_Strict):
    scheduler: str = "BUILTIN"
    builtin_sched_cpus: str = ""
    builtin_sched_mem: str = ""
    dflt_nodes: str = ""
    dflt_throttle: str = ""
    rerun_outdated_procs: bool = False
    conda_support: bool = False
    docker_support: bool = False
    snapshot_every_secs: str = ""


class Topology(_Strict):
    schema_version: int
    name: str
    type: Optional[Literal["resident"]] = None
    description: str = ""
    preamble: str = ""
    env: dict[str, str] = {}
    shared_dirs: list[str] = []
    execution: TopologyExecution = TopologyExecution()
    program_options: dict[str, str] = {}
    processes: dict[str, TopologyProcess] = {}
    seq_processes: dict[str, TopologySeqProcess] = {}


def json_schema() -> dict:
    """The JSON Schema of the topology file, from its model."""
    schema = Topology.model_json_schema(by_alias=True)
    schema["title"] = "DeBasher program"
    schema["description"] = f"The topology file of a DeBasher program, schema version {SCHEMA_VERSION}."
    return schema


# --- reading and writing the file --------------------------------------------


class _StringLoader(yaml.SafeLoader):
    """A loader that reads every plain scalar as a string, since the file
    holds Bash words and names that YAML would otherwise read as numbers
    or booleans (a value `200`, a description `yes`), and that refuses a
    duplicate key, which the standard loader resolves to the last one in
    silence. The typed fields of the model (a count, a flag) are converted
    by the model from the string."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise TopologyError(f'{key_node.start_mark.line + 1}: the key "{key}" is given twice')
            seen.add(key)
        return super().construct_mapping(node, deep)


# No implicit resolver: every plain scalar is a string.
_StringLoader.yaml_implicit_resolvers = {}


class _Flow(dict):
    """A mapping written in flow style ({a: 1, b: 2}), for the short ones."""


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _represent_text(dumper: yaml.SafeDumper, text: str):
    """A text with several lines as a literal block, a long one folded,
    the rest as the dumper writes a string: quoted when YAML would read it
    as something else."""
    style = "|" if "\n" in text else ">" if len(text) > 60 else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", text, style=style)


def _represent_number(dumper: yaml.SafeDumper, number: float):
    """A whole number without its decimal part (`cpus: 1`)."""
    if number == int(number):
        return dumper.represent_scalar("tag:yaml.org,2002:int", str(int(number)))
    return dumper.represent_float(number)


def _represent_flow(dumper: yaml.SafeDumper, data: _Flow):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True)


_Dumper.add_representer(str, _represent_text)
_Dumper.add_representer(float, _represent_number)
_Dumper.add_representer(_Flow, _represent_flow)


def _validation_message(error: ValidationError) -> str:
    problems = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "the file"
        problems.append(f"{where}: {item['msg']}")
    return "; ".join(problems)


def loads(text: str) -> Topology:
    """
    The topology of a topology file, read from its text. Raises
    TopologyError for what cannot be read (see the class).
    """
    try:
        data = yaml.load(text, Loader=_StringLoader)
    except yaml.YAMLError as error:
        raise TopologyError(f"not a topology file: {error}") from error
    if not isinstance(data, dict):
        raise TopologyError("not a topology file: it does not hold a mapping")
    version = data.get("schema_version")
    try:
        version = int(version)
    except (TypeError, ValueError):
        raise TopologyError("the file names no schema_version, an integer, which a topology file starts with")
    if version > SCHEMA_VERSION:
        raise TopologyError(
            f"the file is written for schema version {version}, and this version of DeBasher reads "
            f"up to {SCHEMA_VERSION}: a newer DeBasher is needed to open it"
        )
    if version < 1:
        raise TopologyError(f"schema version {version} is not a version of the topology file")
    try:
        return Topology.model_validate(data)
    except ValidationError as error:
        raise TopologyError(f"the topology file does not fit its schema: {_validation_message(error)}") from error


def _writable(data):
    """The data of a topology as the dumper writes it: `position` and
    `specs` in flow style, the rest in block style."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            value = _writable(value)
            if key in ("position", "specs") and isinstance(value, dict):
                value = _Flow(value)
            out[key] = value
        return out
    if isinstance(data, list):
        return [_writable(item) for item in data]
    return data


def dumps(topology: Topology) -> str:
    """
    The text of a topology file: its schema named on the first line, then
    the topology with every key that holds its default left out, the
    processes and their options in their order.
    """
    data = topology.model_dump(by_alias=True, exclude_defaults=True, exclude_none=True)
    data = {"schema_version": topology.schema_version, "name": topology.name} | data
    body = yaml.dump(
        _writable(data), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=78, default_flow_style=False
    )
    return f"# yaml-language-server: $schema={SCHEMA_URL}\n{body}"


# --- from the program model to the artifact ----------------------------------


@dataclass
class SplitProgram:
    """A program model taken apart: its topology, and the text of every file
    the topology names that the editor writes (the process files of the
    processes with code, the tasks files and the method files), by the path
    the topology gives it. A script (an external alias) is named and not
    written, since it is the user's file."""

    topology: Topology
    files: dict[str, str] = field(default_factory=dict)


def _file_text(code: str) -> str:
    """The text of a file that holds `code`: the code ends with no newline
    in the program model, and the file ends with one."""
    return code + "\n" if code else ""


def _default_code_path(program_name: str, process_name: str, language: str) -> str:
    """The name of the process file that saving chooses: the process name
    with the extension of its language, or, for a Bash process named as its
    program, whose file would be the generated script, with `_process`."""
    path = f"{process_name}.{EXTENSION_BY_LANGUAGE[language]}"
    if path == f"{program_name}.sh":
        path = f"{process_name}_process.sh"
    return path


def code_file_path(program_name: str, process) -> str:
    """The path of the process file of a process, or of a sequential
    process, in the artifact: the one it was loaded with, or the default
    name that saving chooses for it (see _default_code_path)."""
    return process.files.code or _default_code_path(program_name, process.name, process.language)


def _func_language_of(path: str) -> FuncLanguage:
    """The language of a tasks file or a skip file by its extension: Python
    for `.py`, Bash for any other."""
    return "python" if path.endswith(".py") else "bash"


def _func_file_path(path: str, language: str, default_stem: str) -> str:
    """The path of a tasks file or a method file: the one it was loaded
    with, while its extension still says its language, or else the default
    name with the extension of the language."""
    if path and _func_language_of(path) == language:
        return path
    return f"{default_stem}.{FUNC_EXTENSION_BY_LANGUAGE[language]}"


def tasks_language(process) -> str:
    """The language of the tasks file of a process: that of its options
    handler in the array and generator modes, Bash in the manual mode."""
    handler = process.optionsHandler
    return handler.language if handler.mode in ("array", "generator") else "bash"


def tasks_file_path(process) -> str:
    """The path of the tasks file of a process in the artifact, which the
    module refers to when the file is in Python."""
    return _func_file_path(process.files.tasks, tasks_language(process), f"{process.name}_tasks")


def method_file_path(process, method: str) -> str:
    """The path of the method file of a process in the artifact, which the
    module refers to when it is the skip file in Python."""
    language = process.additionalMethods.skipLanguage if method == "skip" else "bash"
    return _func_file_path(process.files.methods.get(method, ""), language, f"{process.name}_{method}")


def _inside(path: str) -> bool:
    """Whether a relative path stays below the directory it is relative to."""
    return not Path(path).is_absolute() and ".." not in Path(path).parts


def write_code_files(program: Program, directory: str | Path) -> None:
    """
    Writes the files of the artifact of `program` that the editor writes
    (its process files, tasks files and method files, see split) into
    `directory`, under the paths the topology names, for a generated
    script written there to find the files it refers to. A path that
    leaves the directory is skipped.
    """
    for path, text in split(program).files.items():
        if not _inside(path):
            continue
        file_path = Path(directory) / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(text)


def _alias_opt_map_dict(mappings: list[AliasOptMapping]) -> dict[str, str]:
    return {mapping.fromLabel: mapping.toLabel for mapping in mappings}


def _alias_opt_map_list(mapping: dict[str, str]) -> list[AliasOptMapping]:
    return [AliasOptMapping(fromLabel=from_label, toLabel=to_label) for from_label, to_label in mapping.items()]


def _split_group(group: GroupSource | None) -> TopologyGroup | None:
    if group is None:
        return None
    return TopologyGroup(program=group.programName, id=group.groupId, size=group.groupSize, dir=group.sourceDir)


def _join_group(group: TopologyGroup | None) -> GroupSource | None:
    if group is None:
        return None
    return GroupSource(programName=group.program, groupId=group.id, groupSize=group.size, sourceDir=group.dir)


def _language_key(path: str, language: str) -> dict:
    """`language` for the file, only when the extension of `path` does not
    give it."""
    extension = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    if LANGUAGE_BY_EXTENSION.get(extension) == language:
        return {}
    return {"language": language}


def _split_code(split: SplitProgram, program_name: str, process) -> dict:
    """The keys of a process or a sequential process that say where its
    code is, adding the text of its process file to `split` when the editor
    writes it."""
    specs = process.additionalSpecs
    if specs.alias:
        return {"alias": specs.alias, "alias_opt_map": _alias_opt_map_dict(specs.aliasOptMap)}
    if specs.externalAlias:
        return {
            "script": specs.externalAlias,
            "alias_opt_map": _alias_opt_map_dict(specs.aliasOptMap),
            **_language_key(specs.externalAlias, process.language),
        }
    if getattr(process, "nodeKind", None) == "Supervisor":
        return {}
    if getattr(process, "nodeKind", None):
        text = node_heredoc(process)
    else:
        text = process.code
    if not text:
        return {}
    path = process.files.code or _default_code_path(program_name, process.name, process.language)
    split.files[path] = _file_text(text)
    return {"code": path, **_language_key(path, process.language)}


def _split_specs(specs: ComputationalSpecs, additional: AdditionalSpecs) -> TopologySpecs:
    return TopologySpecs(
        **specs.model_dump(exclude_none=True),
        processdeps=additional.processdeps,
        force=additional.force,
    )


def _split_option(option: ProgramOption, process: ProgramProcess, sources: list[str], label_edges: bool) -> TopologyOption:
    labels_by_id = {other.id: other.label for other in process.options}
    is_flag = option.dataType == "None"
    default_mandatory = option.commandLine and not is_flag
    return TopologyOption(
        type="flag" if is_flag else option.dataType,
        description=option.description,
        # A connected input holds its connection sentinel, derived again
        # from the connections when the program is loaded; a shared_dir
        # input holds the name of its directory, which its connections only
        # document.
        value="" if sources and option.channel != "shared_dir" else option.value,
        channel=option.channel,
        subpath=option.subpath,
        mirror=option.mirror,
        fifo_tag=option.fifoTag if option.fifoTag == "external" else None,
        cmdline=option.commandLine,
        mandatory=None if option.mandatory == default_mandatory else option.mandatory,
        shaping=option.taskShaping,
        from_spec=option.fromProcessSpec,
        count_source=labels_by_id.get(option.countSourceOptionId) if option.countSourceOptionId else None,
        from_=(sources[0] if len(sources) == 1 else sources) if sources else None,
        display="label" if label_edges else None,
    )


def _split_process(split: SplitProgram, program: Program, process: ProgramProcess) -> TopologyProcess:
    processes_by_id = {other.id: other for other in program.processes}
    sources: dict[str, list[str]] = {}
    label_edges: set[str] = set()
    for edge in program.edges:
        if edge.targetProcessId != process.id:
            continue
        source = processes_by_id[edge.sourceProcessId]
        source_label = next(option.label for option in source.options if option.id == edge.sourceOptionId)
        sources.setdefault(edge.targetOptionId, []).append(f"{source.name}.{source_label}")
        if edge.display == "label":
            label_edges.add(edge.targetOptionId)

    keys = {"description": process.description, **_split_code(split, program.name, process)}

    handler = process.optionsHandler
    tasks = None
    if handler.mode != "standard":
        code = {
            "array": handler.arrayCode,
            "generator": handler.generatorSizeCode,
            "manual": handler.manualCode,
        }[handler.mode]
        tasks = tasks_file_path(process)
        split.files[tasks] = _file_text(code or "")

    methods = {}
    for method, field_name in METHOD_FIELDS.items():
        code = getattr(process.additionalMethods, field_name)
        if code:
            path = method_file_path(process, method)
            split.files[path] = _file_text(code)
            methods[method] = path

    return TopologyProcess(
        **keys,
        mode=None if handler.mode == "standard" else handler.mode,
        tasks=tasks,
        methods=methods,
        conda_envs={env.name: env.file for env in process.additionalMethods.condaEnvs},
        docker_imgs=list(process.additionalMethods.dockerImgs),
        specs=_split_specs(process.computationalSpecs, process.additionalSpecs),
        group=_split_group(process.groupSource),
        kind=process.nodeKind,
        initiator=process.initiator,
        position=TopologyPosition(x=process.position.x, y=process.position.y),
        options={
            option.label: _split_option(option, process, sources.get(option.id, []), option.id in label_edges)
            for option in process.options
        },
    )


def _split_seq_process(split: SplitProgram, program: Program, seq_process: SeqProcess) -> TopologySeqProcess:
    return TopologySeqProcess(
        description=seq_process.description,
        **_split_code(split, program.name, seq_process),
        specs=TopologySeqSpecs(
            **seq_process.computationalSpecs.model_dump(exclude_none=True),
            sched=seq_process.additionalSpecs.sched,
        ),
        group=_split_group(seq_process.groupSource),
    )


def _split_execution(options: ExecutionOptions) -> TopologyExecution:
    return TopologyExecution(
        scheduler=options.scheduler,
        builtin_sched_cpus=options.builtinSchedCpus,
        builtin_sched_mem=options.builtinSchedMem,
        dflt_nodes=options.dfltNodes,
        dflt_throttle=options.dfltThrottle,
        rerun_outdated_procs=options.rerunOutdatedProcs,
        conda_support=options.condaSupport,
        docker_support=options.dockerSupport,
        snapshot_every_secs=options.snapshotEverySecs,
    )


def split(program: Program) -> SplitProgram:
    """
    The artifact of `program`: its topology, and the text of every file the
    topology names that the editor writes, by path. Nothing of the machine
    or of the editor goes into the topology: no id, no revision, no
    directory; and a process without a path for a file gets the default
    name (see _default_code_path).
    """
    result = SplitProgram(topology=Topology(schema_version=SCHEMA_VERSION, name=program.name))
    result.topology = Topology(
        schema_version=SCHEMA_VERSION,
        name=program.name,
        type="resident" if program.programType == "resident" else None,
        description=program.description,
        preamble=program.preamble,
        env=dict(program.envVars),
        shared_dirs=list(program.sharedDirs),
        execution=_split_execution(program.executionOptions),
        program_options=dict(program.programOptions),
        processes={process.name: _split_process(result, program, process) for process in program.processes},
        seq_processes={
            seq_process.name: _split_seq_process(result, program, seq_process) for seq_process in program.seqProcesses
        },
    )
    return result


# --- from the artifact to the program model ----------------------------------


_SOURCE_RE = re.compile(r"^(?P<process>.+?)\.(?P<label>-.+)$")


def _read_file(files: Mapping[str, str], path: str, what: str) -> str:
    """The code held in the file at `path`: its text without the newlines
    that end it. A file that `files` does not hold is an error that names
    it."""
    if path not in files:
        raise TopologyError(f"{what} names the file {path}, which is missing: put the file back, or name another in the topology file")
    return files[path].rstrip("\n")


def _language_of(path: str, language: str | None, what: str) -> str:
    if language:
        return language
    name = path.rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[-1] if "." in name else ""
    if extension not in LANGUAGE_BY_EXTENSION:
        raise TopologyError(f"{what}: the extension of {path} says no language; give one with `language`")
    return LANGUAGE_BY_EXTENSION[extension]


def _join_code(files: Mapping[str, str], process_name: str, topology_process, is_node: bool) -> tuple[dict, dict]:
    """The fields of a process or a sequential process that hold its code,
    and the additional specifications that say where it comes from."""
    what = f'process "{process_name}"'
    given = [key for key in ("code", "script", "alias") if getattr(topology_process, key)]
    if len(given) > 1:
        raise TopologyError(f"{what} gives {' and '.join(given)}: give one of them")
    if getattr(topology_process, "kind", None) == "Supervisor" and given:
        raise TopologyError(f"{what} is the Supervisor, whose code script generation writes: it takes no {given[0]}")
    fields: dict = {"language": "bash", "code": "", "files": ProcessFiles()}
    specs: dict = {"alias": None, "aliasOptMap": [], "externalAlias": None}
    if topology_process.alias:
        specs |= {"alias": topology_process.alias, "aliasOptMap": _alias_opt_map_list(topology_process.alias_opt_map)}
    elif topology_process.script:
        path = topology_process.script
        specs |= {"externalAlias": path, "aliasOptMap": _alias_opt_map_list(topology_process.alias_opt_map)}
        # The copy of the script that the editor shows, when it is at hand.
        fields |= {"language": _language_of(path, topology_process.language, what), "code": files.get(path, "").rstrip("\n")}
    elif topology_process.code:
        path = topology_process.code
        fields |= {
            "language": _language_of(path, topology_process.language, what),
            "code": _read_file(files, path, what),
            "files": ProcessFiles(code=path),
        }
    elif topology_process.alias_opt_map:
        raise TopologyError(f"{what} gives alias_opt_map without an alias or a script")
    if is_node and fields["code"]:
        decomposed = decompose_heredoc(fields["code"])
        if decomposed.misfits:
            problems = "; ".join(
                f"line {misfit.line}: {misfit.problem}, {misfit.fix}" if misfit.line else f"{misfit.problem}, {misfit.fix}"
                for misfit in decomposed.misfits
            )
            raise TopologyError(f"{what}: the file {topology_process.code} does not fit the parts of a node: {problems}")
        fields |= {"language": "python", "code": "", "nodeCode": decomposed.code}
    return fields, specs


def _join_option(program_name: str, process_name: str, label: str, option: TopologyOption, labels: set[str]) -> ProgramOption:
    is_flag = option.type == "flag"
    mandatory = option.mandatory if option.mandatory is not None else (option.cmdline and not is_flag)
    count_source_id = None
    if option.count_source is not None:
        if option.count_source not in labels:
            raise TopologyError(
                f'process "{process_name}", option {label}: the count source {option.count_source} is no option of the process'
            )
        count_source_id = element_id(program_name, process_name, option.count_source)
    return ProgramOption(
        id=element_id(program_name, process_name, label),
        label=label,
        direction="output" if label.startswith("-out") or label.startswith("--out") else "input",
        dataType="None" if is_flag else option.type,
        channel=option.channel,
        subpath=option.subpath,
        mirror=option.mirror,
        fifoTag=option.fifo_tag,
        description=option.description,
        value=option.value,
        commandLine=option.cmdline,
        mandatory=mandatory,
        fromProcessSpec=option.from_spec,
        countSourceOptionId=count_source_id,
        taskShaping=option.shaping,
    )


def _join_edges(topology: Topology) -> list[ProgramEdge]:
    """The connections of every input that names what it reads."""
    edges = []
    for target_name, process in topology.processes.items():
        for target_label, option in process.options.items():
            sources = option.from_
            if sources is None:
                continue
            for source in [sources] if isinstance(sources, str) else sources:
                where = f'process "{target_name}", option {target_label}'
                match = _SOURCE_RE.match(source)
                if not match:
                    raise TopologyError(f'{where}: "{source}" is not a source, "<process>.<label>"')
                source_name, source_label = match.group("process"), match.group("label")
                source_process = topology.processes.get(source_name)
                if source_process is None:
                    raise TopologyError(f'{where}: reads from "{source_name}", which is no process of the program')
                if source_label not in source_process.options:
                    raise TopologyError(f'{where}: reads {source_label} of "{source_name}", which has no such option')
                edges.append(
                    ProgramEdge(
                        id=element_id(topology.name, "edge", source_name, source_label, target_name, target_label),
                        sourceProcessId=element_id(topology.name, source_name),
                        sourceOptionId=element_id(topology.name, source_name, source_label),
                        targetProcessId=element_id(topology.name, target_name),
                        targetOptionId=element_id(topology.name, target_name, target_label),
                        display=option.display or "line",
                    )
                )
    return edges


def _join_process(topology: Topology, files: Mapping[str, str], name: str, process: TopologyProcess) -> ProgramProcess:
    what = f'process "{name}"'
    fields, specs = _join_code(files, name, process, process.kind is not None and process.kind != "Supervisor")
    if process.kind == "Supervisor":
        fields |= {"language": "python", "code": ""}

    handler = OptionsHandler(mode=process.mode or "standard")
    if process.mode:
        if process.tasks is None:
            raise TopologyError(f"{what} is in {process.mode} mode and names no tasks file")
        code = _read_file(files, process.tasks, what)
        setattr(handler, {"array": "arrayCode", "generator": "generatorSizeCode", "manual": "manualCode"}[process.mode], code)
        handler.language = _func_language_of(process.tasks)
        if process.mode == "manual" and handler.language == "python":
            raise TopologyError(
                f"{what} is in manual mode, whose tasks file is a Bash function, and names the Python file {process.tasks}: "
                "rename the tasks file to .sh, or use the array or generator mode"
            )
        fields["files"].tasks = process.tasks
    elif process.tasks is not None:
        raise TopologyError(f"{what} names a tasks file and no mode")

    methods = AdditionalMethods(
        condaEnvs=[CondaEnv(name=name, file=file) for name, file in process.conda_envs.items()],
        dockerImgs=list(process.docker_imgs),
    )
    for method, path in process.methods.items():
        if method != "skip" and _func_language_of(path) == "python":
            raise TopologyError(f"{what}: the {method} method is a Bash body, and names the Python file {path}")
        setattr(methods, METHOD_FIELDS[method], _read_file(files, path, what))
        fields["files"].methods[method] = path
    if "skip" in process.methods:
        methods.skipLanguage = _func_language_of(process.methods["skip"])
    for method, data_key in (("conda_envs", "conda_envs"), ("docker_imgs", "docker_imgs")):
        if method in process.methods and getattr(process, data_key):
            raise TopologyError(
                f"{what} gives both {data_key} and a {method} method file: remove the {data_key} key or the {method} entry of methods"
            )

    spec_fields = process.specs.model_dump(exclude={"processdeps", "force"})
    labels = set(process.options)
    return ProgramProcess(
        id=element_id(topology.name, name),
        name=name,
        description=process.description,
        position=Position(x=process.position.x, y=process.position.y) if process.position else Position(x=0, y=0),
        options=[_join_option(topology.name, name, label, option, labels) for label, option in process.options.items()],
        optionsHandler=handler,
        computationalSpecs=ComputationalSpecs(**spec_fields),
        additionalSpecs=AdditionalSpecs(force=process.specs.force, processdeps=process.specs.processdeps, **specs),
        additionalMethods=methods,
        groupSource=_join_group(process.group),
        nodeKind=process.kind,
        initiator=process.initiator,
        **fields,
    )


def _join_seq_process(topology: Topology, files: Mapping[str, str], name: str, seq_process: TopologySeqProcess) -> SeqProcess:
    fields, specs = _join_code(files, name, seq_process, False)
    return SeqProcess(
        id=element_id(topology.name, name),
        name=name,
        description=seq_process.description,
        computationalSpecs=SeqComputationalSpecs(**seq_process.specs.model_dump(exclude={"sched"})),
        additionalSpecs=SeqAdditionalSpecs(sched=seq_process.specs.sched, **specs),
        groupSource=_join_group(seq_process.group),
        **fields,
    )


def _join_execution(execution: TopologyExecution) -> ExecutionOptions:
    return ExecutionOptions(
        scheduler=execution.scheduler,
        builtinSchedCpus=execution.builtin_sched_cpus,
        builtinSchedMem=execution.builtin_sched_mem,
        dfltNodes=execution.dflt_nodes,
        dfltThrottle=execution.dflt_throttle,
        rerunOutdatedProcs=execution.rerun_outdated_procs,
        condaSupport=execution.conda_support,
        dockerSupport=execution.docker_support,
        snapshotEverySecs=execution.snapshot_every_secs,
    )


def _place(program: Program, unplaced_names: set[str]) -> None:
    """Gives the processes without a position one, as the editor places the
    processes of an imported program; the others keep theirs."""
    unplaced = [process for process in program.processes if process.name in unplaced_names]
    if not unplaced:
        return
    names_by_id = {process.id: process.name for process in program.processes}
    positions = layout(
        [process.name for process in program.processes],
        [(names_by_id[edge.sourceProcessId], names_by_id[edge.targetProcessId]) for edge in program.edges],
    )
    for process in unplaced:
        x, y = positions[process.name]
        process.position = Position(x=x, y=y)


def join(topology: Topology, files: Mapping[str, str]) -> Program:
    """
    The program model of a topology and the text of the files it names, by
    path (a missing process file, tasks file or method file is an error; a
    missing script only leaves the editor nothing to show). The ids come
    from the names (see element_id), the home directory, the output
    directory and the revision are left empty for persistence to fill, and
    a process without a position is placed as an imported one is. Raises
    TopologyError for what the topology gets wrong (see the class).
    """
    program = Program(
        id=element_id(topology.name),
        name=topology.name,
        programType="resident" if topology.type == "resident" else "general",
        description=topology.description,
        preamble=topology.preamble,
        envVars=dict(topology.env),
        homeDir="",
        outputDir="",
        sourceDir="",
        executionOptions=_join_execution(topology.execution),
        programOptions=dict(topology.program_options),
        sharedDirs=list(topology.shared_dirs),
        availableSharedDirs=[],
        processes=[_join_process(topology, files, name, process) for name, process in topology.processes.items()],
        seqProcesses=[
            _join_seq_process(topology, files, name, seq_process) for name, seq_process in topology.seq_processes.items()
        ],
        edges=_join_edges(topology),
    )
    _place(program, {name for name, process in topology.processes.items() if process.position is None})
    return program
