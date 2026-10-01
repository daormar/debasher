import type { InspectNodeCommand, NodeNotice } from "../models/nodeState";
import type { Program } from "../models/program";
import type { ResidentFifoRead, TalkMode } from "../models/residentTalk";

// FastAPI's default error body is `{"detail": "..."}`. Prefer that
// message when present, otherwise fall back to a generic one.
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON — fall through to the fallback message.
  }

  return fallback;
}

export async function listSchedulers(): Promise<string[]> {
  const response = await fetch("/api/execution/schedulers");

  if (!response.ok) {
    throw new Error(`Failed to list schedulers (${response.status})`);
  }

  const { schedulers } = await response.json();
  return schedulers;
}

export interface RunProgramResult {
  started: boolean;
  // Only for a resident program, whose launch the backend waits for: the
  // exit code of debasher_exec and what it printed. Null for a general
  // program.
  exitCode: number | null;
  output: string | null;
}

// /run refused to resume the program state of a resident program, since the
// program differs from the launch record, or there is none: the user has to
// choose between resuming with the changed program and starting afresh.
export class LaunchRecordConflict extends Error {
  readonly hasLaunchRecord: boolean;

  constructor(hasLaunchRecord: boolean) {
    super("The program state in the output directory was produced by another program.");
    this.hasLaunchRecord = hasLaunchRecord;
  }
}

// Launches the run of a general program in the background and returns as
// soon as it's started: it does not wait for the program to finish. Poll
// getProgramState() to find out when it's done. The launch of a resident
// program is waited for, and returns once debasher_exec has launched every
// process, or failed to; `resumeChangedProgram` says that the user chose to
// resume the program state with a program that differs from the launch
// record, which /run refuses otherwise with a LaunchRecordConflict.
export async function runProgram(
  program: Program,
  resumeChangedProgram = false
): Promise<RunProgramResult> {
  const query = resumeChangedProgram ? "?resumeChangedProgram=true" : "";
  const response = await fetch(`/api/execution/run${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (response.status === 409) {
    const body = await response.clone().json().catch(() => null);
    if (body?.detail?.code === "launch-record") {
      throw new LaunchRecordConflict(Boolean(body.detail.hasLaunchRecord));
    }
  }

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to run program (${response.status})`)
    );
  }

  const { started, exitCode, output } = await response.json();
  return { started, exitCode: exitCode ?? null, output: output ?? null };
}

export interface LaunchCheckResult {
  hasProgramState: boolean;
  hasLaunchRecord: boolean;
  // There is program state, and no launch record or one that differs from
  // the program: "Run program" asks before launching.
  needsConfirmation: boolean;
}

export async function checkLaunch(program: Program): Promise<LaunchCheckResult> {
  const response = await fetch("/api/execution/launch-check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to check the launch (${response.status})`));
  }

  return response.json();
}

// "Validate program" (debasher_exec --validate): everything but launching
// the processes, and, with the built-in scheduler, the resources of each
// process against its limits.
export async function validateProgram(program: Program): Promise<string> {
  const response = await fetch("/api/execution/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to validate the program (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

export type ProgramState = "finished" | "in-progress" | "unfinished";

export interface ProgramStatusResult {
  output: string;
  state: ProgramState;
}

// Exported (not just used internally by getProgramStatus/getProgramState
// below) so the run-completion poll in useProgramRun can get both the
// state and the debasher_status output from one call, to show the
// latter alongside an "unfinished" run-finished notice.
export async function fetchProgramStatus(program: Program): Promise<ProgramStatusResult> {
  const response = await fetch("/api/execution/status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to get program status (${response.status})`);
  }

  return response.json();
}

export async function getProgramStatus(program: Program): Promise<string> {
  const { output } = await fetchProgramStatus(program);
  return output;
}

// Cheap check of whether a run is still going, backed by the same
// debasher_status call as getProgramStatus() — used to poll a
// background run and to guard against launching a second one.
export async function getProgramState(program: Program): Promise<ProgramState> {
  const { state } = await fetchProgramStatus(program);
  return state;
}

export interface ProcessStatusesResult {
  // Per-process statuses as reported by debasher_status (e.g. "FINISHED",
  // "IN-PROGRESS", "UNFINISHED", "UNFINISHED_BUT_RUNNABLE", "TO-DO"),
  // keyed by process name.
  statuses: Record<string, string>;
  // Only for a resident program: whether its output directory holds
  // program state, which the next launch resumes. False otherwise.
  hasProgramState: boolean;
  // What debasher_status printed, shown when a run did not finish.
  output: string;
  // Only for a resident program: the notices of its nodes.
  notices: NodeNotice[];
}

// Used to color nodes in the canvas, see useProgramRun's status polling
// and ProcessNode's use of it, and to derive the run phase of a resident
// program.
export async function getProcessStatuses(program: Program): Promise<ProcessStatusesResult> {
  const response = await fetch("/api/execution/process-statuses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to get process statuses (${response.status})`);
  }

  const { statuses, hasProgramState, output, notices } = await response.json();
  return { statuses, hasProgramState: hasProgramState ?? false, output: output ?? "", notices: notices ?? [] };
}

async function fetchProcessOutput(
  endpoint: string,
  program: Program,
  processName: string,
  taskIndex: number | undefined,
  fallback: string,
  extra: Record<string, unknown> = {}
): Promise<string> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, taskIndex, ...extra }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, fallback));
  }

  const { output } = await response.json();
  return output;
}

// A process's captured stdout (the canvas's right-click "Inspect
// execution" menu's "Show stdout"). `taskIndex` selects one task's
// file for a process that ran as more than one task — see
// getProcessTasks — and is omitted for a "standard" one-file process.
export async function getProcessStdout(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/process-stdout",
    program,
    processName,
    taskIndex,
    `Failed to get stdout for ${processName}.`
  );
}

// A process's scheduler output (the canvas's right-click "Inspect
// execution" menu's "Show scheduler output"). See getProcessStdout
// for `taskIndex`.
export async function getProcessSchedOut(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/process-sched-out",
    program,
    processName,
    taskIndex,
    `Failed to get scheduler output for ${processName}.`
  );
}

// A process's resolved command-line options (the canvas's right-click
// "Inspect execution" menu's "Show options"). See getProcessStdout for
// `taskIndex`.
export async function getProcessOpts(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/process-opts",
    program,
    processName,
    taskIndex,
    `Failed to get options for ${processName}.`
  );
}

// A mirrored output fifo's captured content (the canvas's right-click
// "Watch FIFO" action) — see api/routers/execution.py's /fifo-mirror.
// `fifoName` is the fifo's name as given to define_fifo_opt (the
// mirrored option's own `value`, per ProgramOption.mirror). See
// getProcessStdout for `taskIndex`.
export async function getFifoMirror(
  program: Program,
  processName: string,
  fifoName: string,
  taskIndex?: number
): Promise<string> {
  return fetchProcessOutput(
    "/api/execution/fifo-mirror",
    program,
    processName,
    taskIndex,
    `Failed to get mirrored fifo output for ${processName}.`,
    { fifoName }
  );
}

// Writes one line to an unconnected input fifo (the "Talk to FIFOs"
// action) — see api/routers/execution.py's /fifo-write. `fifoName` is
// the fifo's name as given to define_fifo_opt, not the option's label.
// Never throws for an ordinary failure (no reader connected, fifo not
// ready yet) — that comes back as `{ ok: false, error }` so the caller
// can show it inline instead of via a thrown Error.
export async function writeFifo(
  program: Program,
  processName: string,
  fifoName: string,
  text: string
): Promise<{ ok: boolean; error?: string }> {
  const response = await fetch("/api/execution/fifo-write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, fifoName, text }),
  });

  if (!response.ok) {
    return { ok: false, error: await errorDetail(response, `Failed to write to ${fifoName}.`) };
  }

  return response.json();
}

// Reads one line from an unconnected output fifo (the "Talk to FIFOs"
// action) — see api/routers/execution.py's /fifo-read, which blocks
// server-side for a short bounded time. `timedOut: true` means nothing
// arrived within that window — the expected, common case while
// waiting for a response — not an error; the caller just calls again.
// `signal` lets the caller abort an in-flight call (e.g. the dialog
// closing) via AbortController.
export async function readFifo(
  program: Program,
  processName: string,
  fifoName: string,
  signal?: AbortSignal
): Promise<{ line?: string; timedOut?: boolean; error?: string }> {
  const response = await fetch("/api/execution/fifo-read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, fifoName }),
    signal,
  });

  if (!response.ok) {
    return { error: await errorDetail(response, `Failed to read from ${fifoName}.`) };
  }

  return response.json();
}

// Writes one message into an external input of a resident program ("Talk
// to FIFOs"): the backend wraps the payload in a DATA envelope and writes it
// as one line, whole or not at all. In JSON mode `text` is any JSON value; in
// text mode it is sent as a string.
export async function writeResidentFifo(
  program: Program,
  processName: string,
  fifoName: string,
  text: string,
  mode: TalkMode
): Promise<{ ok: boolean; error?: string }> {
  const response = await fetch("/api/execution/resident-fifo-write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, fifoName, text, mode }),
  });

  if (!response.ok) {
    return { ok: false, error: await errorDetail(response, `Failed to write to ${fifoName}.`) };
  }

  return response.json();
}

// Reads the next envelope from a business output with no reader of a
// resident program ("Talk to FIFOs"), skipping blank lines and HELLO. It
// takes the message from the channel. `timedOut: true` means nothing arrived
// within the backend's short bound: the caller reads again.
export async function readResidentFifo(
  program: Program,
  processName: string,
  fifoName: string
): Promise<ResidentFifoRead> {
  const response = await fetch("/api/execution/resident-fifo-read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, fifoName }),
  });

  if (!response.ok) {
    return { error: await errorDetail(response, `Failed to read from ${fifoName}.`) };
  }

  return response.json();
}

// An {label: resolved value} map for a process's command-line options,
// parsed from its ".opts" file (the canvas's right-click "Inspect
// execution" menu's "Show inputs and outputs") — empty when the
// program hasn't been run yet. See getProcessStdout for `taskIndex`.
export async function getProcessResolvedOptions(
  program: Program,
  processName: string,
  taskIndex?: number
): Promise<Record<string, string>> {
  const response = await fetch("/api/execution/process-resolved-options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, taskIndex }),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to get resolved options for ${processName}.`)
    );
  }

  const { values } = await response.json();
  return values;
}

// What a node of a resident program keeps in its execdir, or the batch runs
// of a launcher node, read by debasher_inspect_resident for "Show node
// state" and "Show batch runs": what the tool printed, parsed, or the error
// it reported (a node that keeps no node state, a checkpoint that the node
// no longer retains).
export async function inspectNode<T>(
  program: Program,
  processName: string,
  taskIndex: number | undefined,
  command: InspectNodeCommand
): Promise<{ result: T | null; error: string | null }> {
  const response = await fetch("/api/execution/inspect-node", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName, taskIndex, ...command }),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to inspect node ${processName}.`)
    );
  }

  return response.json();
}

// What debasher_status says of the run directory of a batch run of a
// launcher node that is a whole general program, for "Show batch runs".
export async function getBatchRunStatus(program: Program, runDir: string): Promise<string> {
  const response = await fetch("/api/execution/batch-run-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, runDir }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to get the status of ${runDir}.`));
  }

  const { output } = await response.json();
  return output;
}

export type PathInspection =
  | { kind: "file"; content: string }
  | { kind: "binary" }
  | { kind: "directory"; entries: string[] }
  | { kind: "missing" };

// Inspects a resolved option's value as a filesystem path — a file's
// content, or a directory's listing — for the "Show inputs and
// outputs" modal's per-option "View" button.
export async function inspectPath(path: string): Promise<PathInspection> {
  const response = await fetch("/api/execution/inspect-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to inspect ${path}.`));
  }

  return response.json();
}

// What an inspected path shows as text: a file's content, a directory's
// listing, or why neither is shown.
export function pathInspectionText(path: string, result: PathInspection): string {
  return result.kind === "file"
    ? result.content
    : result.kind === "directory"
      ? (result.entries.length > 0 ? result.entries.join("\n") : "(empty directory)")
      : result.kind === "binary"
        ? `Warning: ${path} looks like a binary file. Content not shown.`
        : `Path not found: ${path}`;
}

// The task indices that have a stdout, scheduler-output, or options
// file for `processName` — empty for a "standard" one-task process,
// otherwise the "Inspect execution" menu shows a task picker before
// fetching either output (see ProcessTaskPicker). Not necessarily contiguous,
// and can run into the thousands for a large array/generator, so this
// is the one place that count is dealt with — everything downstream
// just gets a plain number to pass back as taskIndex.
export async function getProcessTasks(
  program: Program,
  processName: string
): Promise<number[]> {
  const response = await fetch("/api/execution/process-tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName }),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to list tasks for ${processName}.`)
    );
  }

  const { taskIndices } = await response.json();
  return taskIndices;
}

export async function checkProgramOptions(program: Program): Promise<string> {
  const response = await fetch("/api/execution/check-program-options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to check program options (${response.status})`);
  }

  const { output } = await response.json();
  return output;
}

// Deletes everything inside program.outputDir. Resolves to false
// (rather than throwing) when the backend's own guards made it a
// no-op — e.g. outputDir is blank — so the caller can tell the user
// there was nothing to reset.
export async function resetOutputDir(program: Program): Promise<boolean> {
  const response = await fetch("/api/execution/reset-output-dir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to reset output directory (${response.status})`)
    );
  }

  const { cleared } = await response.json();
  return cleared;
}

export interface ResetProgramStateResult {
  output: string;
  exitCode: number;
}

// "Reset program state" on a resident program (debasher_reset_resident):
// sets the program state aside under __reset__/<timestamp>/ in the output
// directory, or deletes it with `deleteState`.
export async function resetProgramState(
  program: Program,
  deleteState: boolean
): Promise<ResetProgramStateResult> {
  const response = await fetch("/api/execution/reset-program-state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, delete: deleteState }),
  });

  if (!response.ok) {
    throw new Error(
      await errorDetail(response, `Failed to reset the program state (${response.status})`)
    );
  }

  return response.json();
}


export interface StopResult {
  output: string;
  exitCode: number | null;
}

async function postStop(endpoint: string, program: Program, fallback: string): Promise<StopResult> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `${fallback} (${response.status})`));
  }

  const { output, exitCode } = await response.json();
  return { output, exitCode: exitCode ?? null };
}

// "Stop program": debasher_stop on a general program, and the orderly stop
// of a resident program (debasher_stop_resident), which resolves once the
// program has stopped, up to about the timeout of the tool: exit code 0 for
// an orderly stop, 2 for one that fell back to the hard kill, 1 for an error
// of usage or setup.
export async function stopProgram(program: Program): Promise<StopResult> {
  return postStop("/api/execution/stop", program, "Failed to stop program");
}

// The hard kill of a resident program (debasher_stop).
export async function killProgram(program: Program): Promise<StopResult> {
  return postStop("/api/execution/kill", program, "Failed to kill program");
}

export interface RelaunchResult {
  output: string;
  exitCode: number;
  // The tasks that the web UI relaunched, as <process> or <process>:<idx>.
  relaunched: string[];
}

async function postNodeAction(
  endpoint: string,
  program: Program,
  processName: string,
  fallback: string
): Promise<RelaunchResult> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `${fallback} (${response.status})`));
  }

  const { output, exitCode, relaunched } = await response.json();
  return { output, exitCode, relaunched: relaunched ?? [] };
}

// "Restart node" on a node of a resident program (debasher_stop -p): a crash
// of the node, which the Supervisor relaunches, or the backend in a program
// without a Supervisor.
export async function restartNode(program: Program, processName: string): Promise<RelaunchResult> {
  return postNodeAction("/api/execution/restart-node", program, processName, "Failed to restart node");
}

// "Relaunch node" in a resident program without a Supervisor: relaunches the
// tasks of the node that are down.
export async function relaunchNode(program: Program, processName: string): Promise<RelaunchResult> {
  return postNodeAction("/api/execution/relaunch-node", program, processName, "Failed to relaunch node");
}

export interface SnapshotResult {
  output: string;
  // 0 a round that closed at every node, 2 one that did not close at some
  // node, 1 an error of usage or setup.
  exitCode: number;
  epoch: number | null;
  // With exit code 2, the nodes at which the round did not close.
  pendingNodes: string[];
}

// "Take snapshot" (debasher_snapshot_resident): starts one round and
// resolves once it has closed at every node, or its timeout has passed.
export async function takeSnapshot(program: Program): Promise<SnapshotResult> {
  const response = await fetch("/api/execution/snapshot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to take a snapshot (${response.status})`));
  }

  const { output, exitCode, epoch, pendingNodes } = await response.json();
  return { output, exitCode, epoch: epoch ?? null, pendingNodes: pendingNodes ?? [] };
}

// Whether the Supervisor of the live program was launched with
// -no-hold-fifos, as the options it was given say.
export async function launchedWithNoHoldFifos(program: Program): Promise<boolean> {
  const response = await fetch("/api/execution/launched-with-no-hold-fifos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(program),
  });

  if (!response.ok) {
    throw new Error(`Failed to read the launch options (${response.status})`);
  }

  const { launchedWithNoHoldFifos } = await response.json();
  return launchedWithNoHoldFifos;
}

// Stop a single process (the canvas's right-click "Stop process"
// action), see api/routers/execution.py's /stop-process.
export async function stopProcess(program: Program, processName: string): Promise<string> {
  const response = await fetch("/api/execution/stop-process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ program, processName }),
  });

  if (!response.ok) {
    throw new Error(await errorDetail(response, `Failed to stop process ${processName}.`));
  }

  const { output } = await response.json();
  return output;
}
