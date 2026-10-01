import type { Position } from "./position";
import type { Program } from "./program";

// Where the canvas places processes whose position nobody chose: those of an
// imported program, whose module says nothing about positions, those that an
// agent adds, and those that "Add program" brings in.

const START_X = 100;
const START_Y = 100;
const X_SPACING = 220;
const Y_SPACING = 160;

/**
 * The program with its processes placed in layers by the depth of their
 * connections: a process that feeds another's input is placed above it
 * (smaller y), so the edges run down the canvas, from the outputs along the
 * bottom of a process to the inputs along the top of the next.
 *
 * A layer comes from longest-path relaxation: a target's layer is pushed
 * below its source's on every pass, repeated until nothing changes. DeBasher
 * allows cycles between processes (through FIFOs), around which the
 * relaxation would chase an ever-growing layer forever, so the passes are
 * capped at the number of processes: every process can gain at most one
 * layer per full pass over the edges, so that many passes always reach the
 * fixpoint of the acyclic part of the graph, and for a cycle they end with
 * some layering rather than none. A self-loop says nothing about the order
 * of two processes, and relaxing it would only push its process down on
 * every pass, so it is left out.
 *
 * Processes that share a layer are placed side by side, left to right in
 * their order in the program, for a deterministic layout.
 */
export function layoutProcesses(program: Program): Program {

  const layer = new Map(program.processes.map(process => [process.id, 0]));

  for (let pass = 0; pass < program.processes.length; pass++) {
    let changed = false;
    for (const edge of program.edges) {
      const sourceLayer = layer.get(edge.sourceProcessId);
      const targetLayer = layer.get(edge.targetProcessId);
      if (sourceLayer === undefined || targetLayer === undefined) {
        continue;
      }
      if (edge.sourceProcessId === edge.targetProcessId) {
        continue;
      }
      if (sourceLayer + 1 > targetLayer) {
        layer.set(edge.targetProcessId, sourceLayer + 1);
        changed = true;
      }
    }
    if (!changed) {
      break;
    }
  }

  const nextXByLayer = new Map<number, number>();

  return {
    ...program,
    processes: program.processes.map(process => {
      const processLayer = layer.get(process.id)!;
      const x = nextXByLayer.get(processLayer) ?? START_X;
      nextXByLayer.set(processLayer, x + X_SPACING);
      return { ...process, position: { x, y: START_Y + processLayer * Y_SPACING } };
    }),
  };

}

// Where a process added to the program goes: to the right of the rightmost
// process, at the height of the first layer, so that it overlaps none.
export function nextFreePosition(program: Program): Position {
  if (program.processes.length === 0) {
    return { x: START_X, y: START_Y };
  }
  const rightmost = Math.max(...program.processes.map(process => process.position.x));
  return { x: rightmost + X_SPACING, y: START_Y };
}
