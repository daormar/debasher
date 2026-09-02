import type { Program } from "../models/program";

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

export async function saveProgram(
  program: Program,
  outputDir: string
): Promise<void> {
  const response = await fetch("/api/programs/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outputDir, program }),
  });

  if (!response.ok) {
    throw new Error(`Failed to save program: ${await errorMessage(response)}`);
  }
}

export async function loadProgram(inputDir: string): Promise<Program> {
  const response = await fetch("/api/programs/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputDir }),
  });

  if (!response.ok) {
    throw new Error(`Failed to load program: ${await errorMessage(response)}`);
  }

  return response.json();
}

export async function importProgram(
  scriptPath: string,
  debasherModDir: string
): Promise<Program> {
  const response = await fetch("/api/programs/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptPath, debasherModDir }),
  });

  if (!response.ok) {
    throw new Error(`Failed to import program: ${await errorMessage(response)}`);
  }

  return response.json();
}

/**
 * Not persisted yet — just builds a blank program in memory.
 * It only gets stored once the user actually saves it.
 */
export function createEmptyProgram(name: string): Program {
  return {
    id: crypto.randomUUID(),
    name,
    description: "",
    preamble: "",
    envVars: {},
    homeDir: "",
    outputDir: "",
    sourceDir: "",
    executionOptions: { scheduler: "" },
    programOptions: {},
    processes: [],
    edges: [],
  };
}
