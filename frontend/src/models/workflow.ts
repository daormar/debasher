import type { WorkflowEdge } from "./edge";
import type { WorkflowProcess } from "./process";

export interface Workflow {

  id: string;

  name: string;

  preamble: string;

  envVars: Record<string, string>;

  processes: WorkflowProcess[];

  edges: WorkflowEdge[];

}
