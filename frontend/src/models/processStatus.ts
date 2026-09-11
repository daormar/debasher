// Per-process status strings as reported by debasher_status (see
// engine/debasher_lib.sh's DEBASHER_*_PROCESS_STATUS constants).
export type ProcessRunStatus =
  | "FINISHED"
  | "IN-PROGRESS"
  | "UNFINISHED"
  | "UNFINISHED_BUT_RUNNABLE"
  | "TO-DO";

// Soft node-background colors per status, chosen to stay legible
// against the dark node text rather than to stand out.
// "UNFINISHED_BUT_RUNNABLE" (ready to be retried after a prior failure)
// gets its own orange, distinct from "UNFINISHED"'s red — it's not a
// plain failure, it's failed-but-currently-runnable.
const BACKGROUND_BY_STATUS: Record<ProcessRunStatus, string> = {
  "FINISHED": "#e8f5ea",
  "IN-PROGRESS": "#fdf6dc",
  "UNFINISHED": "#fbe9e7",
  "UNFINISHED_BUT_RUNNABLE": "#fdead6",
  "TO-DO": "#eeeeee",
};

const DEFAULT_BACKGROUND = "white";

/**
 * The node background color for a process's current status, or the
 * default (white) when the status is unknown/unavailable — e.g. no run
 * has ever happened in the output directory, or the last status poll
 * failed.
 */
export function processNodeBackground(
  status: string | undefined
): string {
  if (status && status in BACKGROUND_BY_STATUS) {
    return BACKGROUND_BY_STATUS[status as ProcessRunStatus];
  }
  return DEFAULT_BACKGROUND;
}
