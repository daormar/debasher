import type {
  Connection,
  Edge,
  Node,
} from "@xyflow/react";

import type { Program } from "../models/program";
import type { ProgramProcess } from "../models/process";
import type { ProgramEdge } from "../models/edge";
import { isLabelEdge } from "../models/edge";
import type { Position } from "../models/position";
import type { ProgramOption } from "../models/option";
import { optionValueSource } from "../models/option";
import { isFanoutEndpoint, isFanoutPartnerMode, isValidEdge } from "../models/connections";
import { computeFlippedOptionIds } from "../models/optionLayout";
import {
  configurationSource,
  nodeOptionRole,
  observesOutside,
} from "../models/node";

/**
 * Data stored inside every React Flow node.
 */
export interface ProgramProcessData {
  process: ProgramProcess;
  flippedOptionIds: Set<string>;
  // The handles of the Supervisor wiring on this canvas node, while the
  // wiring is shown (see supervisorWiring).
  wiringHandles: WiringHandle[];
  [key: string]: unknown;
}

/**
 * Converts the program processes into React Flow nodes, with the handles of
 * the Supervisor wiring when `showWiring` is set.
 */
export function programToReactFlowNodes(
  program: Program,
  showWiring = false
): Node<ProgramProcessData>[] {

  const flippedOptionIds = computeFlippedOptionIds(program);

  const wiringHandles = showWiring ? supervisorWiring(program).handles : {};

  return program.processes.map(process => ({

    id: process.id,

    type: "program",

    position: process.position,

    data: {
      process,
      flippedOptionIds,
      wiringHandles: wiringHandles[process.id] ?? [],
    },

  }));

}

// The color of the edges of the Supervisor wiring, which are drawn dotted,
// apart from the business channels, dashed as every edge from a FIFO.
export const WIRING_EDGE_COLOR = "#7f93b5";

/**
 * A handle of the Supervisor wiring: on a node, its heartbeat channel (an
 * output) or, on an initiator, its trigger port (an input); on the
 * Supervisor, the other end of each of them, named after its node, and its
 * manual trigger port, written from outside the program. None of them is
 * an option of the program model, and none accepts a connection.
 */
export interface WiringHandle {
  id: string;
  row: "top" | "bottom";
  type: "source" | "target";
  label: string;
  // On the Supervisor, where a heartbeat channel and a trigger port of the
  // same node both carry its name, which channel the handle is, shown small
  // after the label.
  tag?: "heartbeat" | "trigger";
  kind: "heartbeat" | "trigger" | "manual";
}

/**
 * The Supervisor wiring of a resident program, as the canvas draws it: the
 * handles of each canvas node and the edges between them, read only. It is
 * derived by the same rule with which script generation derives it (see
 * api/resident_supervisor_wiring.py): from the Supervisor, the nodes and
 * which of them are initiators, and from whether a node runs as several
 * tasks, whose heartbeat channels or trigger ports the Supervisor reads or
 * writes as a fanout family. A program without a Supervisor has none.
 */
export function supervisorWiring(
  program: Program
): { handles: Record<string, WiringHandle[]>; edges: Edge[] } {

  const supervisor = program.processes.find(process => process.nodeKind === "Supervisor");

  if (program.programType !== "resident" || !supervisor) {
    return { handles: {}, edges: [] };
  }

  const nodes = program.processes.filter(process => process !== supervisor);

  const supervisorInputs: WiringHandle[] = [];
  const supervisorOutputs: WiringHandle[] = [];
  const handles: Record<string, WiringHandle[]> = {};
  const edges: Edge[] = [];

  const maxProcessX = Math.max(...program.processes.map(process => process.position.x));

  function wiringEdge(id: string, source: ProgramProcess, sourceHandle: string, target: ProgramProcess, targetHandle: string, familyEnd: "source" | "target"): Edge {
    const isFanout = isFanoutPartnerMode(familyEnd === "source" ? target : source);
    const detour = isBackEdge(source, target)
      ? { detourX: maxProcessX + BACK_EDGE_MARGIN, sourceLeftRank: 0, targetLeftRank: 0 }
      : undefined;
    return {
      id,
      source: source.id,
      sourceHandle,
      target: target.id,
      targetHandle,
      selectable: false,
      deletable: false,
      focusable: false,
      ...(isFanout
        ? { type: "fanout", data: { narrowEnd: familyEnd, isFifo: true, wiring: true, ...detour } }
        : detour
        ? { type: "backedge", data: detour }
        : {}),
      style: { stroke: WIRING_EDGE_COLOR, strokeDasharray: "2 4" },
    };
  }

  for (const node of nodes) {

    const nodeHandles: WiringHandle[] = [
      { id: "wiring:hb", row: "bottom", type: "source", label: "heartbeat", kind: "heartbeat" },
    ];

    supervisorInputs.push(
      { id: `wiring:hb:${node.id}`, row: "top", type: "target", label: node.name, tag: "heartbeat", kind: "heartbeat" }
    );

    edges.push(wiringEdge(`wiring:hb:${node.id}`, node, "wiring:hb", supervisor, `wiring:hb:${node.id}`, "target"));

    if (node.initiator) {

      nodeHandles.push(
        { id: "wiring:trigger", row: "top", type: "target", label: "trigger", kind: "trigger" }
      );

      supervisorOutputs.push(
        { id: `wiring:trigger:${node.id}`, row: "bottom", type: "source", label: node.name, tag: "trigger", kind: "trigger" }
      );

      edges.push(wiringEdge(`wiring:trigger:${node.id}`, supervisor, `wiring:trigger:${node.id}`, node, "wiring:trigger", "source"));

    }

    handles[node.id] = nodeHandles;

  }

  handles[supervisor.id] = [
    ...supervisorInputs,
    { id: "wiring:manual", row: "top", type: "target", label: "manual", tag: "trigger", kind: "manual" },
    ...supervisorOutputs,
  ];

  return { handles, edges };

}

/**
 * The structural key of a program: for each process, its id, name and
 * options handler mode, and the id, label and direction of each option and,
 * for an input, where its value comes from when no connection can give it
 * (see optionValueSource), which its hollow handle and tag show.
 * It changes whenever a process is added, removed or renamed, its options
 * handler mode is switched, or an option is added, removed or edited, and
 * never when a process is moved. The canvas refreshes its list of canvas
 * nodes from the program only when it changes (see ProgramCanvas), so
 * whatever a canvas node draws from its process has to be part of it.
 *
 * In a resident program it also holds, for each process, its node kind,
 * whether it is an initiator and whether it observes the outside world,
 * for each option its sort (see nodeOptionRole) and, for a configuration
 * option, where its value comes from, which decide how its handle is drawn,
 * and whether the Supervisor wiring is shown, which adds and removes handles.
 */
// Where the value of an input of a general program comes from when no
// connection can give it: what its hollow handle and its tag show.
function generalOptionKey(option: ProgramOption): string {
  return option.direction === "input" ? optionValueSource(option) ?? "" : "";
}

// The sort of an option of a node and, for a configuration option, where its
// value comes from: what its handle and its tag show.
function residentOptionKey(option: ProgramOption): string {
  const role = nodeOptionRole(option);
  return role === "configuration" ? `${role}:${configurationSource(option)}` : role;
}

export function canvasStructuralKey(program: Program, showWiring = false): string {
  const isResident = program.programType === "resident";
  const wiring = isResident && showWiring ? "|wiring" : "";
  return program.processes
    .map(process => {
      const options = process.options
        .map(o => `${o.id}:${o.label}:${o.direction}:${isResident ? residentOptionKey(o) : generalOptionKey(o)}`)
        .join(",");
      const key = `${process.id}:${process.name}:${process.optionsHandler.mode}:${options}`;
      return isResident
        ? `${key}:${process.nodeKind}:${!!process.initiator}:${observesOutside(process)}`
        : key;
    })
    .join("|") + wiring;
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
 * What the adapter gives a label edge (see LabelEdge). The stub at the
 * target names the source. The stub at the source is drawn by only one of
 * the label edges of its output, the first in the program, and names the
 * targets of all of them, so that an output with several label edges shows
 * one stub rather than several on top of each other. An input with several
 * label edges, one per source, shows one stub per edge, side by side.
 */
export interface LabelEdgeData {
  // The output of the source, `<process id>:<option id>`, shared by every
  // label edge from it.
  sourceKey: string;
  // "<process> <option>" of the source, which the target stub shows.
  sourceText: string;
  // Only on the edge that draws the source stub.
  sourceStub?: LabelEdgeSourceStub;
  // The place of this edge among the label edges into the same input.
  targetIndex: number;
  targetCount: number;
  isFifo: boolean;
  [key: string]: unknown;
}

export interface LabelEdgeSourceStub {
  // "<process> <option>" of each target, in program order.
  targetTexts: string[];
  targetProcessIds: string[];
}

// What a label edge names an option by: its process and its label.
function optionText(process: ProgramProcess | undefined, option: ProgramOption | undefined): string {
  return `${process?.name ?? "?"} ${option?.label ?? "?"}`;
}

/**
 * The data of each label edge of the program, by edge id.
 */
function labelEdgeData(program: Program): Map<string, LabelEdgeData> {

  const processById = new Map(program.processes.map(process => [process.id, process]));

  const optionOf = (processId: string, optionId: string) =>
    processById.get(processId)?.options.find(option => option.id === optionId);

  const labelEdges = program.edges.filter(isLabelEdge);

  const bySource = new Map<string, ProgramEdge[]>();
  const byTarget = new Map<string, ProgramEdge[]>();

  for (const edge of labelEdges) {
    const sourceKey = `${edge.sourceProcessId}:${edge.sourceOptionId}`;
    const targetKey = `${edge.targetProcessId}:${edge.targetOptionId}`;
    bySource.set(sourceKey, [...(bySource.get(sourceKey) ?? []), edge]);
    byTarget.set(targetKey, [...(byTarget.get(targetKey) ?? []), edge]);
  }

  const data = new Map<string, LabelEdgeData>();

  for (const edge of labelEdges) {

    const sourceKey = `${edge.sourceProcessId}:${edge.sourceOptionId}`;
    const siblings = bySource.get(sourceKey)!;
    const intoTarget = byTarget.get(`${edge.targetProcessId}:${edge.targetOptionId}`)!;
    const sourceOption = optionOf(edge.sourceProcessId, edge.sourceOptionId);

    data.set(edge.id, {
      sourceKey,
      sourceText: optionText(processById.get(edge.sourceProcessId), sourceOption),
      ...(siblings[0] === edge
        ? {
            sourceStub: {
              targetTexts: siblings.map(sibling =>
                optionText(
                  processById.get(sibling.targetProcessId),
                  optionOf(sibling.targetProcessId, sibling.targetOptionId)
                )
              ),
              targetProcessIds: siblings.map(sibling => sibling.targetProcessId),
            },
          }
        : {}),
      targetIndex: intoTarget.indexOf(edge),
      targetCount: intoTarget.length,
      isFifo: sourceOption?.channel === "fifo",
    });

  }

  return data;

}

/**
 * Converts program edges into React Flow edges.
 */
export function programToReactFlowEdges(
  program: Program
): Edge[] {

  const labelData = labelEdgeData(program);

  // Computed once per call (not per edge): every back edge shares the
  // same detour lane, positioned clear of every process in the
  // program regardless of which ones actually sit between a given
  // back edge's source and target.
  const maxProcessX = program.processes.length
    ? Math.max(...program.processes.map(process => process.position.x))
    : 0;

  const flippedOptionIds = computeFlippedOptionIds(program);

  return program.edges.map(edge => {

    // A label edge draws no route, so none of what follows applies to it.
    const label = labelData.get(edge.id);

    if (label) {
      return {
        id: edge.id,
        source: edge.sourceProcessId,
        sourceHandle: edge.sourceOptionId,
        target: edge.targetProcessId,
        targetHandle: edge.targetOptionId,
        type: "label",
        data: label,
      };
    }

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

    // A flipped mutual-FIFO return edge (see computeFlippedOptionIds)
    // already has its handles facing each other, so it never needs
    // BackEdge's rectilinear detour even though its target still sits
    // at or above its source.
    const isFlippedReturnEdge =
      flippedOptionIds.has(edge.sourceOptionId) &&
      flippedOptionIds.has(edge.targetOptionId);

    // A self-loop is drawn next to its own node (see SelfLoopEdge), not
    // along the lane of the back edges, which joins processes far apart.
    const selfLoop = !isFanoutEdge && edge.sourceProcessId === edge.targetProcessId;

    // Whether the edge goes back up and takes the detour lane, whatever it
    // looks like: a fanout edge that goes back up draws its wedge along
    // the detour too (see FanoutEdge).
    const goesBack =
      !selfLoop && !isFlippedReturnEdge && isBackEdge(sourceProcess, targetProcess);

    const backEdge = !isFanoutEdge && goesBack;

    // How many output ports sit to the right of the source port on its
    // node (0 for the rightmost). BackEdge and SelfLoopEdge use this to
    // lift an edge's near-node detour higher the further left its source
    // port sits, so edges from different output ports on the same node
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
      ...(isFanoutEdge
        ? { type: "fanout" }
        : selfLoop
        ? { type: "selfloop" }
        : backEdge
        ? { type: "backedge" }
        : {}),

      data: isFanoutEdge
        ? {
            narrowEnd: sourceIsFanout ? "source" : "target",
            isFifo: sourceOption?.channel === "fifo",
            ...(goesBack ? { detourX: maxProcessX + BACK_EDGE_MARGIN, sourceLeftRank, targetLeftRank } : {}),
          }
        : selfLoop
        ? { sourceLeftRank, targetLeftRank }
        : backEdge
        ? { detourX: maxProcessX + BACK_EDGE_MARGIN, sourceLeftRank, targetLeftRank }
        : undefined,

      style: sourceOption?.channel === "fifo"
        ? { strokeDasharray: "6 4" }
        : undefined,

    };

  });

}

// Whether a connection drawn on the canvas is allowed (see isValidEdge).
export function isValidProgramConnection(
  program: Program,
  connection: Connection | Edge
): boolean {

  const { source, target, sourceHandle, targetHandle } = connection;

  return (
    !!source &&
    !!target &&
    !!sourceHandle &&
    !!targetHandle &&
    isValidEdge(program, {
      sourceProcessId: source,
      sourceOptionId: sourceHandle,
      targetProcessId: target,
      targetOptionId: targetHandle,
    })
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
