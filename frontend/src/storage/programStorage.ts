import type { Program, ProgramType } from "../models/program";
import { DEFAULT_SCHEDULER } from "../models/program";
import { layoutProcesses } from "../models/programLayout";
import { throwIfRevisionConflict } from "../api/revisionConflict";
import { apiFetch } from "../api/apiFetch";

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

// Saves the program into `outputDir` and returns the revision of the program
// metadata written there, or throws a RevisionConflict when someone else
// saved the program since it was loaded.
export async function saveProgram(
  program: Program,
  outputDir: string
): Promise<{ revision: number }> {
  const response = await apiFetch("/api/programs/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outputDir, program }),
  });

  await throwIfRevisionConflict(response);

  if (!response.ok) {
    throw new Error(`Failed to save program: ${await errorMessage(response)}`);
  }

  const { revision } = await response.json();
  return { revision };
}

// The revision of the program metadata in `homeDir`, null when there is
// none, without loading the program.
export async function getProgramRevision(homeDir: string): Promise<number | null> {
  const response = await apiFetch("/api/programs/revision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ homeDir }),
  });

  if (!response.ok) {
    throw new Error(`Failed to read the revision of the program: ${await errorMessage(response)}`);
  }

  const { revision } = await response.json();
  return revision;
}

// The directory holds no program metadata to load.
export class NoProgramMetadata extends Error {}

export async function loadProgram(inputDir: string): Promise<Program> {
  const response = await apiFetch("/api/programs/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputDir }),
  });

  if (response.status === 404) {
    throw new NoProgramMetadata(`Failed to load program: ${await errorMessage(response)}`);
  }

  if (!response.ok) {
    throw new Error(`Failed to load program: ${await errorMessage(response)}`);
  }

  return response.json();
}

// Imports the module at `scriptPath`, whose processes, about whose
// positions the module says nothing, are placed in layers by their
// connections (see layoutProcesses).
export async function importProgram(
  scriptPath: string,
  debasherModDir: string
): Promise<Program> {
  const response = await apiFetch("/api/programs/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scriptPath, debasherModDir }),
  });

  if (!response.ok) {
    throw new Error(`Failed to import program: ${await errorMessage(response)}`);
  }

  return layoutProcesses(await response.json());
}

export async function getAllEnvVars(
  program: Program
): Promise<Record<string, string>> {
  const response = await apiFetch("/api/programs/all-envvars", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program }),
  });

  if (!response.ok) {
    throw new Error(`Failed to get all env vars: ${await errorMessage(response)}`);
  }

  const { envVars } = await response.json();
  return envVars;
}

/**
 * Not persisted yet — just builds a blank program in memory.
 * It only gets stored once the user actually saves it.
 */
export function createEmptyProgram(name: string, programType: ProgramType = "general"): Program {
  return {
    id: crypto.randomUUID(),
    name,
    programType,
    description: "",
    preamble: "",
    envVars: {},
    homeDir: "",
    outputDir: "",
    sourceDir: "",
    revision: 0,
    // Matches ExecutionOptionsEditor's own displayed default, so a
    // program that's run without ever opening that dialog still gets
    // a real --sched value instead of an empty one.
    executionOptions: { scheduler: DEFAULT_SCHEDULER },
    programOptions: {},
    sharedDirs: [],
    availableSharedDirs: [],
    seqProcesses: [],
    processes: [],
    edges: [],
  };
}
