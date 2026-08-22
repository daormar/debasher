import type { WorkflowEdge } from "./edge";
import type { WorkflowNode } from "./node";

export interface Workflow {

  id: string;

  name: string;

  preamble: string;

  nodes: WorkflowNode[];

  edges: WorkflowEdge[];

}
