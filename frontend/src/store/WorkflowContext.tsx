import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { ExecutionOptions, Workflow } from "../models/workflow";
import type {
  WorkflowProcess,
  ProcessLanguage,
  ComputationalSpecs,
  AdditionalSpecs,
  OptionsHandler,
  ProcessInfo,
  ProcessInfoOption,
} from "../models/process";
import { DEFAULT_COMPUTATIONAL_SPECS } from "../models/process";
import type { WorkflowOption } from "../models/option";
import { getOptionDirection } from "../models/option";
import type { WorkflowEdge } from "../models/edge";
import type { Position } from "../models/position";
import { saveWorkflow } from "../storage/workflowStorage";
import type { WorkflowState } from "../api/executionApi";
import {
  getWorkflowState,
  runWorkflow,
  stopWorkflow,
} from "../api/executionApi";

// How often to poll for a background run's completion, in milliseconds.
const RUN_POLL_INTERVAL_MS = 5000;

export type WorkflowRunPhase = "idle" | "running" | "finished" | "unfinished";

interface WorkflowContextType {
  workflow: Workflow;

  selectedProcess: WorkflowProcess | null;

  selectProcess: (processId: string | null) => void;

  save: (outputDir: string) => Promise<void>;

  runPhase: WorkflowRunPhase;

  // Launches "Run workflow" in the background; throws (e.g. if a run
  // is already in progress) rather than resolving with an error, so
  // callers can show it inline. Resolves once the run has launched —
  // not once it's finished, see runPhase for that.
  startWorkflowRun: () => Promise<void>;

  // The running-progress indicator's Close button: stops the run if
  // it's still going, otherwise just dismisses the finished/unfinished
  // notice.
  dismissWorkflowRun: () => void;

  addProcess: (name: string, info: ProcessInfo | null) => void;

  applyProcessInfo: (
    processId: string,
    info: ProcessInfo
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

  setWorkflowOptions: (
    workflowOptions: Record<string, string>
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
    changes: Partial<Omit<WorkflowOption, "id">>
  ) => void;

  removeOption: (
    processId: string,
    optionId: string
  ) => void;

  connect: (
    edge: WorkflowEdge
  ) => void;

  disconnect: (
    edgeId: string
  ) => void;
}

function toWorkflowOption(info: ProcessInfoOption): WorkflowOption {
  return {
    id: crypto.randomUUID(),
    direction: getOptionDirection(info.label),
    label: info.label,
    dataType: info.dataType,
    description: info.description,
    value: "",
    fifo: false,
    commandLine: info.commandLine,
    mandatory: info.mandatory,
  };
}

const WorkflowContext =
  createContext<WorkflowContextType | null>(null);

/**
 * Makes each option's `value` reflect its incoming edge (if any): connected
 * options get the "[process;option]" reference, others are cleared of any
 * stale one. Self-heals workflows whose edges/values fell out of sync, e.g.
 * a file saved before this syncing existed, or a hand-edited JSON file.
 */
function normalizeConnectedOptionValues(source: Workflow): Workflow {

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
        `[${sourceProcess.name};${sourceOption.label}]`
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
  initialWorkflow: Workflow;
}

export function WorkflowProvider({
  children,
  initialWorkflow,
}: Props) {

  const [workflow, setWorkflowRaw] =
    useState<Workflow>(() => normalizeConnectedOptionValues(initialWorkflow));

  // Re-derives every connected option's "[process;option]" value from the
  // current edges/names on every update, so renaming a process or a
  // connected option's label can't leave a stale reference behind in what
  // gets saved/generated (see normalizeConnectedOptionValues above).
  function setWorkflow(updater: (current: Workflow) => Workflow) {
    setWorkflowRaw(current => normalizeConnectedOptionValues(updater(current)));
  }

  async function save(outputDir: string) {
    const updated = { ...workflow, homeDir: outputDir };
    await saveWorkflow(updated, outputDir);
    setWorkflow(() => updated);
  }

  const [runPhase, setRunPhase] =
    useState<WorkflowRunPhase>("idle");

  const pollTimerRef =
    useRef<number | null>(null);

  const beforeUnloadHandlerRef =
    useRef<(() => void) | null>(null);

  const runningWorkflowRef =
    useRef<Workflow | null>(null);

  // Mirrors runPhase for the unmount cleanup below, which — since its
  // effect has an empty dependency array and only runs once, on
  // unmount — would otherwise only ever see the phase from initial
  // mount rather than the current one.
  const runPhaseRef =
    useRef<WorkflowRunPhase>(runPhase);

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
  // doesn't fire — stop a still-running workflow here too, or it's
  // left running with nothing left to track or stop it.
  useEffect(() => {
    return () => {
      stopRunPolling();
      if (runPhaseRef.current === "running") {
        const runningWorkflow = runningWorkflowRef.current ?? workflow;
        stopWorkflow(runningWorkflow).catch(() => {
          // Best-effort — the UI tracking this run is already gone.
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startRunPolling(runningWorkflow: Workflow) {

    runningWorkflowRef.current = runningWorkflow;
    setRunPhase("running");

    const beforeUnloadHandler = () => {
      const blob = new Blob([JSON.stringify(runningWorkflow)], {
        type: "application/json",
      });
      navigator.sendBeacon("/api/execution/stop", blob);
    };

    beforeUnloadHandlerRef.current = beforeUnloadHandler;
    window.addEventListener("beforeunload", beforeUnloadHandler);

    pollTimerRef.current = window.setInterval(async () => {

      let state: WorkflowState;

      try {
        state = await getWorkflowState(runningWorkflow);
      } catch {
        return; // transient failure — try again next tick
      }

      if (state !== "in-progress") {
        stopRunPolling();
        setRunPhase(state === "finished" ? "finished" : "unfinished");
      }

    }, RUN_POLL_INTERVAL_MS);

  }

  async function startWorkflowRun() {

    const state = await getWorkflowState(workflow);

    if (state === "in-progress") {
      throw new Error("A run is already in progress for this output directory.");
    }

    await runWorkflow(workflow);
    startRunPolling(workflow);

  }

  function dismissWorkflowRun() {

    if (runPhase === "running") {
      stopRunPolling();
      const runningWorkflow = runningWorkflowRef.current ?? workflow;
      stopWorkflow(runningWorkflow).catch(() => {
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

    const process: WorkflowProcess = {

      id: crypto.randomUUID(),

      name,

      description: info?.description ?? "",

      position: {
        x: 100,
        y: 100,
      },

      options: info ? info.options.map(toWorkflowOption) : [],

      optionsHandler: {
        mode: "standard",
      },

      language: info?.language ?? "bash",

      code: info?.code ?? "",

      computationalSpecs: { ...DEFAULT_COMPUTATIONAL_SPECS },

      additionalSpecs: {
        forced: false,
      },

    };

    setWorkflow(current => ({
      ...current,
      processes: [...current.processes, process],
    }));

  }

  function applyProcessInfo(
    processId: string,
    info: ProcessInfo
  ) {

    setWorkflow(current => ({

      ...current,

      processes: current.processes.map(process =>
        process.id === processId
          ? {
              ...process,
              description: info.description,
              options: info.options.map(toWorkflowOption),
              language: info.language,
              code: info.code,
            }
          : process
      ),

    }));

  }

  function setDescription(
    description: string
  ) {

    setWorkflow(current => ({
      ...current,
      description,
    }));

  }

  function setPreamble(
    preamble: string
  ) {

    setWorkflow(current => ({
      ...current,
      preamble,
    }));

  }

  function setEnvVar(
    name: string,
    value: string
  ) {

    setWorkflow(current => ({
      ...current,
      envVars: { ...current.envVars, [name]: value },
    }));

  }

  function setOutputDir(
    outputDir: string
  ) {

    setWorkflow(current => ({
      ...current,
      outputDir,
    }));

  }

  function setExecutionOptions(
    executionOptions: ExecutionOptions
  ) {

    setWorkflow(current => ({
      ...current,
      executionOptions,
    }));

  }

  function setWorkflowOptions(
    workflowOptions: Record<string, string>
  ) {

    setWorkflow(current => ({
      ...current,
      workflowOptions,
    }));

  }

  function removeProcess(
    processId: string
  ) {

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

    const option: WorkflowOption = {

      id: crypto.randomUUID(),

      direction: getOptionDirection(label),

      label,

      dataType: "string",

      description: "",

      value: "",

      fifo: false,

      commandLine: false,

      mandatory: false,

    };

    setWorkflow(current => ({

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
    changes: Partial<Omit<WorkflowOption, "id">>
  ) {

    setWorkflow(current => ({

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

    setWorkflow(current => ({

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

  function setOptionValue(
    processes: WorkflowProcess[],
    processId: string,
    optionId: string,
    value: string
  ): WorkflowProcess[] {

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
    edge: WorkflowEdge
  ) {

    setWorkflow(current => {

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
            `[${sourceProcess.name};${sourceOption.label}]`
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

    setWorkflow(current => {

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
    workflow.processes.find(
      p => p.id === selectedProcessId
    ) ?? null;

  const value = useMemo(() => ({

    workflow,

    selectedProcess,

    selectProcess,

    save,

    runPhase,

    startWorkflowRun,

    dismissWorkflowRun,

    addProcess,

    applyProcessInfo,

    setDescription,

    setPreamble,

    setEnvVar,

    setOutputDir,

    setExecutionOptions,

    setWorkflowOptions,

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

    connect,

    disconnect,

  }), [
    workflow,
    selectedProcess,
    runPhase,
  ]);

  return (
    <WorkflowContext.Provider
      value={value}
    >
      {children}
    </WorkflowContext.Provider>
  );

}

export function useWorkflow() {

  const context =
    useContext(WorkflowContext);

  if (!context) {

    throw new Error(
      "useWorkflow must be used inside WorkflowProvider."
    );

  }

  return context;

}
