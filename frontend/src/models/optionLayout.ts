import type { ProgramEdge } from "./edge";
import type { ProgramOption } from "./option";
import type { Program } from "./program";
import { isFanoutEndpoint } from "./connections";

// Where the options of a process node are drawn, top or bottom, which the
// canvas and the reordering of the options share.

/**
 * Option ids whose handle should render on the opposite side from its
 * direction's default (Position.Top for input, Position.Bottom for
 * output). This applies only to the two options carrying the "return"
 * edge of a direct, mutual FIFO cycle between two vertically stacked
 * processes: e.g. process A above sends A.output(fifo) to
 * B.input(fifo), and B replies via B.output(fifo) to A.input(fifo).
 * Flipping just that return pair turns it into a short direct edge
 * instead of routing all the way around via isBackEdge/BackEdge. A
 * FIFO option is point-to-point by construction (one writer, one
 * reader, see isValidEdge's shared_dir-only fan-out/
 * fan-in allowance), so each flipped option id unambiguously refers
 * back to the one edge that earned it.
 */
export function computeFlippedOptionIds(program: Program): Set<string> {

  const byPair = new Map<string, { forward: ProgramEdge[]; backward: ProgramEdge[] }>();

  for (const edge of program.edges) {

    const sourceProcess = program.processes.find(process => process.id === edge.sourceProcessId);
    const targetProcess = program.processes.find(process => process.id === edge.targetProcessId);
    const sourceOption = sourceProcess?.options.find(option => option.id === edge.sourceOptionId);
    const targetOption = targetProcess?.options.find(option => option.id === edge.targetOptionId);

    if (!sourceProcess || !targetProcess || sourceOption?.channel !== "fifo") {
      continue;
    }
    if (isFanoutEndpoint(sourceProcess, sourceOption) || isFanoutEndpoint(targetProcess, targetOption)) {
      continue;
    }

    const [firstId, secondId] = [sourceProcess.id, targetProcess.id].sort();
    const pairKey = `${firstId}|${secondId}`;
    const entry = byPair.get(pairKey) ?? { forward: [], backward: [] };

    if (sourceProcess.id === firstId) {
      entry.forward.push(edge);
    } else {
      entry.backward.push(edge);
    }

    byPair.set(pairKey, entry);

  }

  const flippedOptionIds = new Set<string>();

  for (const { forward, backward } of byPair.values()) {

    if (forward.length === 0 || backward.length === 0) {
      continue;
    }

    const firstProcess = program.processes.find(process => process.id === forward[0].sourceProcessId)!;
    const secondProcess = program.processes.find(process => process.id === backward[0].sourceProcessId)!;

    if (firstProcess.position.y === secondProcess.position.y) {
      continue;
    }

    const lowerIsFirst = firstProcess.position.y > secondProcess.position.y;
    const returnEdge = lowerIsFirst ? forward[0] : backward[0];

    flippedOptionIds.add(returnEdge.sourceOptionId);
    flippedOptionIds.add(returnEdge.targetOptionId);

  }

  return flippedOptionIds;

}

/**
 * Which edge of its process node `option` renders at, used both by
 * ProcessNode (to group options into its top/bottom flex rows) and by
 * the Inspector's option-reorder UI (so dragging there matches what's
 * actually adjacent on the canvas, including a flipped option, see
 * computeFlippedOptionIds).
 */
export function optionRow(
  option: ProgramOption,
  flippedOptionIds: Set<string>
): "top" | "bottom" {
  return (option.direction === "input") !== flippedOptionIds.has(option.id)
    ? "top"
    : "bottom";
}

/**
 * The options of the process with those of one row put in the given order,
 * the other row left in place, or null when there is no such process or the
 * order does not list the whole row.
 */
export function reorderOptionRow(
  program: Program,
  processId: string,
  row: "top" | "bottom",
  orderedIds: string[]
): ProgramOption[] | null {

  const process = program.processes.find(p => p.id === processId);

  if (!process) {
    return null;
  }

  const flippedOptionIds = computeFlippedOptionIds(program);

  const rowIndices = process.options.reduce<number[]>(
    (indices, o, i) => optionRow(o, flippedOptionIds) === row ? [...indices, i] : indices,
    []
  );

  if (rowIndices.length !== orderedIds.length) {
    return null;
  }

  const optionsById = new Map(process.options.map(o => [o.id, o]));
  const options = [...process.options];

  rowIndices.forEach((index, i) => {
    const option = optionsById.get(orderedIds[i]);
    if (option) {
      options[index] = option;
    }
  });

  return options;

}
