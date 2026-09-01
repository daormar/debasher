from typing import Literal, Optional

from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float


class ProgramOption(BaseModel):
    id: str
    label: str
    direction: Literal["input", "output"]
    dataType: Literal["int", "float", "string", "None"]
    description: str
    value: str
    fifo: bool
    commandLine: bool
    mandatory: bool = False


class ComputationalSpecs(BaseModel):
    cpus: Optional[float] = None
    mem: Optional[float] = None
    time: Optional[str] = None


class AdditionalSpecs(BaseModel):
    forced: bool
    processdeps: Optional[str] = None
    alias: Optional[str] = None
    externalAlias: Optional[str] = None


class OptionsHandler(BaseModel):
    mode: Literal["standard", "array", "generator", "manual"]
    generatorSize: Optional[str] = None
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
    executionOptions: ExecutionOptions
    programOptions: dict[str, str]
    processes: list[ProgramProcess]
    edges: list[ProgramEdge]
