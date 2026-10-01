import { useEffect, useState, type RefObject } from "react";

import type { Program } from "../models/program";
import type { ProcessStatusesResult } from "../api/executionApi";
import {
  getProcessStatuses,
  getProgramState,
  killProgram as requestKill,
  resetOutputDir as requestOutputDirReset,
  resetProgramState as requestProgramStateReset,
  runProgram,
  stopProgram,
  checkProgramOptions as requestOptionsCheck,
  validateProgram as requestValidation,
} from "../api/executionApi";
import type { GeneralRunTracking } from "../models/generalRun";
import {
  INITIAL_GENERAL_TRACKING,
  LAUNCHED_GENERAL_TRACKING,
  generalRunPhase,
  nextGeneralTracking,
  stoppedGeneralTracking,
} from "../models/generalRun";
import type { ResidentRequest } from "../models/residentRun";
import { residentRunPhase } from "../models/residentRun";
import type { NodeNotice } from "../models/nodeState";

// How often to poll debasher_status for the process statuses, from which
// the canvas colors the nodes and the run phase is derived, in
// milliseconds. Runs continuously whenever an output directory is set,
// whoever launched the run in it.
const PROCESS_STATUS_POLL_INTERVAL_MS = 5000;

// How the store sends a request of the run that saves the program first
// (launching, validating, checking its options): it handles a revision
// conflict, which it rethrows, and takes the revision the request wrote.
export type WriteProgram = <T extends { revision: number | null }>(request: () => Promise<T>) => Promise<T>;

/**
 * The run of the program in its output directory as the tab follows it: the
 * process statuses, polled while an output directory is set, the run phase
 * derived from them and from the requests of the tab not answered yet, and
 * the requests themselves (launch, stop, kill, validate, check the options,
 * and the resets). `programRef` holds the latest program, which a poll
 * sends, and `writeProgram` sends the requests that save the program.
 */
export function useProgramRun(program: Program, programRef: RefObject<Program>, writeProgram: WriteProgram) {

  async function ensureNoRunInProgress() {

    const state = await getProgramState(program);

    if (state === "in-progress") {
      throw new Error("A run is already in progress for this output directory.");
    }

  }

  // The request of this tab to launch the program, or to stop or kill it,
  // that has not been answered yet: the run phase shows it until the answer
  // comes. Nothing that happens to the tab stops a run: it lives in its
  // output directory, whoever launched it (see "A run that outlives the tab"
  // in doc/design_doc_webui.md).
  const [runRequest, setRunRequest] =
    useState<ResidentRequest | null>(null);

  // The phase of a run of a general program as the readings of the process
  // statuses leave it (see models/generalRun.ts).
  const [generalTracking, setGeneralTracking] =
    useState<GeneralRunTracking>(INITIAL_GENERAL_TRACKING);

  // What debasher_status printed at the last reading, shown when a run did
  // not finish.
  const [statusOutput, setStatusOutput] =
    useState("");

  // Runs `action` as a request of the tab, and reads the process statuses
  // again once it is answered, so that the phase goes on to what the request
  // left without waiting for the next poll.
  async function withRunRequest<T>(
    request: ResidentRequest,
    action: () => Promise<T>
  ): Promise<T> {

    setRunRequest(request);

    try {
      const result = await action();
      await refreshProcessStatuses();
      return result;
    } finally {
      setRunRequest(null);
    }

  }

  async function startProgramRun(resumeChangedProgram = false) {

    if (program.programType === "resident") {
      return withRunRequest("launching", async () => {
        await ensureNoRunInProgress();
        return writeProgram(() => runProgram(program, resumeChangedProgram));
      });
    }

    // A general run is followed from the next poll on, not at once: the
    // first readings after a launch may still show the run before, and two
    // of them with nothing in progress end the phase "launching".
    setRunRequest("launching");

    try {
      await ensureNoRunInProgress();
      const result = await writeProgram(() => runProgram(program));
      if (result.started) {
        setGeneralTracking(LAUNCHED_GENERAL_TRACKING);
      }
      return result;
    } finally {
      setRunRequest(null);
    }

  }

  // "Validate program" and "Check program options", which save the program
  // before debasher_exec runs; each answers with what it printed.
  async function validateProgram() {
    const { output } = await writeProgram(() => requestValidation(program));
    return output;
  }

  async function checkProgramOptions() {
    const { output } = await writeProgram(() => requestOptionsCheck(program));
    return output;
  }

  function stopRun() {
    return withRunRequest("stopping", async () => {
      const result = await stopProgram(program);
      if (program.programType !== "resident") {
        setGeneralTracking(stoppedGeneralTracking);
      }
      return result;
    });
  }

  function killResidentProgram() {
    return withRunRequest("stopping", () => requestKill(program));
  }

  const [processStatuses, setProcessStatuses] =
    useState<Record<string, string>>({});

  const [hasProgramState, setHasProgramState] =
    useState(false);

  const [nodeNotices, setNodeNotices] =
    useState<NodeNotice[]>([]);

  const isRunInProgress =
    Object.values(processStatuses).includes("IN-PROGRESS");

  const residentPhase =
    residentRunPhase(processStatuses, hasProgramState, runRequest);

  const runPhase =
    generalRunPhase(generalTracking, runRequest);

  const runOutput =
    runPhase === "unfinished" ? statusOutput : null;

  function applyProcessStatuses(result: ProcessStatusesResult) {
    setProcessStatuses(result.statuses);
    setHasProgramState(result.hasProgramState);
    setNodeNotices(result.notices);
    setStatusOutput(result.output);
    setGeneralTracking(prev => nextGeneralTracking(prev, result.statuses));
  }

  async function readProcessStatuses(current: Program): Promise<ProcessStatusesResult> {
    try {
      return await getProcessStatuses(current);
    } catch {
      // Nothing to show while debasher_status can't be run (e.g. the
      // output directory hasn't been initialized by a run yet).
      return { statuses: {}, hasProgramState: false, output: "", notices: [] };
    }
  }

  // Reads the process statuses at once, besides the poll below, after a
  // request that changes them. A reading for an output directory that has
  // changed meanwhile is dropped.
  async function refreshProcessStatuses() {
    const current = programRef.current;
    if (!current.outputDir.trim()) {
      return;
    }
    const result = await readProcessStatuses(current);
    if (programRef.current.outputDir === current.outputDir) {
      applyProcessStatuses(result);
    }
  }

  useEffect(() => {

    // Another output directory holds another run.
    setGeneralTracking(INITIAL_GENERAL_TRACKING);

    if (!program.outputDir.trim()) {
      applyProcessStatuses({ statuses: {}, hasProgramState: false, output: "", notices: [] });
      return;
    }

    let cancelled = false;

    async function poll() {
      const result = await readProcessStatuses(programRef.current);
      if (!cancelled) {
        applyProcessStatuses(result);
      }
    }

    poll();
    const timer = window.setInterval(poll, PROCESS_STATUS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [program.outputDir, program.envVars.DEBASHER_MOD_DIR]);

  async function resetProgramState(deleteState: boolean) {

    // As resetOutputDir's guard below: the state of a node that runs is
    // not to be taken from under it. The tool refuses it too.
    if (isRunInProgress) {
      throw new Error(
        "Cannot reset the program state while a run is in progress. Stop the " +
        "program first."
      );
    }

    const result = await requestProgramStateReset(program, deleteState);
    await refreshProcessStatuses();
    return result;

  }

  async function resetOutputDir() {

    // Same reasoning as ProgramContext's save() guard, and kept here for the
    // same defense-in-depth reason: wiping outputDir out from under a
    // run that's actually in progress (this tab's or not, per
    // isRunInProgress) would delete files a not-yet-finished process
    // is using.
    if (isRunInProgress) {
      throw new Error(
        "Cannot reset the output directory while a run is in progress for " +
        "it. Wait for the run to finish, or stop it first."
      );
    }

    const cleared = await requestOutputDirReset(program);

    if (cleared) {
      // Don't wait for the next poll tick, every node's background
      // should go back to white as soon as the reset is confirmed.
      applyProcessStatuses({ statuses: {}, hasProgramState: false, output: "", notices: [] });
    }

    return cleared;

  }

  return {
    isRunInProgress,
    runPhase,
    runOutput,
    runEndSeen: generalTracking.sawEnd,
    processStatuses,
    nodeNotices,
    residentPhase,
    startProgramRun,
    validateProgram,
    checkProgramOptions,
    stopRun,
    killResidentProgram,
    resetOutputDir,
    resetProgramState,
  };

}
