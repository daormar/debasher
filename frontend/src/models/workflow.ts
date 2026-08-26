import type { WorkflowEdge } from "./edge";
import type { WorkflowProcess } from "./process";

export interface ExecutionOptions {

  scheduler: string;

}

export interface Workflow {

  id: string;

  name: string;

  preamble: string;

  envVars: Record<string, string>;

  outputDir: string;

  executionOptions: ExecutionOptions;

  workflowOptions: Record<string, string>;

  processes: WorkflowProcess[];

  edges: WorkflowEdge[];

}
