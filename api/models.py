from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float


class WorkflowHandle(BaseModel):
    id: str
    label: str
    direction: str  # "input" | "output"


class WorkflowNode(BaseModel):
    id: str
    name: str
    position: Position
    handles: list[WorkflowHandle]


class WorkflowEdge(BaseModel):
    id: str
    sourceNodeId: str
    sourceHandleId: str
    targetNodeId: str
    targetHandleId: str


class Workflow(BaseModel):
    id: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
