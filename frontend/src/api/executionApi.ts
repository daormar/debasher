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

export interface ProgramStatusResult {
  output: string;
  state: ProgramState;
}

// Exported (not just used internally by getProgramStatus/getProgramState
// below) so the run-completion poll in ProgramContext can get both the
// state and the debasher_status output from one call, to show the
// latter alongside an "unfinished" run-finished notice.
export async function fetchProgramStatus(program: Program): Promise<ProgramStatusResult> {
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

// Per-process statuses as reported by debasher_status (e.g. "FINISHED",
// "IN-PROGRESS", "UNFINISHED", "UNFINISHED_BUT_RUNNABLE", "TO-DO"),
// keyed by process name. Used to color nodes in the canvas — see
// ProgramContext's status polling and ProcessNode's use of it.
export async function getProcessStatuses(program: Program): Promise<Record<string, string>> {
  const response = await fetch("/api/execution/process-statuses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to get process statuses (${response.status})`);
  }

  const { statuses } = await response.json();
  return statuses;
}

async function fetchProcessOutput(
  endpoint: string,
  program: Program,
  processName: string,
  taskIndex: number | undefined,
  fallback: string
): Promise<string> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, taskIndex }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, fallback));
  }

  const { output } = await response.json();
  return output;
}

// A process's captured stdout (the canvas's right-click "Inspect
// execution" menu's "Show stdout"). `taskIndex` selects one task's
// file for a process that ran as more than one task — see
// getProcessTasks — and is omitted for a "standard" one-file process.
export async function getProcessStdout(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/process-stdout",
    program,
    processName,
    taskIndex,
    `Failed to get stdout for ${processName}.`
  );
}

// A process's scheduler output (the canvas's right-click "Inspect
// execution" menu's "Show scheduler output"). See getProcessStdout
// for `taskIndex`.
export async function getProcessSchedOut(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/process-sched-out",
    program,
    processName,
    taskIndex,
    `Failed to get scheduler output for ${processName}.`
  );
}

// The task indices that have a stdout or scheduler-output file for
// `processName` — empty for a "standard" one-task process, otherwise
// the "Inspect execution" menu shows a task picker before fetching
// either output (see ProcessTaskPicker). Not necessarily contiguous,
// and can run into the thousands for a large array/generator, so this
// is the one place that count is dealt with — everything downstream
// just gets a plain number to pass back as taskIndex.
export async function getProcessTasks(
  program: Program,
  processName: string
): Promise<number[]> {
  const response = await fetch("/api/execution/process-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName }),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to list tasks for ${processName}.`)
    );
  }

  const { taskIndices } = await response.json();
  return taskIndices;
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

// Deletes everything inside program.outputDir. Resolves to false
// (rather than throwing) when the backend's own guards made it a
// no-op — e.g. outputDir is blank — so the caller can tell the user
// there was nothing to reset.
export async function resetOutputDir(program: Program): Promise<boolean> {
  const response = await fetch("/api/execution/reset-output-dir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to reset output directory (${response.status})`)
    );
  }

  const { cleared } = await response.json();
  return cleared;
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
