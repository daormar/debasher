import { apiFetch, clearTokenRefused } from "./apiFetch";

// What the web UI offers that depends on where the backend runs.
export interface WebuiInfo {
  // Whether the Help menu gives the command that starts Claude Code on a
  // program: not where the directories of the backend are not those of the
  // machine where Claude Code would run.
  claudeCode: boolean;
  // What that command is run through, to run it where the backend runs, as
  // the `docker compose exec` of the container of the Docker image; null to
  // run it as it is.
  claudeCodePrefix: string | null;
  // The command that installs Claude Code there, where it does not come with
  // the rest; null where the user installs it.
  claudeCodeInstall: string | null;
  // The URL of the backend from its own machine; null when the backend does
  // not know its port (uvicorn started by hand).
  backendUrl: string | null;
}

// What a backend that cannot answer is taken to offer: the command as it is,
// naming the origin of the page.
export const DEFAULT_WEBUI_INFO: WebuiInfo = {
  claudeCode: true,
  claudeCodePrefix: null,
  claudeCodeInstall: null,
  backendUrl: null,
};

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
