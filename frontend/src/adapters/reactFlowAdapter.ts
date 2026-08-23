import type {
  Connection,
  Edge,
  Node,
} from "@xyflow/react";

import type { Workflow } from "../models/workflow";
import type { WorkflowProcess } from "../models/process";
import type { WorkflowEdge } from "../models/edge";
import type { Position } from "../models/position";

/**
 * Data stored inside every React Flow node.
 */
export interface WorkflowProcessData {
  process: WorkflowProcess;
  [key: string]: unknown;
}

/**
 * Converts the workflow processes into React Flow nodes.
 */
export function workflowToReactFlowNodes(
  workflow: Workflow
): Node<WorkflowProcessData>[] {

  return workflow.processes.map(process => ({

    id: process.id,

    type: "workflow",

    position: process.position,

    data: {
      process,
    },

  }));

}

/**
 * Converts workflow edges into React Flow edges.
 */
export function workflowToReactFlowEdges(
  workflow: Workflow
): Edge[] {

  return workflow.edges.map(edge => ({

    id: edge.id,

    source: edge.sourceProcessId,

    sourceHandle: edge.sourceOptionId,

    target: edge.targetProcessId,

    targetHandle: edge.targetOptionId,

  }));

}

/**
 * Whether a connection is allowed: it must go from an output
 * option to an input option, and the two options must belong to
 * different processes.
 */
export function isValidWorkflowConnection(
  workflow: Workflow,
  connection: Connection | Edge
): boolean {

  const { source, target, sourceHandle, targetHandle } = connection;

  if (
    !source ||
    !target ||
    !sourceHandle ||
    !targetHandle ||
    source === target
  ) {
    return false;
  }

  const sourceProcess = workflow.processes.find(process => process.id === source);
  const targetProcess = workflow.processes.find(process => process.id === target);

  const sourceOptionDef = sourceProcess?.options.find(
    option => option.id === sourceHandle
  );

  const targetOptionDef = targetProcess?.options.find(
    option => option.id === targetHandle
  );

  return (
    sourceOptionDef?.direction === "output" &&
    targetOptionDef?.direction === "input"
  );

}

/**
 * Converts a React Flow connection into
 * our domain WorkflowEdge.
 */
export function connectionToWorkflowEdge(
  connection: Connection
): WorkflowEdge | null {

  if (
    !connection.source ||
    !connection.target ||
    !connection.sourceHandle ||
    !connection.targetHandle
  ) {
    return null;
  }

  return {

    id: crypto.randomUUID(),

    sourceProcessId: connection.source,

    sourceOptionId: connection.sourceHandle,

    targetProcessId: connection.target,

    targetOptionId: connection.targetHandle,

  };

}

/**
 * Updates a node position from React Flow.
 */
export function nodePosition(
  node: Node
): Position {

  return {

    x: node.position.x,

    y: node.position.y,

  };

}
