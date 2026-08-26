from typing import Literal, Optional

from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float


class WorkflowOption(BaseModel):
    id: str
    label: str
    direction: Literal["input", "output"]
    dataType: Literal["int", "float", "string"]
    description: str
    value: str
    fifo: bool
    commandLine: bool


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


class WorkflowProcess(BaseModel):
    id: str
    name: str
    position: Position
    options: list[WorkflowOption]
    optionsHandler: OptionsHandler
    language: Literal["bash", "python", "perl", "r", "groovy"]
    code: str
    computationalSpecs: ComputationalSpecs
    additionalSpecs: AdditionalSpecs


class WorkflowEdge(BaseModel):
    id: str
    sourceProcessId: str
    sourceOptionId: str
    targetProcessId: str
    targetOptionId: str


class Workflow(BaseModel):
    id: str
    name: str
    preamble: str
    envVars: dict[str, str]
    outputDir: str
    processes: list[WorkflowProcess]
    edges: list[WorkflowEdge]
