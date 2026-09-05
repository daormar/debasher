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

// Horizontal clearance (px) between the detour lane a back edge (see
// isBackEdge) is routed through and the rightmost process in the
// program, so the lane sits clear of every node's box. Unlike a
// process's left edge (its bare position.x), its right edge isn't in
// the Program model at all — ProcessNode has no fixed width, only a
// minWidth, and grows with however many options it has — so this
// margin has to double as a stand-in for "widest plausible node width"
// too. Comfortable for the option counts in data/programs today; a
// process with an unusually large number of options could in
// principle still poke past it.
const BACK_EDGE_MARGIN = 260;

/**
 * Whether an edge points "backward" — its target sitting at or above
 * its source (smaller/equal y) — which a cyclic program always has at
 * least one of, since a strict top-to-bottom layering can't exist for
 * a cycle. Rendered via BackEdge instead of a plain edge; see there for
 * why a plain one would cut through intervening nodes.
 */
function isBackEdge(
  sourceProcess: ProgramProcess | undefined,
  targetProcess: ProgramProcess | undefined
): boolean {
  return (
    !!sourceProcess &&
    !!targetProcess &&
    targetProcess.position.y <= sourceProcess.position.y
  );
}

/**
 * Converts program edges into React Flow edges.
 */
export function programToReactFlowEdges(
  program: Program
): Edge[] {

  // Computed once per call (not per edge): every back edge shares the
  // same detour lane, positioned clear of every process in the
  // program regardless of which ones actually sit between a given
  // back edge's source and target.
  const maxProcessX = program.processes.length
    ? Math.max(...program.processes.map(process => process.position.x))
    : 0;

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
    const backEdge = !isFanoutEdge && isBackEdge(sourceProcess, targetProcess);

    // How many output ports sit to the right of the source port on its
    // node (0 for the rightmost). BackEdge uses this to lift a back
    // edge's near-node detour higher the further left its source port
    // sits, so back edges from different output ports on the same node
    // fan out at different heights instead of overlapping.
    const sourceOutputOptions = sourceProcess?.options.filter(
      option => option.direction === "output"
    ) ?? [];

    const sourceOptionIndex = sourceOutputOptions.findIndex(
      option => option.id === edge.sourceOptionId
    );

    const sourceLeftRank = sourceOptionIndex === -1
      ? 0
      : sourceOutputOptions.length - 1 - sourceOptionIndex;

    // Same idea, on the receiving end: how many input ports sit to the
    // right of the target port on its node. BackEdge uses this to raise
    // the target-side rise the further left the target port sits.
    const targetInputOptions = targetProcess?.options.filter(
      option => option.direction === "input"
    ) ?? [];

    const targetOptionIndex = targetInputOptions.findIndex(
      option => option.id === edge.targetOptionId
    );

    const targetLeftRank = targetOptionIndex === -1
      ? 0
      : targetInputOptions.length - 1 - targetOptionIndex;

    return {

      id: edge.id,

      source: edge.sourceProcessId,

      sourceHandle: edge.sourceOptionId,

      target: edge.targetProcessId,

      targetHandle: edge.targetOptionId,

      // Omitted (rather than set to undefined) for a plain edge, so
      // ReactFlow's `{...defaultEdgeOptions, ...edge}` merge doesn't have
      // an explicit `type: undefined` here clobbering the default type
      // ProgramCanvas configures (see its defaultEdgeOptions).
      ...(isFanoutEdge ? { type: "fanout" } : backEdge ? { type: "backedge" } : {}),

      data: isFanoutEdge
        ? { narrowEnd: sourceIsFanout ? "source" : "target" }
        : backEdge
        ? { detourX: maxProcessX + BACK_EDGE_MARGIN, sourceLeftRank, targetLeftRank }
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
