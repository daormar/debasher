import type { Workflow } from "../models/workflow";

export async function listSchedulers(): Promise<string[]> {
  const response = await fetch("/api/execution/schedulers");

  if (!response.ok) {
    throw new Error(`Failed to list schedulers (${response.status})`);
  }

  const { schedulers } = await response.json();
  return schedulers;
}

export async function runWorkflow(workflow: Workflow): Promise<string> {
  const response = await fetch("/api/execution/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to run workflow (${response.status})`);
  }

  const { output } = await response.json();
  return output;
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

export async function getWorkflowStatus(workflow: Workflow): Promise<string> {
  const response = await fetch("/api/execution/status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });

  if (!response.ok) {
    throw new Error(`Failed to get workflow status (${response.status})`);
  }

  const { output } = await response.json();
  return output;
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
