import { apiFetch } from "./apiFetch";
import type { ClaudeConversation } from "../models/claudeCommand";

// A session of Claude Code in the page (see "Opening a session in the page"
// in doc/design_doc_webui.md): an ordinary request with the token gets a
// ticket, which the WebSocket of the terminal carries instead of the token,
// since a browser cannot give a WebSocket the header of the token.

export interface SessionRequest {
  homeDir: string;
  start: ClaudeConversation;
  cols: number;
  rows: number;
  // Ends the session of the program in another tab, and starts with the
  // last conversation whatever `start` says.
  takeOver: boolean;
}

export type SessionAnswer =
  | { ticket: string }
  | { status: number; detail: string };

export async function requestClaudeSession(request: SessionRequest): Promise<SessionAnswer> {
  const response = await apiFetch("/api/claude/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  const body = await response.json().catch(() => null);
  if (response.ok) {
    return { ticket: body.ticket };
  }
  const detail = typeof body?.detail === "string" ? body.detail : "";
  return { status: response.status, detail };
}

// The address of the WebSocket of a session, on the origin of the page,
// which the backend serves (the dev server forwards it, as it does /api).
export function terminalUrl(
  ticket: string,
  location: Pick<Location, "protocol" | "host"> = window.location,
): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/api/claude/terminal?ticket=${encodeURIComponent(ticket)}`;
}
