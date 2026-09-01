import type { ProcessInfo } from "../models/process";

export async function validateProcessName(name: string): Promise<boolean> {
  const response = await fetch("/api/processes/validate-name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });

  if (!response.ok) {
    throw new Error(`Failed to validate process name (${response.status})`);
  }

  const { valid } = await response.json();
  return valid;
}

export async function suggestProcessNames(
  preamble: string,
  envVars: Record<string, string>
): Promise<string[]> {
  const response = await fetch("/api/processes/suggest-names", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preamble, envVars }),
  });

  if (!response.ok) {
    throw new Error(`Failed to suggest process names (${response.status})`);
  }

  const { names } = await response.json();
  return names;
}

export async function getProcessInfo(
  preamble: string,
  envVars: Record<string, string>,
  name: string
): Promise<ProcessInfo | null> {
  const response = await fetch("/api/processes/get-info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preamble, envVars, name }),
  });

  if (!response.ok) {
    throw new Error(`Failed to get process info (${response.status})`);
  }

  const { info } = await response.json();
  return info;
}
