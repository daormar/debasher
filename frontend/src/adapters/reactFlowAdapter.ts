import type {
  Connection,
  Edge,
  Node,
} from "@xyflow/react";

import type { Workflow } from "../models/workflow";
import type { WorkflowNode } from "../models/node";
import type { WorkflowEdge } from "../models/edge";
import type { Position } from "../models/position";

/**
 * Data stored inside every React Flow node.
 */
export interface WorkflowNodeData {
  node: WorkflowNode;
  [key: string]: unknown;
}

/**
 * Converts the workflow nodes into React Flow nodes.
 */
export function workflowToReactFlowNodes(
  workflow: Workflow
): Node<WorkflowNodeData>[] {

  return workflow.nodes.map(node => ({

    id: node.id,

    type: "workflow",

    position: node.position,

    data: {
      node,
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

    source: edge.sourceNodeId,

    sourceHandle: edge.sourceOptionId,

    target: edge.targetNodeId,

    targetHandle: edge.targetOptionId,

  }));

}

/**
 * Whether a connection is allowed: it must go from an output
 * option to an input option, and the two options must belong to
 * different nodes.
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

  const sourceNode = workflow.nodes.find(node => node.id === source);
  const targetNode = workflow.nodes.find(node => node.id === target);

  const sourceOptionDef = sourceNode?.options.find(
    option => option.id === sourceHandle
  );

  const targetOptionDef = targetNode?.options.find(
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

    sourceNodeId: connection.source,

    sourceOptionId: connection.sourceHandle,

    targetNodeId: connection.target,

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
