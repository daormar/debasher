import type { ProgramEdge } from "./edge";
import { isFanoutOption } from "./option";
import { isBusinessInputCandidate, isBusinessOutput } from "./node";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

// The rules of the connections between the options of a program's processes,
// which the canvas applies while the user draws an edge and any other code
// that adds one applies too.

// The two ends of an edge.
export type EdgeEndpoints = Omit<ProgramEdge, "id">;

/**
 * Whether `option` (declared on `process`) is a fanout family option
 * (see isFanoutOption). Only meaningful on a "standard"-mode process.
 */
export function isFanoutEndpoint(
  process: ProgramProcess | undefined,
  option: { label: string } | undefined
): boolean {
  return (
    process?.optionsHandler.mode === "standard" &&
    !!option &&
    isFanoutOption(option.label)
  );
}

// The non-"-ith" side of a fanout/fanin pairing, as in
// script_generation.py's _FANOUT_PARTNER_MODES.
export function isFanoutPartnerMode(process: ProgramProcess | undefined): boolean {
  return (
    process?.optionsHandler.mode === "array" ||
    process?.optionsHandler.mode === "generator"
  );
}

/**
 * Whether `to` can be reached from `from` (or is `from` itself) through
 * edges whose source option is not a fifo. Each such edge makes its
 * target wait for its source to finish (an afterok dependency of the
 * engine), while a fifo edge makes no dependency at all (see
 * debasher::_get_procdeps_for_process_task), so a cycle made only of
 * edges like these is one the engine refuses with "circular dependency
 * detected".
 */
function reachesWithoutFifo(program: Program, from: string, to: string): boolean {

  const channelOf = (processId: string, optionId: string) =>
    program.processes
      .find(process => process.id === processId)
      ?.options.find(option => option.id === optionId)?.channel;

  const visited = new Set<string>();
  const pending = [from];

  while (pending.length > 0) {
    const processId = pending.pop()!;
    if (processId === to) {
      return true;
    }
    if (visited.has(processId)) {
      continue;
    }
    visited.add(processId);
    for (const edge of program.edges) {
      if (
        edge.sourceProcessId === processId &&
        channelOf(edge.sourceProcessId, edge.sourceOptionId) !== "fifo"
      ) {
        pending.push(edge.targetProcessId);
      }
    }
  }

  return false;

}

/**
 * Whether a connection is allowed: it must go from an output option to
 * an input option whose value does not come from elsewhere: not a flag,
 * which takes no value, nor a command line option, nor one taken from the
 * process specifications, all of which script generation writes before it
 * looks at any connection. Both may
 * belong to the same process: a self-loop, which lets a process feed
 * itself. Every cycle, a self-loop included,
 * needs at least one edge from a fifo: a connection that is not from a
 * fifo is refused when it would close a cycle of connections that are
 * not from a fifo either, since the engine refuses such a cycle (see
 * reachesWithoutFifo). An output may always feed multiple inputs
 * (fan-out). An
 * input, by default, accepts at most one connected output, except a
 * "shared_dir" input (and not a fanout-family one, which keeps its own
 * single-source pairing rule), which may accept several, one per writer
 * of that same shared directory. That's the one case the engine
 * actually guarantees every connected source resolves to an identical
 * value (debasher::_dedup_resolved_opts): every "shared_dir" option
 * naming the same directory always resolves via get_absolute_shdirname
 * to the same absolute path, which is what makes gathering several
 * connections into one option safe in the first place; a plain option
 * has no such guarantee, so it stays limited to a single connection. A
 * "shared_dir" option, on either end, may also only ever pair with
 * another "shared_dir" option naming the identical directory.
 */
export function isValidEdge(
  program: Program,
  endpoints: EdgeEndpoints
): boolean {

  const {
    sourceProcessId: source,
    sourceOptionId: sourceHandle,
    targetProcessId: target,
    targetOptionId: targetHandle,
  } = endpoints;

  const sourceProcess = program.processes.find(process => process.id === source);
  const targetProcess = program.processes.find(process => process.id === target);

  const sourceOptionDef = sourceProcess?.options.find(
    option => option.id === sourceHandle
  );

  const targetOptionDef = targetProcess?.options.find(
    option => option.id === targetHandle
  );

  if (
    targetOptionDef?.dataType === "None" ||
    targetOptionDef?.commandLine ||
    targetOptionDef?.fromProcessSpec
  ) {
    return false;
  }

  // A resident program accepts a connection only from a business output to
  // an input that it makes a business input, of another node or of the
  // same one: every channel between its nodes is a FIFO. An external input
  // takes none, and the Supervisor wiring is never drawn by hand.
  if (
    program.programType === "resident" &&
    !(
      sourceOptionDef &&
      targetOptionDef &&
      isBusinessOutput(sourceOptionDef) &&
      isBusinessInputCandidate(targetOptionDef)
    )
  ) {
    return false;
  }

  // A fanout family option (see isFanoutOption) on a "standard" process
  // may only pair with an "array"- or "generator"-mode process on the
  // other end (mirrors script_generation.py's _FANOUT_PARTNER_MODES),
  // and fanout options can't chain directly into one another.
  const sourceIsFanout = isFanoutEndpoint(sourceProcess, sourceOptionDef);
  const targetIsFanout = isFanoutEndpoint(targetProcess, targetOptionDef);

  if (sourceIsFanout && (!isFanoutPartnerMode(targetProcess) || targetIsFanout)) {
    return false;
  }
  if (targetIsFanout && (!isFanoutPartnerMode(sourceProcess) || sourceIsFanout)) {
    return false;
  }

  const sourceIsSharedDir = sourceOptionDef?.channel === "shared_dir";
  const targetIsSharedDir = targetOptionDef?.channel === "shared_dir";

  // Fan-in (more than one incoming connection into the same input) is
  // only ever allowed when both ends are "shared_dir" options naming
  // the identical directory, the one case the engine guarantees every
  // connected source resolves to an identical value
  // (debasher::_dedup_resolved_opts). A single connection into any
  // other input follows the ordinary one-source rule regardless of
  // either option's channel: e.g. a "shared_dir" output can still
  // feed a single, ordinary "none"-channel input just like any other
  // output, exactly as decompress_deliverable's "-out-extractdir" feeds
  // a plain "-extractd" input.
  const targetAllowsMultipleConnections =
    targetIsSharedDir && sourceIsSharedDir && !targetIsFanout;

  const targetAlreadyConnected = program.edges.some(
    edge =>
      edge.targetProcessId === target &&
      edge.targetOptionId === targetHandle
  );

  if (targetAlreadyConnected && !targetAllowsMultipleConnections) {
    return false;
  }

  // Two "shared_dir" options may only ever pair with each other, and
  // only when they name the identical directory: a mismatched pair
  // would resolve to two different absolute paths, which is exactly
  // the case debasher::_dedup_resolved_opts rejects at run time.
  if (sourceIsSharedDir && targetIsSharedDir) {
    if (!sourceOptionDef!.value || sourceOptionDef!.value !== targetOptionDef!.value) {
      return false;
    }
  }

  if (
    sourceOptionDef?.channel !== "fifo" &&
    reachesWithoutFifo(program, target, source)
  ) {
    return false;
  }

  return (
    sourceOptionDef?.direction === "output" &&
    targetOptionDef?.direction === "input"
  );

}
