import type { Workflow } from "../models/workflow";

/**
 * Lightweight summary used to list workflows without loading
 * the full nodes/edges of each one.
 */
export interface WorkflowSummary {
  id: string;
  name: string;
}

// ---------------------------------------------------------------
// FAKE IMPLEMENTATION — replace the body of each function below
// with real `fetch` calls to your backend when it's ready. The
// function signatures (name, params, return type) are the actual
// contract the rest of the app depends on: as long as they stay
// the same, nothing outside this file needs to change.
// ---------------------------------------------------------------

const fakeDb = new Map<string, Workflow>();

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  return Array.from(fakeDb.values()).map(workflow => ({
    id: workflow.id,
    name: workflow.name,
  }));
}

export async function loadWorkflow(id: string): Promise<Workflow> {
  const workflow = fakeDb.get(id);

  if (!workflow) {
    throw new Error(`Workflow "${id}" not found`);
  }

  // Return a copy so nothing outside this module can accidentally
  // mutate the "stored" version directly.
  return structuredClone(workflow);
}

export async function saveWorkflow(workflow: Workflow): Promise<void> {
  fakeDb.set(workflow.id, structuredClone(workflow));
}

/**
 * Not persisted yet — just builds a blank workflow in memory.
 * It only gets stored once the user actually saves it.
 */
export function createEmptyWorkflow(name: string): Workflow {
  return {
    id: crypto.randomUUID(),
    name,
    preamble: "",
    nodes: [],
    edges: [],
  };
}
