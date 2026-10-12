// What the terminal panel says about a session of Claude Code in the page
// (see "The terminal panel" in doc/design_doc_webui.md), from the answer of
// the request for a session and from how its WebSocket closed.

// Closing codes of the WebSocket that the backend gives: the end of the
// process, after the message with its exit status; a ticket that is unknown
// or expired; a session that another tab took over.
export const CLOSE_NORMAL = 1000;
export const CLOSE_BAD_TICKET = 1008;
export const CLOSE_TAKEN_OVER = 4001;

// A control message of the backend, in JSON: the exit status of the process,
// just before the WebSocket closes. Anything else is not one.
export function exitStatusOf(text: string): number | null {
  try {
    const message = JSON.parse(text);
    return typeof message?.exit === "number" ? message.exit : null;
  } catch {
    return null;
  }
}

// The control message of the page that gives the terminal its size.
export function resizeMessage(cols: number, rows: number): string {
  return JSON.stringify({ resize: [cols, rows] });
}

// Why a session ended, from how its WebSocket closed and the exit status the
// backend gave before (null if it gave none).
export function endingNotice(code: number, exitStatus: number | null): string {
  if (code === CLOSE_TAKEN_OVER) {
    return "The session was opened in another page.";
  }
  if (code === CLOSE_BAD_TICKET) {
    return "The session could not open: another page may have taken this program over.";
  }
  if (exitStatus !== null) {
    if (exitStatus === 0) {
      return "Claude Code ended.";
    }
    return exitStatus < 0
      ? `Claude Code ended, killed by signal ${-exitStatus}.`
      : `Claude Code ended with exit status ${exitStatus}.`;
  }
  return "The connection to the backend was lost: it may have stopped.";
}

// What a refused request for a session says to the user.
export function refusalNotice(status: number, detail: string): string {
  switch (status) {
    case 404:
      return "Claude Code works on a program saved in its home directory: save this one first.";
    case 409:
      return "Claude Code is already open on this program in another page.";
    case 503:
      // The backend words why.
      return detail ? `${detail}.` : "Claude Code cannot run in the page here.";
    default:
      return detail
        ? `The session could not start (${status}): ${detail}.`
        : `The session could not start (${status}).`;
  }
}

// What "Close" asks before it leaves the editor, or null when it has nothing
// to lose: the unsaved changes, and the session of Claude Code in the page,
// which ends with the editor.
export function closeQuestion(unsavedChanges: boolean, sessionActive: boolean): string | null {
  if (unsavedChanges && sessionActive) {
    return "Close the program? The changes made since it was last saved are lost, and the session of Claude Code ends.";
  }
  if (unsavedChanges) {
    return "Close the program? The changes made since it was last saved are lost.";
  }
  if (sessionActive) {
    return "Close the program? The session of Claude Code ends.";
  }
  return null;
}
