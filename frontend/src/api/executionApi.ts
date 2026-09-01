import type { Program } from "../models/program";

// FastAPI's default error body is `{"detail": "..."}`. Prefer that
// message when present, otherwise fall back to a generic one.
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON — fall through to the fallback message.
  }

  return fallback;
}

export async function listSchedulers(): Promise<string[]> {
  const response = await fetch("/api/execution/schedulers");

  if (!response.ok) {
    throw new Error(`Failed to list schedulers (${response.status})`);
  }

  const { schedulers } = await response.json();
  return schedulers;
}

// Launches the run in the background and returns as soon as it's
// started — it does not wait for the program to finish. Poll
// getProgramState() to find out when it's done.
export async function runProgram(program: Program): Promise<void> {
  const response = await fetch("/api/execution/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to run program (${response.status})`)
    );
  }
}

export async function runProgramDebug(program: Program): Promise<string> {
  const response = await fetch("/api/execution/run-debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to run program (debug) (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

export type ProgramState = "finished" | "in-progress" | "unfinished";

interface ProgramStatusResult {
  output: string;
  state: ProgramState;
}

async function fetchProgramStatus(program: Program): Promise<ProgramStatusResult> {
  const response = await fetch("/api/execution/status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to get program status (${response.status})`);
  }

  return response.json();
}

export async function getProgramStatus(program: Program): Promise<string> {
  const { output } = await fetchProgramStatus(program);
  return output;
}

// Cheap check of whether a run is still going, backed by the same
// debasher_status call as getProgramStatus() — used to poll a
// background run and to guard against launching a second one.
export async function getProgramState(program: Program): Promise<ProgramState> {
  const { state } = await fetchProgramStatus(program);
  return state;
}

export async function checkProgramOptions(program: Program): Promise<string> {
  const response = await fetch("/api/execution/check-program-options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to check program options (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

export async function stopProgram(program: Program): Promise<string> {
  const response = await fetch("/api/execution/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to stop program (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}
