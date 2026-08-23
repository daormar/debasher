import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Workflow } from "../models/workflow";
import type {
  WorkflowProcess,
  ProcessLanguage,
  ComputationalSpecs,
  AdditionalSpecs,
  OptionsHandler,
} from "../models/process";
import type { WorkflowOption } from "../models/option";
import type { WorkflowEdge } from "../models/edge";
import type { Position } from "../models/position";
import { saveWorkflow } from "../storage/workflowStorage";

interface WorkflowContextType {
  workflow: Workflow;

  selectedProcess: WorkflowProcess | null;

  selectProcess: (processId: string | null) => void;

  save: () => Promise<void>;

  addProcess: () => void;

  setPreamble: (
    preamble: string
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
    direction: "input" | "output",
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

const WorkflowContext =
  createContext<WorkflowContextType | null>(null);

interface Props {
  children: ReactNode;
  initialWorkflow: Workflow;
}

export function WorkflowProvider({
  children,
  initialWorkflow,
}: Props) {

  const [workflow, setWorkflow] =
    useState<Workflow>(initialWorkflow);

  async function save() {
    await saveWorkflow(workflow);
  }

  const [selectedProcessId, setSelectedProcessId] =
    useState<string | null>(null);

  function selectProcess(
    processId: string | null
  ) {
    setSelectedProcessId(processId);
  }

  function addProcess() {

    const process: WorkflowProcess = {

      id: crypto.randomUUID(),

      name: "New process",

      position: {
        x: 100,
        y: 100,
      },

      options: [],

      optionsHandler: {
        mode: "standard",
      },

      language: "bash",

      code: "",

      computationalSpecs: {},

      additionalSpecs: {
        forced: false,
      },

    };

    setWorkflow(current => ({
      ...current,
      processes: [...current.processes, process],
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
    direction: "input" | "output",
    label: string
  ) {

    const option: WorkflowOption = {

      id: crypto.randomUUID(),

      direction,

      label,

      dataType: "string",

      description: "",

      value: "",

      fifo: false,

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

  function connect(
    edge: WorkflowEdge
  ) {

    setWorkflow(current => ({

      ...current,

      edges: [
        ...current.edges,
        edge,
      ],

    }));

  }

  function disconnect(
    edgeId: string
  ) {

    setWorkflow(current => ({

      ...current,

      edges: current.edges.filter(
        e => e.id !== edgeId
      ),

    }));

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

    addProcess,

    setPreamble,

    removeProcess,

    moveProcess,

    renameProcess,

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
