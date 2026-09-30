// The run phase of a general program (see "Following a run" in
// doc/design_doc_webui.md), derived from the process statuses of each
// reading, whoever launched the run, and from the requests of the tab not
// answered yet.

export type GeneralRunPhase =
  | "idle"
  | "running"
  | "finished"
  | "unfinished"
  | "launching"
  | "stopping";

// What the readings leave: the phase they derive, and what the next reading
// needs to know.
export interface GeneralRunTracking {
  phase: Exclude<GeneralRunPhase, "stopping">;
  // Readings in a row with no process in progress.
  quietReadings: number;
  // Whether the tab saw the run end, going from "launching" or "running" to
  // "finished" or "unfinished": only then is the end shown.
  sawEnd: boolean;
}

export const INITIAL_GENERAL_TRACKING: GeneralRunTracking = {
  phase: "idle",
  quietReadings: 0,
  sawEnd: false,
};

// A launch of the tab has started a run: "launching" until the first reading
// that shows a process in progress, or two readings with none, when the run
// ended or failed at once. Until then a reading may still show the statuses
// of the run before.
export const LAUNCHED_GENERAL_TRACKING: GeneralRunTracking = {
  phase: "launching",
  quietReadings: 0,
  sawEnd: false,
};

// How many readings in a row with no process in progress it takes to say that
// a run did not finish: a single one also happens in the short gap between
// one process ending and the next starting.
const QUIET_READINGS = 2;

// A stop of the tab has been answered: the next reading with no process in
// progress settles the phase, since no next process is about to start.
export function stoppedGeneralTracking(prev: GeneralRunTracking): GeneralRunTracking {
  return { ...prev, quietReadings: QUIET_READINGS - 1 };
}

function settledPhase(statuses: Record<string, string>): GeneralRunTracking["phase"] {
  const values = Object.values(statuses);
  if (values.length === 0) {
    return "idle";
  }
  return values.every(status => status === "FINISHED") ? "finished" : "unfinished";
}

export function nextGeneralTracking(
  prev: GeneralRunTracking,
  statuses: Record<string, string>
): GeneralRunTracking {

  if (Object.values(statuses).includes("IN-PROGRESS")) {
    return { phase: "running", quietReadings: 0, sawEnd: false };
  }

  const quietReadings = prev.quietReadings + 1;
  const settled = settledPhase(statuses);
  const following = prev.phase === "launching" || prev.phase === "running";

  // A launch waits for two quiet readings whatever they show; any other
  // phase waits for them only to say "unfinished".
  const waits = prev.phase === "launching" || settled === "unfinished";
  if (waits && quietReadings < QUIET_READINGS) {
    return { ...prev, quietReadings };
  }

  const sawEnd = following
    ? settled !== "idle"
    : prev.sawEnd && settled === prev.phase;

  return { phase: settled, quietReadings, sawEnd };

}

// The run phase that the tab shows: a request not answered yet first.
export function generalRunPhase(
  tracking: GeneralRunTracking,
  request: "launching" | "stopping" | null
): GeneralRunPhase {
  return request ?? tracking.phase;
}

// Whether the indicator of the run is shown: while the run is launched, runs
// or is stopped, and at its end only when the tab saw it end, so that a
// program opened with the results of an old run shows none.
export function showsGeneralIndicator(phase: GeneralRunPhase, sawEnd: boolean): boolean {
  if (phase === "launching" || phase === "running" || phase === "stopping") {
    return true;
  }
  return (phase === "finished" || phase === "unfinished") && sawEnd;
}

// The message shown when leaving the editor while there is a run in progress,
// which blocks nothing: the run goes on in its output directory, and this is
// the only moment at which the web UI can say where it lives. Null when there
// is no run in progress.
export function runGoesOnMessage(
  program: { name: string; outputDir: string; programType: "general" | "resident" },
  isRunInProgress: boolean
): string | null {

  if (!isRunInProgress) {
    return null;
  }

  return program.programType === "resident"
    ? `${program.name} is live in ${program.outputDir}. Load the program ` +
      "again to observe it or stop it."
    : `The run of ${program.name} goes on in ${program.outputDir}. Load the ` +
      "program again to follow it or stop it.";

}
