import type {
  Connection,
  Edge,
  Node,
} from "@xyflow/react";

import type { Program } from "../models/program";
import type { ProgramProcess } from "../models/process";
import type { ProgramEdge } from "../models/edge";
import type { Position } from "../models/position";

/**
 * Data stored inside every React Flow node.
 */
export interface ProgramProcessData {
  process: ProgramProcess;
  [key: string]: unknown;
}

/**
 * Converts the program processes into React Flow nodes.
 */
export function programToReactFlowNodes(
  program: Program
): Node<ProgramProcessData>[] {

  return program.processes.map(process => ({

    id: process.id,

    type: "program",

    position: process.position,

    data: {
      process,
    },

  }));

}

/**
 * Converts program edges into React Flow edges.
 */
export function programToReactFlowEdges(
  program: Program
): Edge[] {

  return program.edges.map(edge => {

    const sourceProcess = program.processes.find(
      process => process.id === edge.sourceProcessId
    );

    const sourceOption = sourceProcess?.options.find(
      option => option.id === edge.sourceOptionId
    );

    return {

      id: edge.id,

      source: edge.sourceProcessId,

      sourceHandle: edge.sourceOptionId,

      target: edge.targetProcessId,

      targetHandle: edge.targetOptionId,

      style: sourceOption?.channel === "fifo"
        ? { strokeDasharray: "6 4" }
        : undefined,

    };

  });

}

/**
 * Whether a connection is allowed: it must go from an output
 * option to an input option, and the two options must belong to
 * different processes.
 */
export function isValidProgramConnection(
  program: Program,
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

  const sourceProcess = program.processes.find(process => process.id === source);
  const targetProcess = program.processes.find(process => process.id === target);

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
 * our domain ProgramEdge.
 */
export function connectionToProgramEdge(
  connection: Connection
): ProgramEdge | null {

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
