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
  ProcessInfo,
  ProcessInfoOption,
} from "../models/process";
import { DEFAULT_COMPUTATIONAL_SPECS } from "../models/process";
import type { ProgramOption, OptionDirection } from "../models/option";
import { getOptionDirection } from "../models/option";
import type { ProgramEdge } from "../models/edge";
import { buildConnectionSentinel } from "../models/edge";
import type { Position } from "../models/position";
import { saveProgram } from "../storage/programStorage";
import type { ProgramState } from "../api/executionApi";
import {
  getProgramState,
  runProgram,
  stopProgram,
} from "../api/executionApi";

// How often to poll for a background run's completion, in milliseconds.
const RUN_POLL_INTERVAL_MS = 5000;

export type ProgramRunPhase = "idle" | "running" | "finished" | "unfinished";

interface ProgramContextType {
  program: Program;

  selectedProcess: ProgramProcess | null;

  selectProcess: (processId: string | null) => void;

  save: (outputDir: string) => Promise<void>;

  runPhase: ProgramRunPhase;

  // Launches "Run program" in the background; throws (e.g. if a run
  // is already in progress) rather than resolving with an error, so
  // callers can show it inline. Resolves once the run has launched —
  // not once it's finished, see runPhase for that.
  startProgramRun: () => Promise<void>;

  // The running-progress indicator's Close button: stops the run if
  // it's still going, otherwise just dismisses the finished/unfinished
  // notice.
  dismissProgramRun: () => void;

  addProcess: (name: string, info: ProcessInfo | null) => void;

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
    direction: OptionDirection,
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
    description: info.description,
    value: "",
    commandLine: info.commandLine,
    mandatory: info.mandatory,
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

interface Props {
  children: ReactNode;
  initialProgram: Program;
}

export function ProgramProvider({
  children,
  initialProgram,
}: Props) {

  const [program, setProgramRaw] =
    useState<Program>(() => normalizeConnectedOptionValues(initialProgram));

  // Re-derives every connected option's "[process;option]" value from the
  // current edges/names on every update, so renaming a process or a
  // connected option's label can't leave a stale reference behind in what
  // gets saved/generated (see normalizeConnectedOptionValues above).
  function setProgram(updater: (current: Program) => Program) {
    setProgramRaw(current => normalizeConnectedOptionValues(updater(current)));
  }

  async function save(outputDir: string) {
    const updated = { ...program, homeDir: outputDir };
    await saveProgram(updated, outputDir);
    setProgram(() => updated);
  }

  const [runPhase, setRunPhase] =
    useState<ProgramRunPhase>("idle");

  const pollTimerRef =
    useRef<number | null>(null);

  const beforeUnloadHandlerRef =
    useRef<(() => void) | null>(null);

  const runningProgramRef =
    useRef<Program | null>(null);

  // Mirrors runPhase for the unmount cleanup below, which — since its
  // effect has an empty dependency array and only runs once, on
  // unmount — would otherwise only ever see the phase from initial
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
  // doesn't fire — stop a still-running program here too, or it's
  // left running with nothing left to track or stop it.
  useEffect(() => {
    return () => {
      stopRunPolling();
      if (runPhaseRef.current === "running") {
        const runningProgram = runningProgramRef.current ?? program;
        stopProgram(runningProgram).catch(() => {
          // Best-effort — the UI tracking this run is already gone.
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startRunPolling(runningProgram: Program) {

    runningProgramRef.current = runningProgram;
    setRunPhase("running");

    const beforeUnloadHandler = () => {
      const blob = new Blob([JSON.stringify(runningProgram)], {
        type: "application/json",
      });
      navigator.sendBeacon("/api/execution/stop", blob);
    };

    beforeUnloadHandlerRef.current = beforeUnloadHandler;
    window.addEventListener("beforeunload", beforeUnloadHandler);

    pollTimerRef.current = window.setInterval(async () => {

      let state: ProgramState;

      try {
        state = await getProgramState(runningProgram);
      } catch {
        return; // transient failure — try again next tick
      }

      if (state !== "in-progress") {
        stopRunPolling();
        setRunPhase(state === "finished" ? "finished" : "unfinished");
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
        // Best-effort — nothing meaningful left to show once the
        // running indicator has already been dismissed.
      });
    }

    setRunPhase("idle");

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

    };

    setProgram(current => ({
      ...current,
      processes: [...current.processes, process],
    }));

  }

  function applyProcessInfo(
    processId: string,
    info: ProcessInfo
  ) {

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

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? { ...process, optionsHandler }
          : process
      ),

    }));

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

      description: "",

      value: "",

      commandLine: false,

      mandatory: false,

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
    direction: OptionDirection,
    orderedIds: string[]
  ) {

    setProgram(current => ({

      ...current,

      processes: current.processes.map(process => {

        if (process.id !== processId) {
          return process;
        }

        const groupIndices = process.options.reduce<number[]>(
          (indices, o, i) =>
            o.direction === direction
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

    }));

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

  function connect(
    edge: ProgramEdge
  ) {

    setProgram(current => {

      const sourceProcess = current.processes.find(
        process => process.id === edge.sourceProcessId
      );

      const sourceOption = sourceProcess?.options.find(
        o => o.id === edge.sourceOptionId
      );

      const processes = sourceProcess && sourceOption
        ? setOptionValue(
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

    setProgram(current => {

      const removedEdge = current.edges.find(
        e => e.id === edgeId
      );

      const processes = removedEdge
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

    runPhase,

    startProgramRun,

    dismissProgramRun,

    addProcess,

    applyProcessInfo,

    setName,

    setDescription,

    setPreamble,

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
