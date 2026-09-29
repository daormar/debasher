// Running a resident program (see "Running a resident program" in
// doc/design_doc_webui.md): its run phase, what the exit codes of the tools
// that stop it or take a snapshot of it mean, and "Restart node".

import type { ProgramEdge } from "./edge";
import { hasSupervisor } from "./node";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

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

// "Restart node" kills the node, and the Supervisor relaunches it: it is
// offered on every node of a program with a Supervisor but the Supervisor,
// which nothing supervises. In a program without a Supervisor nothing would
// relaunch the node.
export function offersRestartNode(
  program: Pick<Program, "programType" | "processes">,
  process: ProgramProcess
): boolean {
  return program.programType === "resident" &&
    hasSupervisor(program.processes) &&
    process.nodeKind !== "Supervisor";
}

// Whether the node has a channel whose two ends are restarted together: a
// self-loop, or a channel between two tasks of the process. Only such a
// channel relies on the Supervisor to hold it while the node is down.
export function restartsWithBothEnds(edges: ProgramEdge[], processId: string): boolean {
  return edges.some(edge => edge.sourceProcessId === processId && edge.targetProcessId === processId);
}

// The warning with which "Restart node" asks for confirmation.
export function restartNodeWarning(
  process: ProgramProcess,
  losesHeldChannel: boolean
): string[] {

  const warning = [
    "The node is killed, as in a crash, and the Supervisor relaunches it: it " +
    "restarts from its last checkpoint and replays its input log, and what " +
    "its FIFOs hold is kept by the nodes at their other ends.",
  ];

  const mode = process.optionsHandler.mode;
  if (mode === "array" || mode === "generator") {
    warning.push("Every task of the node restarts, since debasher_stop stops a process as a whole.");
  }

  if (losesHeldChannel) {
    warning.push(
      "The program was launched with -no-hold-fifos, and the node has a " +
      "channel whose two ends restart together (a self-loop, or a channel " +
      "between two of its tasks): what that channel holds may be lost."
    );
  }

  warning.push(
    "A node restarted again and again before it sends a heartbeat counts for " +
    "the Supervisor as a node that crashes after every relaunch: after a few " +
    "times the Supervisor gives up on it and stops the program."
  );

  return warning;

}

// What the outcome of "Take snapshot" (debasher_snapshot_resident) means.
export function snapshotOutcome(
  exitCode: number,
  epoch: number | null,
  pendingNodes: string[]
): string {

  const round = epoch === null ? "The round" : `Round ${epoch}`;

  if (exitCode === 0) {
    return `${round} closed at every node: each one wrote a checkpoint of it ` +
      "and pruned its input log.";
  }

  if (exitCode === 2) {
    const where = pendingNodes.length > 0 ? ` at ${pendingNodes.join(", ")}` : " at some node";
    return `${round} did not close${where}, since the node is down, has ` +
      "halted or has a halt open.";
  }

  if (exitCode === 1) {
    return "No round was started: an error of usage or setup.";
  }

  return `debasher_snapshot_resident ended with exit code ${exitCode}.`;

}
