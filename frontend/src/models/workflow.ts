import type { WorkflowEdge } from "./edge";
import type { WorkflowProcess } from "./process";

export interface ExecutionOptions {

  scheduler: string;

}

export interface Workflow {

  id: string;

  name: string;

  description: string;

  preamble: string;

  envVars: Record<string, string>;

  // Directory the workflow's own definition (workflow.json) and .sh
  // script are saved to (via the toolbar's "Save" button) — distinct
  // from outputDir, which is where a run's results are written.
  homeDir: string;

  outputDir: string;

  executionOptions: ExecutionOptions;

  workflowOptions: Record<string, string>;

  processes: WorkflowProcess[];

  edges: WorkflowEdge[];

}
