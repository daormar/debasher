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

    sourceHandle: edge.sourceHandleId,

    target: edge.targetNodeId,

    targetHandle: edge.targetHandleId,

  }));

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

    sourceHandleId: connection.sourceHandle,

    targetNodeId: connection.target,

    targetHandleId: connection.targetHandle,

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
