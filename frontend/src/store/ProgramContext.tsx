import {
  createContext,
  useContext,
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
} from "../models/process";
import { createProcess, optionFromInfo } from "../models/process";
import type { ProgramOption } from "../models/option";
import { createOption } from "../models/option";
import * as edits from "../models/programEdits";
import type { ProgramEdge } from "../models/edge";
import type { SeqProcess } from "../models/seqProcess";
import type { Position } from "../models/position";
import type { NodeCode, NodeInfo, NodeKind } from "../models/node";
import { reorderOptionRow } from "../models/optionLayout";
import { saveProgram } from "../storage/programStorage";
import type {
  ResetProgramStateResult,
  RunProgramResult,
  StopResult,
} from "../api/executionApi";
import type { GeneralRunPhase } from "../models/generalRun";
import type { ResidentRunPhase } from "../models/residentRun";
import type { NodeNotice } from "../models/nodeState";
import { useProgramRun } from "./useProgramRun";

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
  // decides from the program (whether it touches a group, see edit) is
  // never decided from a stale render. The status poll of useProgramRun
  // reads it too, to send the current program.
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

  const {
    isRunInProgress,
    runPhase,
    runOutput,
    runEndSeen,
    processStatuses,
    nodeNotices,
    residentPhase,
    startProgramRun,
    stopRun,
    killResidentProgram,
    resetOutputDir,
    resetProgramState,
  } = useProgramRun(program, programRef);

  const [selectedProcessId, setSelectedProcessId] =
    useState<string | null>(null);

  function selectProcess(
    processId: string | null
  ) {
    setSelectedProcessId(processId);
  }

  const newId = () => crypto.randomUUID();

  // A process tagged with GroupSource ("Add program") represents a
  // process add_debasher_program will re-declare, unmodified, from its
  // source module, so edits that would be overwritten by that
  // re-declaration first ask the user, once for all the groups they
  // touch (see edits.groupsTouchedBy), and are then applied together with
  // the dissolution of those groups or, if the user declines, not at all.
  // Returns whether the edits were applied.
  function edit(...ops: edits.EditOp[]): boolean {

    const groups = edits.groupsTouchedBy(programRef.current, ops);

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

    setProgram(current => ops.reduce(
      (edited, op) => edits.applyEdit(edited, op),
      edits.dissolveGroups(current, new Set(groups.keys()))
    ));

    return true;

  }

  function addProcess(name: string, info: ProcessInfo | null, nodeKind?: NodeKind, nodeInfo?: NodeInfo) {
    edit({ op: "addProcess", process: createProcess(newId(), name, { info, nodeKind, nodeInfo }, newId) });
  }

  function mergeProgram(loaded: Program, sourceDir: string) {

    const refusal = edits.mergeRefusal(programRef.current, loaded);

    if (refusal) {
      window.alert(refusal);
      return;
    }

    edit({ op: "addGroup", group: edits.prepareMerge(programRef.current, loaded, sourceDir, newId) });

  }

  function setProgramFields(changes: edits.ProgramFields) {
    edit({ op: "setProgramFields", changes });
  }

  function setName(name: string) {
    setProgramFields({ name });
  }

  function setDescription(description: string) {
    setProgramFields({ description });
  }

  function setPreamble(preamble: string) {
    setProgramFields({ preamble });
  }

  function setSeqProcesses(seqProcesses: SeqProcess[]): boolean {
    return edit({ op: "setSeqProcesses", seqProcesses });
  }

  function setSharedDirs(sharedDirs: string[]) {
    setProgramFields({ sharedDirs });
  }

  function setEnvVar(name: string, value: string) {
    edit({ op: "setEnvVar", name, value });
  }

  function setOutputDir(outputDir: string) {

    // Changing outputDir while a run is going for the current one
    // would silently redirect isRunInProgress itself, plus "Stop
    // program"/"Get program status" (which act on the live `program`,
    // not a snapshot), to a different directory than the one the
    // run actually uses, making the run invisible and unstoppable
    // from this UI. Same defense-in-depth spot as save() above and
    // useProgramRun's resetOutputDir().
    if (isRunInProgress) {
      throw new Error(
        "Cannot change the output directory while a run is in progress " +
        "for it. Wait for the run to finish, or stop it first."
      );
    }

    setProgramFields({ outputDir });

  }

  function setExecutionOptions(executionOptions: ExecutionOptions) {
    setProgramFields({ executionOptions });
  }

  function setProgramOptions(programOptions: Record<string, string>) {
    setProgramFields({ programOptions });
  }

  // Removes the processes and edges deleted together on the canvas, with
  // one confirmation for the groups they touch (see edit). Returns whether
  // they were removed.
  function removeFromCanvas(processIds: string[], edgeIds: string[]): boolean {

    const removed = edit(
      ...edgeIds.map(edgeId => ({ op: "disconnect", edgeId }) as const),
      ...processIds.map(processId => ({ op: "removeProcess", processId }) as const)
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
  function moveProcess(processId: string, position: Position) {
    edit({ op: "moveProcess", processId, position });
  }

  function updateProcess(processId: string, changes: edits.ProcessChanges) {
    edit({ op: "updateProcess", processId, changes });
  }

  function renameProcess(processId: string, name: string, info?: ProcessInfo | null) {
    updateProcess(processId, {
      name,
      ...(info && {
        description: info.description,
        options: info.options.map(option => optionFromInfo(option, newId())),
        language: info.language,
        code: info.code,
      }),
    });
  }

  function setProcessDescription(processId: string, description: string) {
    updateProcess(processId, { description });
  }

  function setProcessLanguage(processId: string, language: ProcessLanguage) {
    updateProcess(processId, { language });
  }

  function setProcessCode(processId: string, code: string) {
    updateProcess(processId, { code });
  }

  function setNodeCode(processId: string, nodeCode: NodeCode) {
    updateProcess(processId, { nodeCode });
  }

  function setInitiator(processId: string, initiator: boolean) {
    updateProcess(processId, { initiator });
  }

  function setComputationalSpecs(processId: string, computationalSpecs: ComputationalSpecs) {
    updateProcess(processId, { computationalSpecs });
  }

  function setAdditionalSpecs(processId: string, additionalSpecs: AdditionalSpecs) {
    updateProcess(processId, { additionalSpecs });
  }

  function setOptionsHandler(processId: string, optionsHandler: OptionsHandler) {
    updateProcess(processId, { optionsHandler });
  }

  function setAdditionalMethods(processId: string, additionalMethods: AdditionalMethods) {
    updateProcess(processId, { additionalMethods });
  }

  function addOption(processId: string, label: string) {
    edit({ op: "addOption", processId, option: createOption(newId(), label) });
  }

  function updateOption(processId: string, optionId: string, changes: edits.OptionChanges) {
    edit({ op: "updateOption", processId, optionId, changes });
  }

  function removeOption(processId: string, optionId: string) {
    edit({ op: "removeOption", processId, optionId });
  }

  // Reorders the options drawn in one row of the process node (see
  // reorderOptionRow).
  function reorderOptionGroup(processId: string, row: "top" | "bottom", orderedIds: string[]) {

    const options = reorderOptionRow(programRef.current, processId, row, orderedIds);

    if (options) {
      updateProcess(processId, { options });
    }

  }

  function connect(edge: ProgramEdge) {
    edit({ op: "connect", edge });
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

    runEndSeen,

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
    runEndSeen,
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
