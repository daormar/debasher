import { apiFetch, clearTokenRefused } from "./apiFetch";

// What the web UI offers that depends on where the backend runs.
export interface WebuiInfo {
  // Whether the Help menu gives the command that starts Claude Code on a
  // program: not where the backend runs in a container, whose directories
  // are not those of the user's computer.
  claudeCode: boolean;
}

export async function getWebuiInfo(): Promise<WebuiInfo> {
  const response = await apiFetch("/api/webui/info");

  if (!response.ok) {
    throw new Error(`Failed to get what the web UI offers (${response.status})`);
  }

  return response.json();
}

// Asks the backend again whether it takes the token of the tab, once the tab
// has a new one: a refused request marks the token refused again.
export async function checkToken(): Promise<void> {
  clearTokenRefused();
  try {
    await getWebuiInfo();
  } catch {
    // Not refused for its token: left to the requests of the editor.
  }
}
