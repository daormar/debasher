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
import type { ProgramEdge } from "../models/edge";
import { buildConnectionSentinel } from "../models/edge";
import type { Position } from "../models/position";
import { computeFlippedOptionIds, optionRow } from "../adapters/reactFlowAdapter";
import { saveProgram } from "../storage/programStorage";
import type { ProgramStatusResult } from "../api/executionApi";
import {
  fetchProgramStatus,
  getProcessStatuses,
  getProgramState,
  resetOutputDir as requestOutputDirReset,
  runProgram,
  stopProgram,
} from "../api/executionApi";

// How often to poll for a background run's completion, in milliseconds.
const RUN_POLL_INTERVAL_MS = 5000;

// Matches engine/debasher_lib.sh's DEBASHER_MOD_DIR_SEP.
const MOD_DIR_SEP = ":";

// How often to poll debasher_status for per-process node colors, in
// milliseconds. Runs continuously whenever an output directory is set,
// independently of runPhase (which only tracks runs launched from this
// UI), the output directory may hold a run that's already in
// progress from outside it.
const PROCESS_STATUS_POLL_INTERVAL_MS = 5000;

export type ProgramRunPhase = "idle" | "running" | "finished" | "unfinished";

interface ProgramContextType {
  program: Program;

  selectedProcess: ProgramProcess | null;

  selectProcess: (processId: string | null) => void;

  save: (outputDir: string) => Promise<void>;

  // True whenever processStatuses reports at least one process as
  // "IN-PROGRESS", i.e. a run is going for program.outputDir, whether
  // launched from this tab or not (unlike runPhase, which only tracks
  // a run this tab itself launched). Drives SaveDialog's proactive
  // disable, see save()'s own guard below for why saving mid-run is
  // unsafe.
  isRunInProgress: boolean;

  runPhase: ProgramRunPhase;

  // debasher_status's output from the poll that settled runPhase into
  // "unfinished" (see startRunPolling); null otherwise.
  runOutput: string | null;

  // Latest per-process statuses from debasher_status (see
  // processNodeBackground), keyed by process name. Empty whenever no
  // output directory is set or the last poll failed/had nothing to
  // report.
  processStatuses: Record<string, string>;

  // Deletes everything inside the output directory (Run menu's "Reset
  // output directory", after its confirmation modal). Resolves to
  // false when the backend's own guards made it a no-op (e.g.
  // outputDir is blank); throws on a real failure so the caller can
  // show it inline. On success, clears processStatuses immediately:
  // every node's background goes back to white right away, rather
  // than waiting for the next status poll tick.
  resetOutputDir: () => Promise<boolean>;

  // Launches "Run program" in the background; throws (e.g. if a run
  // is already in progress) rather than resolving with an error, so
  // callers can show it inline. Resolves once the run has launched,
  // not once it's finished; see runPhase for that.
  startProgramRun: () => Promise<void>;

  // The running-progress indicator's Close button: stops the run if
  // it's still going, otherwise just dismisses the finished/unfinished
  // notice.
  dismissProgramRun: () => void;

  addProcess: (name: string, info: ProcessInfo | null) => void;

  // Merges `loaded`'s processes/edges into the current program as a new
  // group (see "Add program"): every merged process is tagged with a
  // GroupSource so script_generation.py can emit a single
  // add_debasher_program call for it while the group stays intact. Fails
  // (via window.alert) instead of merging if any of `loaded`'s process
  // names collide with an existing one, they can't be deduped by
  // renaming, since add_debasher_program only knows the source module's
  // own original names.
  mergeProgram: (loaded: Program, sourceDir: string) => void;

  applyProcessInfo: (
    processId: string,
    info: ProcessInfo
  ) => void;

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

  removeProcess: (
    processId: string
  ) => void;

  moveProcess: (
    processId: string,
    position: Position
  ) => void;

  renameProcess: (
    processId: string,
    name: string
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

  disconnect: (
    edgeId: string
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

/**
 * Makes each option's `value` reflect its incoming edge (if any): connected
 * options get the "[process;option]" reference, others are cleared of any
 * stale one. Self-heals programs whose edges/values fell out of sync, e.g.
 * a file saved before this syncing existed, or a hand-edited JSON file.
 */
function normalizeConnectedOptionValues(source: Program): Program {

  const connectedValueByOptionKey = new Map<string, string>();

  for (const edge of source.edges) {

    const sourceProcess = source.processes.find(
      process => process.id === edge.sourceProcessId
    );

    const sourceOption = sourceProcess?.options.find(
      o => o.id === edge.sourceOptionId
    );

    if (sourceProcess && sourceOption) {
      connectedValueByOptionKey.set(
        `${edge.targetProcessId}:${edge.targetOptionId}`,
        buildConnectionSentinel(sourceProcess.name, sourceOption.label)
      );
    }

  }

  return {

    ...source,

    processes: source.processes.map(process => ({

      ...process,

      options: process.options.map(option => {

        // A "shared_dir" option's value is always its declared
        // directory name, independent of any connection, a connection
        // into/out of it exists purely to document the multi-writer
        // dependency in the canvas (see isValidProgramConnection), not
        // to supply its value the way a "none"-channel connection does.
        if (option.channel === "shared_dir") {
          return option;
        }

        const connectedValue =
          connectedValueByOptionKey.get(`${process.id}:${option.id}`);

        if (connectedValue !== undefined) {
          return option.value === connectedValue
            ? option
            : { ...option, value: connectedValue };
        }

        return option.value.startsWith("[") && option.value.endsWith("]")
          ? { ...option, value: "" }
          : option;

      }),

    })),

  };

}

// Matches createEmptyProgram's/program_import.py's own default.
const DEFAULT_SCHEDULER = "BUILTIN";

/**
 * Self-heals a falsy executionOptions.scheduler (e.g. a file saved
 * while it was blank, see ExecutionOptionsEditor, whose dropdown
 * defaults its *displayed* value to "BUILTIN" without ever correcting
 * a genuinely empty stored one, since Cancel is a no-op) back to a
 * valid default. Without this, debasher_exec/debasher_status get
 * "--sched ''" and fail with "Error: is not a valid scheduler" even
 * though the UI appears to show "BUILTIN" selected.
 */
function normalizeProgram(source: Program): Program {

  const normalized = normalizeConnectedOptionValues(source);

  return normalized.executionOptions.scheduler
    ? normalized
    : {
        ...normalized,
        executionOptions: {
          ...normalized.executionOptions,
          scheduler: DEFAULT_SCHEDULER,
        },
      };

}

interface Props {
  children: ReactNode;
  initialProgram: Program;
}

export function ProgramProvider({
  children,
  initialProgram,
}: Props) {

  const [program, setProgramRaw] =
    useState<Program>(() => normalizeProgram(initialProgram));

  // Re-derives every connected option's "[process;option]" value from the
  // current edges/names on every update, so renaming a process or a
  // connected option's label can't leave a stale reference behind in what
  // gets saved/generated, and re-heals executionOptions.scheduler if it's
  // ever falsy (see normalizeProgram above).
  function setProgram(updater: (current: Program) => Program) {
    setProgramRaw(current => normalizeProgram(updater(current)));
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

    const updated = { ...program, homeDir: outputDir };
    await saveProgram(updated, outputDir);
    setProgram(() => updated);
  }

  const [runPhase, setRunPhase] =
    useState<ProgramRunPhase>("idle");

  // debasher_status's output from the poll that settled runPhase into
  // "unfinished", shown alongside the run-finished notice so a
  // genuine failure can be diagnosed without a separate "Get program
  // status" call. Not meaningful (and not shown) for any other phase.
  const [runOutput, setRunOutput] =
    useState<string | null>(null);

  const pollTimerRef =
    useRef<number | null>(null);

  const beforeUnloadHandlerRef =
    useRef<(() => void) | null>(null);

  const runningProgramRef =
    useRef<Program | null>(null);

  // Mirrors runPhase for the unmount cleanup below, which, since its
  // effect has an empty dependency array and only runs once, on
  // unmount, would otherwise only ever see the phase from initial
  // mount rather than the current one.
  const runPhaseRef =
    useRef<ProgramRunPhase>(runPhase);

  useEffect(() => {
    runPhaseRef.current = runPhase;
  }, [runPhase]);

  function stopRunPolling() {

    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (beforeUnloadHandlerRef.current !== null) {
      window.removeEventListener("beforeunload", beforeUnloadHandlerRef.current);
      beforeUnloadHandlerRef.current = null;
    }

  }

  // Leaving the editor (the toolbar's "Close" button) unmounts this
  // provider without ever unloading the page, so beforeunload above
  // doesn't fire, stop a still-running program here too, or it's
  // left running with nothing left to track or stop it.
  useEffect(() => {
    return () => {
      stopRunPolling();
      if (runPhaseRef.current === "running") {
        const runningProgram = runningProgramRef.current ?? program;
        stopProgram(runningProgram).catch(() => {
          // Best-effort, the UI tracking this run is already gone.
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startRunPolling(runningProgram: Program) {

    runningProgramRef.current = runningProgram;
    setRunPhase("running");
    setRunOutput(null);

    const beforeUnloadHandler = () => {
      const blob = new Blob([JSON.stringify(runningProgram)], {
        type: "application/json",
      });
      navigator.sendBeacon("/api/execution/stop", blob);
    };

    beforeUnloadHandlerRef.current = beforeUnloadHandler;
    window.addEventListener("beforeunload", beforeUnloadHandler);

    // "unfinished" (debasher_status's neither-finished-nor-in-progress
    // exit code) is ambiguous: it also fires during an ordinary brief
    // gap between processes, the previous one's job id is already
    // gone but its completion marker, or the next one's job id, hasn't
    // landed yet, which looks identical to a genuinely finished-with-
    // failures run from a single reading. Requiring it twice in a row
    // (one poll interval apart) filters that out: a run that's still
    // actually going almost always shows "in-progress" again by the
    // next tick, while a truly finished one keeps reading "unfinished".
    let consecutiveUnfinished = 0;

    pollTimerRef.current = window.setInterval(async () => {

      let result: ProgramStatusResult;

      try {
        result = await fetchProgramStatus(runningProgram);
      } catch {
        return; // transient failure, try again next tick
      }

      if (result.state === "in-progress") {
        consecutiveUnfinished = 0;
        return;
      }

      if (result.state === "finished") {
        stopRunPolling();
        setRunPhase("finished");
        return;
      }

      consecutiveUnfinished += 1;

      if (consecutiveUnfinished >= 2) {
        stopRunPolling();
        setRunOutput(result.output);
        setRunPhase("unfinished");
      }

    }, RUN_POLL_INTERVAL_MS);

  }

  async function startProgramRun() {

    const state = await getProgramState(program);

    if (state === "in-progress") {
      throw new Error("A run is already in progress for this output directory.");
    }

    await runProgram(program);
    startRunPolling(program);

  }

  function dismissProgramRun() {

    if (runPhase === "running") {
      stopRunPolling();
      const runningProgram = runningProgramRef.current ?? program;
      stopProgram(runningProgram).catch(() => {
        // Best-effort, nothing meaningful left to show once the
        // running indicator has already been dismissed.
      });
    }

    setRunPhase("idle");
    setRunOutput(null);

  }

  const [processStatuses, setProcessStatuses] =
    useState<Record<string, string>>({});

  const isRunInProgress =
    Object.values(processStatuses).includes("IN-PROGRESS");

  // Kept in sync on every render so the status-poll effect below (which
  // only restarts when outputDir/DEBASHER_MOD_DIR change, not on every
  // program edit) always sends the current program rather than a stale
  // closure over it.
  const programRef =
    useRef(program);

  useEffect(() => {
    programRef.current = program;
  }, [program]);

  useEffect(() => {

    if (!program.outputDir.trim()) {
      setProcessStatuses({});
      return;
    }

    let cancelled = false;

    async function poll() {
      try {
        const statuses = await getProcessStatuses(programRef.current);
        if (!cancelled) {
          setProcessStatuses(statuses);
        }
      } catch {
        // Nothing to show while debasher_status can't be run (e.g. the
        // output directory hasn't been initialized by a run yet).
        if (!cancelled) {
          setProcessStatuses({});
        }
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
      setProcessStatuses({});
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

  function addProcess(name: string, info: ProcessInfo | null) {

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

    };

    setProgram(current => ({
      ...current,
      processes: [...current.processes, process],
    }));

  }

  function mergeProgram(loaded: Program, sourceDir: string) {

    const collisionName = loaded.processes.find(process =>
      program.processes.some(
        existing => existing.name.toLowerCase() === process.name.toLowerCase()
      )
    )?.name;

    if (collisionName) {
      window.alert(
        `Cannot add program "${loaded.name}": it has a process named ` +
        `"${collisionName}", which already exists in this program. Rename ` +
        `the conflicting process (in either program) and try again.`
      );
      return;
    }

    const groupId = crypto.randomUUID();

    // Places the merged batch to the right of whatever's already on the
    // canvas, preserving the relative layout its processes had in
    // `loaded`, there's no bounding-box UI to keep in sync (see
    // ProcessNode's per-group color instead), just a one-off offset at
    // merge time, same spirit as addProcess's own hardcoded position.
    const currentMaxX = program.processes.reduce(
      (max, process) => Math.max(max, process.position.x),
      0
    );

    const loadedMinX = loaded.processes.reduce(
      (min, process) => Math.min(min, process.position.x),
      Infinity
    );

    const offsetX = loadedMinX === Infinity ? 0 : currentMaxX + 250 - loadedMinX;

    const idMap = new Map<string, string>();

    // Names are kept exactly as in `loaded` (checked above), renaming a
    // merged process's own name would desync it from the
    // add_debasher_program call, which internally re-declares each
    // process under its original name.
    const mergedProcesses: ProgramProcess[] = loaded.processes.map(process => {

      const id = crypto.randomUUID();
      idMap.set(process.id, id);

      return {
        ...process,
        id,
        position: {
          x: process.position.x + offsetX,
          y: process.position.y,
        },
        groupSource: {
          programName: loaded.name,
          groupId,
          groupSize: loaded.processes.length,
          sourceDir,
        },
      };

    });

    const mergedEdges: ProgramEdge[] = loaded.edges.map(edge => ({
      ...edge,
      id: crypto.randomUUID(),
      sourceProcessId: idMap.get(edge.sourceProcessId) ?? edge.sourceProcessId,
      targetProcessId: idMap.get(edge.targetProcessId) ?? edge.targetProcessId,
    }));

    setProgram(current => {

      const modDirEntries = (current.envVars.DEBASHER_MOD_DIR ?? "")
        .split(MOD_DIR_SEP)
        .map(entry => entry.trim())
        .filter(Boolean);

      const envVars = modDirEntries.includes(sourceDir)
        ? current.envVars
        : {
            ...current.envVars,
            DEBASHER_MOD_DIR: [...modDirEntries, sourceDir].join(MOD_DIR_SEP),
          };

      return {
        ...current,
        processes: [...current.processes, ...mergedProcesses],
        edges: [...current.edges, ...mergedEdges],
        envVars,
      };

    });

  }

  // A process tagged with GroupSource ("Add program") represents a
  // process add_debasher_program will re-declare, unmodified, from its
  // source module. Anything that changes that process's own definition
  //, or which edges target it, since a connected option's
  // define_opt_from_proc_out call lives in the *target*'s own generated
  // function (see api/script_generation.py's _option_definition_line)
  //, would silently get overwritten by that re-declaration once
  // generated. So any such change first confirms detaching the whole
  // group (stripping groupSource from every process sharing its
  // groupId, not just this one) with the user, and is aborted if
  // declined. Connecting/disconnecting an edge whose target ISN'T
  // grouped stays free even when its source is (see connect/disconnect)
  //, that only touches the (ungrouped) target's own function.
  function confirmDetachIfGrouped(processId: string): boolean {

    const groupSource = program.processes.find(
      process => process.id === processId
    )?.groupSource;

    if (!groupSource) {
      return true;
    }

    const confirmed = window.confirm(
      `This process was added from program "${groupSource.programName}" via ` +
      `"Add program". Changing it here will disconnect the whole group from ` +
      `that program: it will stop being generated as ` +
      `add_debasher_program "${groupSource.programName}" and each of its ` +
      `processes will be generated on its own instead. Continue?`
    );

    if (!confirmed) {
      return false;
    }

    setProgram(current => ({
      ...current,
      processes: current.processes.map(process =>
        process.groupSource?.groupId === groupSource.groupId
          ? { ...process, groupSource: undefined }
          : process
      ),
    }));

    return true;

  }

  function applyProcessInfo(
    processId: string,
    info: ProcessInfo
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? {
              ...process,
              description: info.description,
              options: info.options.map(toProgramOption),
              language: info.language,
              code: info.code,
            }
          : process
      ),

    }));

  }

  function setName(
    name: string
  ) {

    setProgram(current => ({
      ...current,
      name,
    }));

  }

  function setDescription(
    description: string
  ) {

    setProgram(current => ({
      ...current,
      description,
    }));

  }

  function setPreamble(
    preamble: string
  ) {

    setProgram(current => ({
      ...current,
      preamble,
    }));

  }

  function setSharedDirs(
    sharedDirs: string[]
  ) {

    setProgram(current => ({
      ...current,
      sharedDirs,
    }));

  }

  function setEnvVar(
    name: string,
    value: string
  ) {

    setProgram(current => ({
      ...current,
      envVars: { ...current.envVars, [name]: value },
    }));

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

    setProgram(current => ({
      ...current,
      outputDir,
    }));

  }

  function setExecutionOptions(
    executionOptions: ExecutionOptions
  ) {

    setProgram(current => ({
      ...current,
      executionOptions,
    }));

  }

  function setProgramOptions(
    programOptions: Record<string, string>
  ) {

    setProgram(current => ({
      ...current,
      programOptions,
    }));

  }

  function removeProcess(
    processId: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.filter(
        process => process.id !== processId
      ),

      // Drop any edges left dangling by the removed process.
      edges: current.edges.filter(
        edge =>
          edge.sourceProcessId !== processId &&
          edge.targetProcessId !== processId
      ),

    }));

    setSelectedProcessId(current =>
      current === processId ? null : current
    );

  }

  function moveProcess(
    processId: string,
    position: Position
  ) {

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, position }
          : process
      ),

    }));

  }

  function renameProcess(
    processId: string,
    name: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, name }
          : process
      ),

    }));

  }

  function setProcessDescription(
    processId: string,
    description: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, description }
          : process
      ),

    }));

  }

  function setProcessLanguage(
    processId: string,
    language: ProcessLanguage
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, language }
          : process
      ),

    }));

  }

  function setProcessCode(
    processId: string,
    code: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, code }
          : process
      ),

    }));

  }

  function setComputationalSpecs(
    processId: string,
    computationalSpecs: ComputationalSpecs
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, computationalSpecs }
          : process
      ),

    }));

  }

  function setAdditionalSpecs(
    processId: string,
    additionalSpecs: AdditionalSpecs
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, additionalSpecs }
          : process
      ),

    }));

  }

  function setOptionsHandler(
    processId: string,
    optionsHandler: OptionsHandler
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, optionsHandler }
          : process
      ),

    }));

  }

  function setAdditionalMethods(
    processId: string,
    additionalMethods: AdditionalMethods
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, additionalMethods }
          : process
      ),

    }));

  }

  function addOption(
    processId: string,
    label: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

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

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? {
              ...process,
              options: [
                ...process.options,
                option,
              ],
            }
          : process
      ),

    }));

  }

  function updateOption(
    processId: string,
    optionId: string,
    changes: Partial<Omit<ProgramOption, "id">>
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? {
              ...process,
              options: process.options.map(o =>
                o.id === optionId
                  ? { ...o, ...changes }
                  : o
              ),
            }
          : process
      ),

    }));

  }

  function removeOption(
    processId: string,
    optionId: string
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? {
              ...process,
              options: process.options.filter(
                o => o.id !== optionId
              ),
            }
          : process
      ),

    }));

  }

  function reorderOptionGroup(
    processId: string,
    row: "top" | "bottom",
    orderedIds: string[]
  ) {

    if (!confirmDetachIfGrouped(processId)) {
      return;
    }

    setProgram(current => {

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

  function setOptionValue(
    processes: ProgramProcess[],
    processId: string,
    optionId: string,
    value: string
  ): ProgramProcess[] {

    return processes.map(process =>
      process.id === processId
        ? {
            ...process,
            options: process.options.map(o =>
              o.id === optionId
                ? { ...o, value }
                : o
            ),
          }
        : process
    );

  }

  function setOptionSharedDir(
    processes: ProgramProcess[],
    processId: string,
    optionId: string,
    sharedDirName: string
  ): ProgramProcess[] {

    return processes.map(process =>
      process.id === processId
        ? {
            ...process,
            options: process.options.map(o =>
              o.id === optionId
                ? { ...o, channel: "shared_dir" as const, value: sharedDirName }
                : o
            ),
          }
        : process
    );

  }

  function connect(
    edge: ProgramEdge
  ) {

    // Only the *target*'s own generated function embeds the connection
    // (see confirmDetachIfGrouped), a grouped process's output feeding
    // something new outside the group stays free, since that's encoded
    // in the (ungrouped) target's function instead.
    if (!confirmDetachIfGrouped(edge.targetProcessId)) {
      return;
    }

    setProgram(current => {

      const sourceProcess = current.processes.find(
        process => process.id === edge.sourceProcessId
      );

      const sourceOption = sourceProcess?.options.find(
        o => o.id === edge.sourceOptionId
      );

      // A "shared_dir" source's channel/value already fully determines
      // its resolved path, connecting it into a plain target promotes
      // that target into a matching "shared_dir" option too, instead
      // of the usual "[proc;option]" sentinel, so a second connection
      // from another writer of the same directory validates against an
      // already-tagged, matching target (see isValidProgramConnection)
      // and both keep generating the same compact
      // get_absolute_shdirname-based code (see script_generation.py's
      // shared_dir branch) rather than one becoming a
      // define_opt_from_proc_out reference to this specific source.
      const processes = sourceProcess && sourceOption
        ? sourceOption.channel === "shared_dir"
          ? setOptionSharedDir(
              current.processes,
              edge.targetProcessId,
              edge.targetOptionId,
              sourceOption.value
            )
          : setOptionValue(
              current.processes,
              edge.targetProcessId,
              edge.targetOptionId,
              buildConnectionSentinel(sourceProcess.name, sourceOption.label)
            )
        : current.processes;

      return {
        ...current,
        processes,
        edges: [
          ...current.edges,
          edge,
        ],
      };

    });

  }

  function disconnect(
    edgeId: string
  ) {

    const targetProcessId = program.edges.find(
      e => e.id === edgeId
    )?.targetProcessId;

    if (targetProcessId && !confirmDetachIfGrouped(targetProcessId)) {
      return;
    }

    setProgram(current => {

      const removedEdge = current.edges.find(
        e => e.id === edgeId
      );

      const targetOption = removedEdge && current.processes
        .find(process => process.id === removedEdge.targetProcessId)
        ?.options.find(o => o.id === removedEdge.targetOptionId);

      // A "shared_dir" option's value is independent of any connection
      // (see connect above), removing an edge into one shouldn't
      // clear its declared directory name.
      const processes = removedEdge && targetOption?.channel !== "shared_dir"
        ? setOptionValue(
            current.processes,
            removedEdge.targetProcessId,
            removedEdge.targetOptionId,
            ""
          )
        : current.processes;

      return {
        ...current,
        processes,
        edges: current.edges.filter(
          e => e.id !== edgeId
        ),
      };

    });

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

    resetOutputDir,

    startProgramRun,

    dismissProgramRun,

    addProcess,

    mergeProgram,

    applyProcessInfo,

    setName,

    setDescription,

    setPreamble,

    setSharedDirs,

    setEnvVar,

    setOutputDir,

    setExecutionOptions,

    setProgramOptions,

    removeProcess,

    moveProcess,

    renameProcess,

    setProcessDescription,

    setProcessLanguage,

    setProcessCode,

    setComputationalSpecs,

    setAdditionalSpecs,

    setOptionsHandler,

    setAdditionalMethods,

    addOption,

    updateOption,

    removeOption,

    reorderOptionGroup,

    connect,

    disconnect,

  }), [
    program,
    selectedProcess,
    runPhase,
    runOutput,
    processStatuses,
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
