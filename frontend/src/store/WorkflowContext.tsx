import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Workflow } from "../models/workflow";
import type {
  WorkflowNode,
  NodeLanguage,
  ComputationalSpecs,
  AdditionalSpecs,
} from "../models/node";
import type { WorkflowOption } from "../models/option";
import type { WorkflowEdge } from "../models/edge";
import type { Position } from "../models/position";
import { saveWorkflow } from "../storage/workflowStorage";

interface WorkflowContextType {
  workflow: Workflow;

  selectedNode: WorkflowNode | null;

  selectNode: (nodeId: string | null) => void;

  save: () => Promise<void>;

  addNode: () => void;

  setPreamble: (
    preamble: string
  ) => void;

  removeNode: (
    nodeId: string
  ) => void;

  moveNode: (
    nodeId: string,
    position: Position
  ) => void;

  renameNode: (
    nodeId: string,
    name: string
  ) => void;

  setNodeLanguage: (
    nodeId: string,
    language: NodeLanguage
  ) => void;

  setNodeCode: (
    nodeId: string,
    code: string
  ) => void;

  setComputationalSpecs: (
    nodeId: string,
    specs: ComputationalSpecs
  ) => void;

  setAdditionalSpecs: (
    nodeId: string,
    specs: AdditionalSpecs
  ) => void;

  addOption: (
    nodeId: string,
    direction: "input" | "output",
    label: string
  ) => void;

  updateOption: (
    nodeId: string,
    optionId: string,
    changes: Partial<Omit<WorkflowOption, "id">>
  ) => void;

  removeOption: (
    nodeId: string,
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

  const [selectedNodeId, setSelectedNodeId] =
    useState<string | null>(null);

  function selectNode(
    nodeId: string | null
  ) {
    setSelectedNodeId(nodeId);
  }

  function addNode() {

    const node: WorkflowNode = {

      id: crypto.randomUUID(),

      name: "New node",

      position: {
        x: 100,
        y: 100,
      },

      options: [],

      language: "bash",

      code: "",

      computationalSpecs: {},

      additionalSpecs: {
        forced: false,
      },

    };

    setWorkflow(current => ({
      ...current,
      nodes: [...current.nodes, node],
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

  function removeNode(
    nodeId: string
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.filter(
        node => node.id !== nodeId
      ),

      // Drop any edges left dangling by the removed node.
      edges: current.edges.filter(
        edge =>
          edge.sourceNodeId !== nodeId &&
          edge.targetNodeId !== nodeId
      ),

    }));

    setSelectedNodeId(current =>
      current === nodeId ? null : current
    );

  }

  function moveNode(
    nodeId: string,
    position: Position
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, position }
          : node
      ),

    }));

  }

  function renameNode(
    nodeId: string,
    name: string
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, name }
          : node
      ),

    }));

  }

  function setNodeLanguage(
    nodeId: string,
    language: NodeLanguage
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, language }
          : node
      ),

    }));

  }

  function setNodeCode(
    nodeId: string,
    code: string
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, code }
          : node
      ),

    }));

  }

  function setComputationalSpecs(
    nodeId: string,
    computationalSpecs: ComputationalSpecs
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, computationalSpecs }
          : node
      ),

    }));

  }

  function setAdditionalSpecs(
    nodeId: string,
    additionalSpecs: AdditionalSpecs
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? { ...node, additionalSpecs }
          : node
      ),

    }));

  }

  function addOption(
    nodeId: string,
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

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? {
              ...node,
              options: [
                ...node.options,
                option,
              ],
            }
          : node
      ),

    }));

  }

  function updateOption(
    nodeId: string,
    optionId: string,
    changes: Partial<Omit<WorkflowOption, "id">>
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? {
              ...node,
              options: node.options.map(o =>
                o.id === optionId
                  ? { ...o, ...changes }
                  : o
              ),
            }
          : node
      ),

    }));

  }

  function removeOption(
    nodeId: string,
    optionId: string
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? {
              ...node,
              options: node.options.filter(
                o => o.id !== optionId
              ),
            }
          : node
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

  const selectedNode =
    workflow.nodes.find(
      n => n.id === selectedNodeId
    ) ?? null;

  const value = useMemo(() => ({

    workflow,

    selectedNode,

    selectNode,

    save,

    addNode,

    setPreamble,

    removeNode,

    moveNode,

    renameNode,

    setNodeLanguage,

    setNodeCode,

    setComputationalSpecs,

    setAdditionalSpecs,

    addOption,

    updateOption,

    removeOption,

    connect,

    disconnect,

  }), [
    workflow,
    selectedNode,
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
