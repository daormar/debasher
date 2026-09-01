import type { Workflow } from "../models/workflow";

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
// started — it does not wait for the workflow to finish. Poll
// getWorkflowState() to find out when it's done.
export async function runWorkflow(workflow: Workflow): Promise<void> {
  const response = await fetch("/api/execution/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to run workflow (${response.status})`)
    );
  }
}

export async function runWorkflowDebug(workflow: Workflow): Promise<string> {
  const response = await fetch("/api/execution/run-debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to run workflow (debug) (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

export type WorkflowState = "finished" | "in-progress" | "unfinished";

interface WorkflowStatusResult {
  output: string;
  state: WorkflowState;
}

async function fetchWorkflowStatus(workflow: Workflow): Promise<WorkflowStatusResult> {
  const response = await fetch("/api/execution/status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to get workflow status (${response.status})`);
  }

  return response.json();
}

export async function getWorkflowStatus(workflow: Workflow): Promise<string> {
  const { output } = await fetchWorkflowStatus(workflow);
  return output;
}

// Cheap check of whether a run is still going, backed by the same
// debasher_status call as getWorkflowStatus() — used to poll a
// background run and to guard against launching a second one.
export async function getWorkflowState(workflow: Workflow): Promise<WorkflowState> {
  const { state } = await fetchWorkflowStatus(workflow);
  return state;
}

export async function checkWorkflowOptions(workflow: Workflow): Promise<string> {
  const response = await fetch("/api/execution/check-workflow-options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to check workflow options (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

export async function stopWorkflow(workflow: Workflow): Promise<string> {
  const response = await fetch("/api/execution/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to stop workflow (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}
