import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Workflow } from "../models/workflow";
import type { WorkflowNode } from "../models/node";
import type { WorkflowHandle } from "../models/handle";
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

  addHandle: (
    nodeId: string,
    direction: "input" | "output",
    label: string
  ) => void;

  removeHandle: (
    nodeId: string,
    handleId: string
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

      handles: [],
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

  function addHandle(
    nodeId: string,
    direction: "input" | "output",
    label: string
  ) {

    const handle: WorkflowHandle = {

      id: crypto.randomUUID(),

      direction,

      label,

    };

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? {
              ...node,
              handles: [
                ...node.handles,
                handle,
              ],
            }
          : node
      ),

    }));

  }

  function removeHandle(
    nodeId: string,
    handleId: string
  ) {

    setWorkflow(current => ({

      ...current,

      nodes: current.nodes.map(node =>
        node.id === nodeId
          ? {
              ...node,
              handles: node.handles.filter(
                h => h.id !== handleId
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

    addHandle,

    removeHandle,

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
