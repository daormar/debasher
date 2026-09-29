// Running a resident program (see "Running a resident program" in
// doc/design_doc_webui.md): its run phase and what the exit codes of the
// tools that stop it mean.

// The run phase of a resident program. Unlike the run phase of a general
// program, it does not follow a run of this tab: it is derived from the
// process statuses, read whoever launched the program, and from whether the
// output directory holds program state. Only "launching" and "stopping" come
// from this tab: a request to launch the program, or to stop or kill it,
// that has not been answered yet.
export type ResidentRunPhase = "new" | "live" | "stopped" | "launching" | "stopping";

export type ResidentRequest = "launching" | "stopping";

export function residentRunPhase(
  statuses: Record<string, string>,
  hasProgramState: boolean,
  request: ResidentRequest | null
): ResidentRunPhase {

  if (request !== null) {
    return request;
  }

  if (Object.values(statuses).includes("IN-PROGRESS")) {
    return "live";
  }

  return hasProgramState ? "stopped" : "new";

}

// Whether a stopped program stopped in order, every process of it having
// finished, rather than abruptly: after a hard kill, a Supervisor that gave up
// on a node, or a node that failed in a program without a Supervisor.
export function stoppedInOrder(statuses: Record<string, string>): boolean {
  const values = Object.values(statuses);
  return values.length > 0 && values.every(status => status === "FINISHED");
}

// What a hard kill leaves, said both when the user is asked to confirm
// "Kill program" and when an orderly stop falls back to it.
export const HARD_KILL_CONSEQUENCES =
  "Each node resumes from its last checkpoint and its input log, and what " +
  "the FIFOs held may be lost, at most what a pipe holds for each business " +
  "channel, which the nodes that read them report as a gap in the sequence " +
  "numbers when they resume.";

// What the exit code of debasher_stop_resident means, for "Stop program".
export function orderlyStopOutcome(exitCode: number | null): string {

  if (exitCode === 0) {
    return "Stopped in order. Every node halted in the same round, and the " +
      "next launch resumes the program with nothing lost.";
  }

  if (exitCode === 2) {
    return "The orderly stop did not end within the timeout, and fell back " +
      "to the hard kill of debasher_stop. The program has ended, but was " +
      "killed. " + HARD_KILL_CONSEQUENCES;
  }

  if (exitCode === 1) {
    return "The program could not be stopped: an error of usage or setup.";
  }

  return `debasher_stop_resident ended with exit code ${exitCode}.`;

}
