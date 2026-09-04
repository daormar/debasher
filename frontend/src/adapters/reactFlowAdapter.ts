import type {
  Connection,
  Edge,
  Node,
} from "@xyflow/react";

import type { Program } from "../models/program";
import type { ProgramProcess } from "../models/process";
import type { ProgramEdge } from "../models/edge";
import type { Position } from "../models/position";
import { isFanoutOption } from "../models/option";

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
 * Whether `option` (declared on `process`) is a fanout family option —
 * see isFanoutOption. Only meaningful on a "standard"-mode process.
 */
function isFanoutEndpoint(
  process: ProgramProcess | undefined,
  option: { label: string } | undefined
): boolean {
  return (
    process?.optionsHandler.mode === "standard" &&
    !!option &&
    isFanoutOption(option.label)
  );
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

    const targetProcess = program.processes.find(
      process => process.id === edge.targetProcessId
    );

    const targetOption = targetProcess?.options.find(
      option => option.id === edge.targetOptionId
    );

    const sourceIsFanout = isFanoutEndpoint(sourceProcess, sourceOption);
    const targetIsFanout = isFanoutEndpoint(targetProcess, targetOption);
    const isFanoutEdge = sourceIsFanout || targetIsFanout;

    return {

      id: edge.id,

      source: edge.sourceProcessId,

      sourceHandle: edge.sourceOptionId,

      target: edge.targetProcessId,

      targetHandle: edge.targetOptionId,

      // Omitted (rather than set to undefined) for a non-fanout edge, so
      // ReactFlow's `{...defaultEdgeOptions, ...edge}` merge doesn't have
      // an explicit `type: undefined` here clobbering the default type
      // ProgramCanvas configures (see its defaultEdgeOptions).
      ...(isFanoutEdge ? { type: "fanout" } : {}),

      data: isFanoutEdge
        ? { narrowEnd: sourceIsFanout ? "source" : "target" }
        : undefined,

      style: sourceOption?.channel === "fifo"
        ? { strokeDasharray: "6 4" }
        : undefined,

    };

  });

}

/**
 * Whether a connection is allowed: it must go from an output
 * option to an input option, the two options must belong to
 * different processes, and the target input must not already have
 * an incoming connection (an input accepts at most one connected
 * output, while an output may feed multiple inputs).
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

  const targetAlreadyConnected = program.edges.some(
    edge =>
      edge.targetProcessId === target &&
      edge.targetOptionId === targetHandle
  );

  // A fanout family option (see isFanoutOption) on a "standard" process
  // may only pair with an "array"-mode process on the other end, and
  // fanout options can't chain directly into one another.
  const sourceIsFanout = isFanoutEndpoint(sourceProcess, sourceOptionDef);
  const targetIsFanout = isFanoutEndpoint(targetProcess, targetOptionDef);

  if (sourceIsFanout && (targetProcess?.optionsHandler.mode !== "array" || targetIsFanout)) {
    return false;
  }
  if (targetIsFanout && (sourceProcess?.optionsHandler.mode !== "array" || sourceIsFanout)) {
    return false;
  }

  return (
    sourceOptionDef?.direction === "output" &&
    targetOptionDef?.direction === "input" &&
    !targetAlreadyConnected
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
