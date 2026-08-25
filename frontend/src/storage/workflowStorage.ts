import type { Workflow } from "../models/workflow";

// ---------------------------------------------------------------
// FAKE IMPLEMENTATION — replace the body of each function below
// with real `fetch` calls to your backend when it's ready. The
// function signatures (name, params, return type) are the actual
// contract the rest of the app depends on: as long as they stay
// the same, nothing outside this file needs to change.
// ---------------------------------------------------------------

export async function saveWorkflow(
  workflow: Workflow,
  outputDir: string
): Promise<void> {
  const response = await fetch("/api/workflows/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outputDir, workflow }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `Failed to save workflow (${response.status}): ${body}`
    );
  }
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
    processes: [],
    edges: [],
  };
}
