import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { ExecutionOptions, Program } from "../models/program";
import type {
  ProgramProcess,
  ProcessLanguage,
  ComputationalSpecs,
  AdditionalSpecs,
  OptionsHandler,
  AdditionalMethods,
  ProcessInfo,
  ProcessInfoOption,
} from "../models/process";
import { DEFAULT_COMPUTATIONAL_SPECS } from "../models/process";
import type { ProgramOption } from "../models/option";
import { getOptionDirection } from "../models/option";
import * as edits from "../models/programEdits";
import type { ProgramEdge } from "../models/edge";
import type { SeqProcess } from "../models/seqProcess";
import type { Position } from "../models/position";
import type { NodeCode, NodeInfo, NodeKind } from "../models/node";
import { emptyNodeCode } from "../models/node";
import { computeFlippedOptionIds, optionRow } from "../adapters/reactFlowAdapter";
import { saveProgram } from "../storage/programStorage";
import type {
  ProcessStatusesResult,
  ResetProgramStateResult,
  RunProgramResult,
  StopResult,
} from "../api/executionApi";
import {
  getProcessStatuses,
  getProgramState,
  killProgram as requestKill,
  resetOutputDir as requestOutputDirReset,
  resetProgramState as requestProgramStateReset,
  runProgram,
  stopProgram,
} from "../api/executionApi";
import type { GeneralRunPhase, GeneralRunTracking } from "../models/generalRun";
import {
  INITIAL_GENERAL_TRACKING,
  LAUNCHED_GENERAL_TRACKING,
  generalRunPhase,
  nextGeneralTracking,
  stoppedGeneralTracking,
} from "../models/generalRun";
import type { ResidentRequest, ResidentRunPhase } from "../models/residentRun";
import { residentRunPhase } from "../models/residentRun";
import type { NodeNotice } from "../models/nodeState";

// How often to poll debasher_status for the process statuses, from which
// the canvas colors the nodes and the run phase is derived, in
// milliseconds. Runs continuously whenever an output directory is set,
// whoever launched the run in it.
const PROCESS_STATUS_POLL_INTERVAL_MS = 5000;

export type ProgramRunPhase = GeneralRunPhase;

interface ProgramContextType {
  program: Program;

  selectedProcess: ProgramProcess | null;

  selectProcess: (processId: string | null) => void;

  save: (outputDir: string) => Promise<void>;

  // True whenever processStatuses reports at least one process as
  // "IN-PROGRESS", i.e. a run is going for program.outputDir, whether
  // launched from this tab or not. Drives SaveDialog's proactive
  // disable, see save()'s own guard below for why saving mid-run is
  // unsafe.
  isRunInProgress: boolean;

  // The run phase of a general program, derived from the process statuses,
  // whoever launched the run, and from a request of this tab not answered
  // yet (see models/generalRun.ts). Meaningless for a resident program,
  // which has residentPhase.
  runPhase: ProgramRunPhase;

  // Whether this tab saw the run end, going to "finished" or "unfinished"
  // from "launching" or "running": only then is the end shown.
  runEndSeen: boolean;

  // debasher_status's output from the last reading, while runPhase is
  // "unfinished"; null otherwise.
  runOutput: string | null;

  // Latest per-process statuses from debasher_status (see
  // processNodeBackground), keyed by process name. Empty whenever no
  // output directory is set or the last poll failed/had nothing to
  // report.
  processStatuses: Record<string, string>;

  // The notices of the nodes of a resident program, read with the process
  // statuses; empty otherwise.
  nodeNotices: NodeNotice[];

  // Deletes everything inside the output directory (Run menu's "Reset
  // output directory", after its confirmation modal). Resolves to
  // false when the backend's own guards made it a no-op (e.g.
  // outputDir is blank); throws on a real failure so the caller can
  // show it inline. On success, clears processStatuses immediately:
  // every node's background goes back to white right away, rather
  // than waiting for the next status poll tick.
  resetOutputDir: () => Promise<boolean>;

  // "Reset program state" on a resident program (the run menu's, in place
  // of "Reset output directory"): sets the program state aside, or deletes
  // it with `deleteState`, and reads the process statuses again, so that the
  // run phase goes to "new" at once. Throws while a run is in progress.
  resetProgramState: (deleteState: boolean) => Promise<ResetProgramStateResult>;

  // Launches "Run program"; throws (e.g. if a run is already in
  // progress) rather than resolving with an error, so callers can show
  // it inline. Resolves once the run has launched, not once it's
  // finished; see runPhase and residentPhase for that. A launch that
  // the backend waits for (a resident program, or Slurm) resolves with
  // the exit code of debasher_exec and what it printed;
  // `resumeChangedProgram` resumes the program state of a resident
  // program with a program that differs from the launch record (see
  // runProgram). Nothing that happens to the tab stops the run.
  startProgramRun: (resumeChangedProgram?: boolean) => Promise<RunProgramResult>;

  // The run phase of a resident program, derived from processStatuses,
  // from whether the output directory holds program state, and from a
  // request of this tab not answered yet (see models/residentRun.ts).
  // Meaningless for a general program.
  residentPhase: ResidentRunPhase;

  // "Stop program": debasher_stop on a general program, and the orderly stop
  // on a resident one, which resolves once the program has stopped, with
  // the exit code of the tool. "Kill program": the hard kill of a resident
  // program. Both show the run phase "stopping" meanwhile, and throw on a
  // failed request.
  stopRun: () => Promise<StopResult>;

  killResidentProgram: () => Promise<StopResult>;

  // In a resident program `nodeKind` is the node kind of the new process,
  // chosen when it is added: a node is written in Python, in the parts of
  // NodeCode, and a Supervisor has no code of its own. `nodeInfo`, for a
  // node that a module of the preamble defines, brings its description,
  // code, options and options handler.
  addProcess: (name: string, info: ProcessInfo | null, nodeKind?: NodeKind, nodeInfo?: NodeInfo) => void;

  // "Add program": brings the processes, sequential processes and edges of
  // `loaded`, read from `sourceDir`, into the current program (see
  // edits.prepareMerge), or tells the user with window.alert why it can't
  // (see edits.mergeRefusal).
  mergeProgram: (loaded: Program, sourceDir: string) => void;

  setName: (
    name: string
  ) => void;

  setDescription: (
    description: string
  ) => void;

  setPreamble: (
    preamble: string
  ) => void;

  setSharedDirs: (
    sharedDirs: string[]
  ) => void;

  // Replaces the sequential processes of the program. When the change
  // edits or removes a sequential process of a group ("Add program"), it
  // first asks to dissolve the group, as a change to a process of the group
  // does, and changes nothing if the user declines. Returns whether the
  // sequential processes were replaced.
  setSeqProcesses: (
    seqProcesses: SeqProcess[]
  ) => boolean;

  setEnvVar: (
    name: string,
    value: string
  ) => void;

  setOutputDir: (
    outputDir: string
  ) => void;

  setExecutionOptions: (
    executionOptions: ExecutionOptions
  ) => void;

  setProgramOptions: (
    programOptions: Record<string, string>
  ) => void;

  // Removes the processes and edges deleted together on the canvas, with a
  // single confirmation for the groups they touch. Returns whether they
  // were removed, so the canvas keeps them when the user declines.
  removeFromCanvas: (
    processIds: string[],
    edgeIds: string[]
  ) => boolean;

  moveProcess: (
    processId: string,
    position: Position
  ) => void;

  // Renames the process and, when `info` is given, replaces its
  // description, options, language and code with what the library brings
  // for the new name.
  renameProcess: (
    processId: string,
    name: string,
    info?: ProcessInfo | null
  ) => void;

  setProcessDescription: (
    processId: string,
    description: string
  ) => void;

  setProcessLanguage: (
    processId: string,
    language: ProcessLanguage
  ) => void;

  setProcessCode: (
    processId: string,
    code: string
  ) => void;

  setNodeCode: (
    processId: string,
    nodeCode: NodeCode
  ) => void;

  setInitiator: (
    processId: string,
    initiator: boolean
  ) => void;

  setComputationalSpecs: (
    processId: string,
    specs: ComputationalSpecs
  ) => void;

  setAdditionalSpecs: (
    processId: string,
    specs: AdditionalSpecs
  ) => void;

  setOptionsHandler: (
    processId: string,
    optionsHandler: OptionsHandler
  ) => void;

  setAdditionalMethods: (
    processId: string,
    additionalMethods: AdditionalMethods
  ) => void;

  addOption: (
    processId: string,
    label: string
  ) => void;

  updateOption: (
    processId: string,
    optionId: string,
    changes: Partial<Omit<ProgramOption, "id">>
  ) => void;

  removeOption: (
    processId: string,
    optionId: string
  ) => void;

  reorderOptionGroup: (
    processId: string,
    row: "top" | "bottom",
    orderedIds: string[]
  ) => void;

  connect: (
    edge: ProgramEdge
  ) => void;

}

function toProgramOption(info: ProcessInfoOption): ProgramOption {
  return {
    id: crypto.randomUUID(),
    direction: getOptionDirection(info.label),
    label: info.label,
    dataType: info.dataType,
    channel: "none",
    mirror: false,
    description: info.description,
    value: "",
    commandLine: info.commandLine,
    mandatory: info.mandatory,
    fromProcessSpec: false,
  };
}

const ProgramContext =
  createContext<ProgramContextType | null>(null);

interface Props {
  children: ReactNode;
  initialProgram: Program;
}

export function ProgramProvider({
  children,
  initialProgram,
}: Props) {

  const [program, setProgramRaw] =
    useState<Program>(() => edits.normalizeProgram(initialProgram));

  // The latest program, ahead of `program` until React renders again:
  // every edit applies to it, so that several edits within one event (or
  // an edit after an await) build on each other, and what an edit
  // decides from the program (whether it touches a group, see
  // editProcesses) is never decided from a stale render. The status poll
  // below reads it too, to send the current program.
  const programRef =
    useRef(program);

  // Every edit is followed by normalizeProgram, which keeps the references
  // of the connected options in step with the edges and names.
  function setProgram(updater: (current: Program) => Program) {
    const next = edits.normalizeProgram(updater(programRef.current));
    programRef.current = next;
    setProgramRaw(next);
  }

  async function save(outputDir: string) {

    // Saving regenerates the .sh script in homeDir (see
    // persistence.save_script), but engine/debasher_exec_process
    // reloads that same file from disk each time a process starts,
    // not just once when the run launches. Overwriting it while a run
    // is in progress can leave already-started processes on the old
    // script and not-yet-started ones silently picking up the new one:
    // a single run mixing two versions, with nothing to flag it. Kept
    // here (not just as SaveDialog's proactive disable) so any other
    // future caller of save() gets the same protection.
    if (isRunInProgress) {
      throw new Error(
        "Cannot save while a run is in progress for this program's output " +
        "directory: it would overwrite the script that not-yet-started " +
        "processes read from disk when they start. Wait for the run to " +
        "finish, or stop it first."
      );
    }

    // homeDir (the .sh/.debasher directory being saved to) and outputDir
    // (where a run writes its results) must stay distinct, otherwise a
    // run would mix engine-internal files into the saved program, and
    // "Reset output directory" would delete it. Kept here (not just as
    // SaveDialog's proactive disable) so any other future caller of
    // save() gets the same protection; the backend enforces this too.
    if (program.outputDir.trim() && outputDir.trim() === program.outputDir.trim()) {
      throw new Error(
        "The save directory can't be the same as this program's output " +
        "directory (Run menu > Set output directory)."
      );
    }

    await saveProgram({ ...program, homeDir: outputDir }, outputDir);
    // Only homeDir is taken from the saved copy: the user may have kept
    // editing while the request was in flight, and putting the copy back
    // whole would silently drop those edits.
    setProgram(current => ({ ...current, homeDir: outputDir }));
  }

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
        return runProgram(program, resumeChangedProgram);
      });
    }

    // A general run is followed from the next poll on, not at once: the
    // first readings after a launch may still show the run before, and two
    // of them with nothing in progress end the phase "launching".
    setRunRequest("launching");

    try {
      await ensureNoRunInProgress();
      const result = await runProgram(program);
      if (result.started) {
        setGeneralTracking(LAUNCHED_GENERAL_TRACKING);
      }
      return result;
    } finally {
      setRunRequest(null);
    }

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

    // Same reasoning as save()'s guard above, and kept here for the
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

  const [selectedProcessId, setSelectedProcessId] =
    useState<string | null>(null);

  function selectProcess(
    processId: string | null
  ) {
    setSelectedProcessId(processId);
  }

  function addProcess(name: string, info: ProcessInfo | null, nodeKind?: NodeKind, nodeInfo?: NodeInfo) {

    const nodeFields: Partial<ProgramProcess> = nodeInfo
      ? {
          nodeKind: nodeInfo.nodeKind,
          initiator: false,
          nodeCode: nodeInfo.nodeCode,
          language: "python",
          description: nodeInfo.description,
          options: nodeInfo.options,
          optionsHandler: nodeInfo.optionsHandler,
        }
      : nodeKind
        ? {
            nodeKind,
            initiator: false,
            nodeCode: nodeKind === "Supervisor" ? undefined : emptyNodeCode(),
            language: "python",
          }
        : {};

    const process: ProgramProcess = {

      id: crypto.randomUUID(),

      name,

      description: info?.description ?? "",

      position: {
        x: 100,
        y: 100,
      },

      options: info ? info.options.map(toProgramOption) : [],

      optionsHandler: {
        mode: "standard",
      },

      language: info?.language ?? "bash",

      code: info?.code ?? "",

      computationalSpecs: { ...DEFAULT_COMPUTATIONAL_SPECS },

      additionalSpecs: {
        force: false,
      },

      additionalMethods: {},

      ...nodeFields,

    };

    setProgram(current => edits.addProcess(current, process));

  }

  function mergeProgram(loaded: Program, sourceDir: string) {

    const refusal = edits.mergeRefusal(programRef.current, loaded);

    if (refusal) {
      window.alert(refusal);
      return;
    }

    const group = edits.prepareMerge(programRef.current, loaded, sourceDir, () => crypto.randomUUID());

    setProgram(current => edits.addGroup(current, group));

  }

  // A process tagged with GroupSource ("Add program") represents a
  // process add_debasher_program will re-declare, unmodified, from its
  // source module, so an edit that would be overwritten by that
  // re-declaration first asks the user, once for all the groups it
  // touches (see edits.groupsOfProcesses), and either dissolves them
  // together with the edit or, if the user declines, leaves the program
  // as it was. Returns whether the edit was applied.
  function editTouchingGroups(
    groups: edits.TouchedGroups,
    edit: (current: Program) => Program
  ): boolean {

    if (groups.size > 0) {
      const programNames = [...new Set(groups.values())].join('", "');
      const confirmed = window.confirm(
        `This changes what was added from program "${programNames}" via ` +
        `"Add program". Changing it here will disconnect the whole group ` +
        `from that program: it will stop being generated as ` +
        `add_debasher_program and each of its processes and sequential ` +
        `processes will be generated on its own instead. Continue?`
      );
      if (!confirmed) {
        return false;
      }
    }

    setProgram(current => edit(edits.dissolveGroups(current, new Set(groups.keys()))));

    return true;

  }

  // An edit of the definition of the given processes (see
  // editTouchingGroups).
  function editProcesses(
    processIds: string[],
    edit: (current: Program) => Program
  ): boolean {
    return editTouchingGroups(edits.groupsOfProcesses(programRef.current, processIds), edit);
  }

  function setName(
    name: string
  ) {

    setProgram(current => edits.setProgramFields(current, { name }));

  }

  function setDescription(
    description: string
  ) {

    setProgram(current => edits.setProgramFields(current, { description }));

  }

  function setPreamble(
    preamble: string
  ) {

    setProgram(current => edits.setProgramFields(current, { preamble }));

  }

  function setSeqProcesses(
    seqProcesses: SeqProcess[]
  ): boolean {

    return editTouchingGroups(
      edits.groupsOfChangedSeqProcesses(programRef.current, seqProcesses),
      current => ({ ...current, seqProcesses })
    );

  }

  function setSharedDirs(
    sharedDirs: string[]
  ) {

    setProgram(current => edits.setProgramFields(current, { sharedDirs }));

  }

  function setEnvVar(
    name: string,
    value: string
  ) {

    setProgram(current => edits.setEnvVar(current, name, value));

  }

  function setOutputDir(
    outputDir: string
  ) {

    // Changing outputDir while a run is going for the current one
    // would silently redirect isRunInProgress itself, plus "Stop
    // program"/"Get program status" (which act on the live `program`,
    // not a snapshot), to a different directory than the one the
    // run actually uses, making the run invisible and unstoppable
    // from this UI. Same defense-in-depth spot as save()/
    // resetOutputDir() above.
    if (isRunInProgress) {
      throw new Error(
        "Cannot change the output directory while a run is in progress " +
        "for it. Wait for the run to finish, or stop it first."
      );
    }

    setProgram(current => edits.setProgramFields(current, { outputDir }));

  }

  function setExecutionOptions(
    executionOptions: ExecutionOptions
  ) {

    setProgram(current => edits.setProgramFields(current, { executionOptions }));

  }

  function setProgramOptions(
    programOptions: Record<string, string>
  ) {

    setProgram(current => edits.setProgramFields(current, { programOptions }));

  }

  // Removes the processes and edges deleted together on the canvas, asking
  // once for all the groups they touch (see editTouchingGroups). Returns
  // whether they were removed.
  function removeFromCanvas(
    processIds: string[],
    edgeIds: string[]
  ): boolean {

    const current = programRef.current;
    const groups = new Map([
      ...edits.groupsOfProcesses(current, processIds),
      ...edits.groupsOfEdgeTargets(current, edgeIds),
    ]);

    const removed = editTouchingGroups(groups, program =>
      processIds.reduce(
        (edited, processId) => edits.removeProcess(edited, processId),
        edgeIds.reduce((edited, edgeId) => edits.disconnect(edited, edgeId), program)
      )
    );

    if (removed) {
      setSelectedProcessId(selected =>
        selected !== null && processIds.includes(selected) ? null : selected
      );
    }

    return removed;

  }

  // The position is not part of what add_debasher_program declares, so
  // moving a process of a group leaves the group as it is.
  function moveProcess(
    processId: string,
    position: Position
  ) {

    setProgram(current => edits.updateProcess(current, processId, { position }));

  }

  function renameProcess(
    processId: string,
    name: string,
    info?: ProcessInfo | null
  ) {

    const options = info?.options.map(toProgramOption);

    editProcesses([processId], current => edits.updateProcess(current, processId, {
      name,
      ...(info && {
        description: info.description,
        options,
        language: info.language,
        code: info.code,
      }),
    }));

  }

  function setProcessDescription(
    processId: string,
    description: string
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { description }));

  }

  function setProcessLanguage(
    processId: string,
    language: ProcessLanguage
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { language }));

  }

  function setProcessCode(
    processId: string,
    code: string
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { code }));

  }

  // A node and its initiator flag exist only in a resident program, which
  // has no groups (see mergeProgram), so neither setter asks.
  function setNodeCode(
    processId: string,
    nodeCode: NodeCode
  ) {

    setProgram(current => edits.updateProcess(current, processId, { nodeCode }));

  }

  function setInitiator(
    processId: string,
    initiator: boolean
  ) {

    setProgram(current => edits.updateProcess(current, processId, { initiator }));

  }

  function setComputationalSpecs(
    processId: string,
    computationalSpecs: ComputationalSpecs
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { computationalSpecs }));

  }

  function setAdditionalSpecs(
    processId: string,
    additionalSpecs: AdditionalSpecs
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { additionalSpecs }));

  }

  function setOptionsHandler(
    processId: string,
    optionsHandler: OptionsHandler
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { optionsHandler }));

  }

  function setAdditionalMethods(
    processId: string,
    additionalMethods: AdditionalMethods
  ) {

    editProcesses([processId], current => edits.updateProcess(current, processId, { additionalMethods }));

  }

  function addOption(
    processId: string,
    label: string
  ) {

    const option: ProgramOption = {

      id: crypto.randomUUID(),

      direction: getOptionDirection(label),

      label,

      dataType: "string",

      channel: "none",

      mirror: false,

      description: "",

      value: "",

      commandLine: false,

      mandatory: false,

      fromProcessSpec: false,

    };

    editProcesses([processId], current => edits.addOption(current, processId, option));

  }

  function updateOption(
    processId: string,
    optionId: string,
    changes: Partial<Omit<ProgramOption, "id">>
  ) {

    editProcesses([processId], current => edits.updateOption(current, processId, optionId, changes));

  }

  function removeOption(
    processId: string,
    optionId: string
  ) {

    editProcesses([processId], current => edits.removeOption(current, processId, optionId));

  }

  function reorderOptionGroup(
    processId: string,
    row: "top" | "bottom",
    orderedIds: string[]
  ) {

    editProcesses([processId], current => {

      const flippedOptionIds = computeFlippedOptionIds(current);

      return {

        ...current,

        processes: current.processes.map(process => {

          if (process.id !== processId) {
            return process;
          }

          const groupIndices = process.options.reduce<number[]>(
            (indices, o, i) =>
              optionRow(o, flippedOptionIds) === row
                ? [...indices, i]
                : indices,
            []
          );

          if (groupIndices.length !== orderedIds.length) {
            return process;
          }

          const optionsById = new Map(
            process.options.map(o => [o.id, o])
          );

          const options = [...process.options];

          groupIndices.forEach((index, i) => {

            const option = optionsById.get(orderedIds[i]);

            if (option) {
              options[index] = option;
            }

          });

          return { ...process, options };

        }),

      };

    });

  }

  function connect(
    edge: ProgramEdge
  ) {

    editProcesses([edge.targetProcessId], current => edits.connect(current, edge));

  }

  const selectedProcess =
    program.processes.find(
      p => p.id === selectedProcessId
    ) ?? null;

  const value = useMemo(() => ({

    program,

    selectedProcess,

    selectProcess,

    save,

    isRunInProgress,

    runPhase,

    runOutput,

    processStatuses,

    nodeNotices,

    resetOutputDir,

    resetProgramState,

    startProgramRun,

    runEndSeen: generalTracking.sawEnd,

    residentPhase,

    stopRun,

    killResidentProgram,

    addProcess,

    mergeProgram,


    setName,

    setDescription,

    setPreamble,

    setSharedDirs,

    setSeqProcesses,

    setEnvVar,

    setOutputDir,

    setExecutionOptions,

    setProgramOptions,

    removeFromCanvas,

    moveProcess,

    renameProcess,

    setProcessDescription,

    setProcessLanguage,

    setProcessCode,

    setNodeCode,

    setInitiator,

    setComputationalSpecs,

    setAdditionalSpecs,

    setOptionsHandler,

    setAdditionalMethods,

    addOption,

    updateOption,

    removeOption,

    reorderOptionGroup,

    connect,


  }), [
    program,
    selectedProcess,
    runPhase,
    runOutput,
    generalTracking.sawEnd,
    processStatuses,
    nodeNotices,
    residentPhase,
  ]);

  return (
    <ProgramContext.Provider
      value={value}
    >
      {children}
    </ProgramContext.Provider>
  );

}

export function useProgram() {

  const context =
    useContext(ProgramContext);

  if (!context) {

    throw new Error(
      "useProgram must be used inside ProgramProvider."
    );

  }

  return context;

}
