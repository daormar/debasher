import type { ProcessInfo } from "../models/process";
import type { NodeHookPart, NodeInfo, SuggestedNode } from "../models/node";

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

// FastAPI's error body is `{"detail": "..."}`: the reason, when there is one.
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON: no reason to give.
  }
  return `status ${response.status}`;
}

export async function suggestNodes(
  preamble: string,
  envVars: Record<string, string>
): Promise<SuggestedNode[]> {
  const response = await fetch("/api/processes/suggest-nodes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preamble, envVars }),
  });

  if (!response.ok) {
    throw new Error(`Failed to suggest nodes (${response.status})`);
  }

  const { nodes } = await response.json();
  return nodes;
}

/**
 * A node of the preamble, to add it to a resident program. A node that the
 * web UI cannot hold throws an Error whose message says why, line by line.
 */
export async function getNodeInfo(
  preamble: string,
  envVars: Record<string, string>,
  name: string
): Promise<NodeInfo> {
  const response = await fetch("/api/processes/get-node-info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preamble, envVars, name }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }

  const { info } = await response.json();
  return info;
}

// The code of the hooks that a node of `kind` inherits from its class of the
// runtime library (a ProgramLauncher or a DirectoryWatcher implements every
// hook), read from the library itself, by field of NodeCode: the node code
// editor shows it read only next to each hook. Empty for an FBPProcess.
export async function getInheritedHooks(
  kind: string
): Promise<{ hooks: Partial<Record<NodeHookPart, string>>; error: string | null }> {
  const response = await fetch("/api/processes/inherited-hooks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }

  return response.json();
}
