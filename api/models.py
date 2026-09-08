from typing import Literal, Optional

from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float


class ProgramOption(BaseModel):
    id: str
    label: str
    direction: Literal["input", "output"]
    dataType: Literal["int", "float", "string", "file", "None"]
    # How the value is delivered, independent of its type: "none" is a
    # literal/computed value (or a connection, via the value's own
    # "[proc;opt]" sentinel), "value_desc" is an engine-synthesized
    # descriptor for this process's own output (always output-direction —
    # the consuming side never marks itself, it just connects normally),
    # "fifo" is a named pipe, which — unlike value_desc — isn't
    # direction-restricted: a process can legitimately open an input via
    # a fifo it rendezvous on rather than a plain connection. "shared_dir"
    # isn't direction-restricted either: its value always comes from
    # get_absolute_shdirname(value) regardless of any connection — value
    # holds the shared directory's name (one of Program.sharedDirs), not
    # a path. Connections between two shared_dir options (see
    # frontend's isValidProgramConnection) are purely documentary/DAG-
    # visualization aids: the engine already derives the real dependency
    # from every writer resolving to the identical absolute path
    # (DEBASHER_OUT_VALUE_TO_PROCESSES in engine/debasher_lib_opts.sh),
    # independent of whether such a connection is drawn at all.
    channel: Literal["none", "value_desc", "fifo", "shared_dir"] = "none"
    description: str
    value: str
    commandLine: bool
    mandatory: bool = False
    # On a "standard"-mode process only, whether this option's value comes
    # from an attribute of the process's own process_spec (searched among
    # computational specs — cpus, mem, time, nodes, account, partition,
    # throttle — then among additional specs — processdeps, force, alias,
    # ext_alias — via debasher::define_procspec_opt) rather than being a
    # literal/connection/channel-delivered value. Deliberately not folded
    # into `channel`: unlike value_desc/fifo/shared_dir, which describe a
    # genuinely different runtime delivery mechanism, a process-spec-
    # sourced option is an ordinary literal once resolved — this is
    # define-time provenance only, the same kind of thing commandLine
    # already captures for cmdline-sourced options. Mutually exclusive
    # with commandLine (see script_generation.py's _option_definition_line).
    # When true, `value` holds the spec attribute's name (e.g. "cpus"),
    # not its runtime value — mirroring how a "shared_dir"-channel
    # option's `value` holds the shared directory's name rather than its
    # resolved path.
    fromProcessSpec: bool = False
    # On a "standard"-mode process only, the id of another option on the
    # same process (with commandLine=True) supplying the runtime count
    # for a fanout family (a label ending in "ith") — see
    # script_generation.py's _is_fanout_label/_fanout_definition_lines.
    countSourceOptionId: Optional[str] = None


class ComputationalSpecs(BaseModel):
    cpus: Optional[float] = None
    mem: Optional[float] = None
    time: Optional[str] = None


class AdditionalSpecs(BaseModel):
    force: bool
    processdeps: Optional[str] = None
    alias: Optional[str] = None
    externalAlias: Optional[str] = None


class OptionsHandler(BaseModel):
    mode: Literal["standard", "array", "generator", "manual"]
    generatorSizeCode: Optional[str] = None
    arrayCode: Optional[str] = None
    manualCode: Optional[str] = None


class ProgramProcess(BaseModel):
    id: str
    name: str
    description: str
    position: Position
    options: list[ProgramOption]
    optionsHandler: OptionsHandler
    language: Literal["bash", "python", "perl", "r", "groovy"]
    code: str
    computationalSpecs: ComputationalSpecs
    additionalSpecs: AdditionalSpecs


class ProgramEdge(BaseModel):
    id: str
    sourceProcessId: str
    sourceOptionId: str
    targetProcessId: str
    targetOptionId: str


class ExecutionOptions(BaseModel):
    scheduler: str


class Program(BaseModel):
    id: str
    name: str
    description: str = ""
    preamble: str
    envVars: dict[str, str]
    homeDir: str = ""
    outputDir: str
    # Absolute directory of the .sh this program was imported from (see
    # program_import.py), empty for a program that wasn't imported. Used
    # only to resolve a process's AdditionalSpecs.externalAlias — a path
    # relative to that directory — when copying the aliased file
    # alongside a later save (see persistence.copy_ext_alias_files).
    sourceDir: str = ""
    executionOptions: ExecutionOptions
    programOptions: dict[str, str]
    # Names of the module-level shared directories declared for this
    # program (see script_generation.py's _add_shared_dirs_func), each
    # becoming one debasher::define_shared_dir call in the generated
    # <name>_shared_dirs function.
    sharedDirs: list[str] = []
    # Every shared directory name reachable from this program — its own
    # sharedDirs plus every one declared by a module it loads,
    # transitively (see doc_mod.run_doc_mod_all_shared_dirs, populated
    # only by program_import.py). Purely additive: never written back by
    # script generation, and never a substitute for sharedDirs, which is
    # what codegen actually emits from — a module this program merely
    # loads may declare shared directories of its own that this program
    # never redeclares.
    availableSharedDirs: list[str] = []
    processes: list[ProgramProcess]
    edges: list[ProgramEdge]
