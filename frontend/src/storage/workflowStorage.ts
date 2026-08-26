import type { Workflow } from "../models/workflow";

// ---------------------------------------------------------------
// FAKE IMPLEMENTATION — replace the body of each function below
// with real `fetch` calls to your backend when it's ready. The
// function signatures (name, params, return type) are the actual
// contract the rest of the app depends on: as long as they stay
// the same, nothing outside this file needs to change.
// ---------------------------------------------------------------

// FastAPI's default error body is `{"detail": "..."}`. Prefer that
// message when present, otherwise fall back to the raw response body.
async function errorMessage(response: Response): Promise<string> {
  const body = await response.text();

  try {
    const parsed = JSON.parse(body);
    if (typeof parsed?.detail === "string") {
      return parsed.detail;
    }
  } catch {
    // Not JSON — fall through and use the raw body.
  }

  return body;
}

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
    throw new Error(`Failed to save workflow: ${await errorMessage(response)}`);
  }
}

export async function loadWorkflow(inputDir: string): Promise<Workflow> {
  const response = await fetch("/api/workflows/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputDir }),
  });

  if (!response.ok) {
    throw new Error(`Failed to load workflow: ${await errorMessage(response)}`);
  }

  return response.json();
}

export async function importWorkflow(scriptPath: string): Promise<Workflow> {
  const response = await fetch("/api/workflows/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptPath, workflow: createEmptyWorkflow("") }),
  });

  if (!response.ok) {
    throw new Error(`Failed to import workflow: ${await errorMessage(response)}`);
  }

  return response.json();
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
    envVars: {},
    outputDir: "",
    executionOptions: { scheduler: "" },
    processes: [],
    edges: [],
  };
}
