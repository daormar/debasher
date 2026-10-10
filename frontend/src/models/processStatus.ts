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

/**
 * The status of a process of a resident program as the canvas shows it:
 * UNFINISHED_BUT_RUNNABLE is shown as UNFINISHED, since in a resident program
 * no process waits to be run later.
 */
export function residentProcessStatus(
  status: string | undefined
): string | undefined {
  return status === "UNFINISHED_BUT_RUNNABLE" ? "UNFINISHED" : status;
}

// What each process status means in a general program, as the legend of the
// canvas says it (see "Process status" in doc/design_doc_engine.md).
export const GENERAL_STATUS_MEANINGS: { status: ProcessRunStatus; meaning: string }[] = [
  { status: "IN-PROGRESS", meaning: "some task still runs" },
  { status: "FINISHED", meaning: "every task ended well or was skipped" },
  { status: "UNFINISHED", meaning: "launched or cancelled, nothing runs, and some task did not end well" },
  { status: "UNFINISHED_BUT_RUNNABLE", meaning: "an array stopped partway; the next run launches the tasks left" },
  { status: "TO-DO", meaning: "nothing launched or cancelled yet" },
];

// What each process status means in a resident program, as the legend of the
// canvas says it.
export const RESIDENT_STATUS_MEANINGS: { status: ProcessRunStatus; meaning: string }[] = [
  { status: "IN-PROGRESS", meaning: "alive, also after a halt, until stopped" },
  { status: "FINISHED", meaning: "ended cleanly, by an orderly stop" },
  { status: "UNFINISHED", meaning: "down; if the program is not live, stopped abruptly" },
  { status: "TO-DO", meaning: "not launched" },
];
