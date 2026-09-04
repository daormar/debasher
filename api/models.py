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
    # a fifo it rendezvous on rather than a plain connection.
    channel: Literal["none", "value_desc", "fifo"] = "none"
    description: str
    value: str
    commandLine: bool
    mandatory: bool = False


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
    processes: list[ProgramProcess]
    edges: list[ProgramEdge]
