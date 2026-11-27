import type { ProgramEdge } from "./edge";
import { edgeEndText } from "./edge";
import { isFanoutOption } from "./option";
import type { ProgramOption } from "./option";
import { isBusinessInputCandidate, isBusinessOutput } from "./node";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

// The rules of the connections between the options of a program's processes,
// which the canvas applies while the user draws an edge and any other code
// that adds one applies too.

// The two ends of an edge.
export type EdgeEndpoints = Omit<ProgramEdge, "id">;

// The processes at the other end of the connections of a fanout family of
// `process`: the one that an input family reads, the ones that read an
// output family. A family without a count source option counts the tasks
// of that process, which has to be the only one and in "array" or
// "generator" mode (see _fanout_count_process in api/script_generation.py).
export function findFanoutCountProcesses(
  program: Program,
  process: ProgramProcess,
  option: ProgramOption
): ProgramProcess[] {
  const ids = new Set(
    program.edges.flatMap(edge => {
      if (option.direction === "input") {
        return edge.targetProcessId === process.id && edge.targetOptionId === option.id ? [edge.sourceProcessId] : [];
      }
      return edge.sourceProcessId === process.id && edge.sourceOptionId === option.id ? [edge.targetProcessId] : [];
    })
  );
  return program.processes.filter(p => ids.has(p.id));
}

// What gives the number of options of a fanout family of `process`, for a
// sentence "as many as ...": the value of its count source option, or the
// number of tasks of the process at the other end of its connections (see
// findFanoutCountProcesses).
export function describeFanoutCount(program: Program, process: ProgramProcess, option: ProgramOption): string {
  const countSource = process.options.find(o => o.id === option.countSourceOptionId);
  if (countSource) {
    return `the value of \`${countSource.label}\``;
  }
  const ends = findFanoutCountProcesses(program, process, option);
  return ends.length === 1
    ? `the tasks of \`${ends[0].name}\``
    : "the tasks of the process at the other end of its connections, an array or a generator";
}

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
 * Takes a program and the ids of two of its processes; returns whether
 * `to` can be reached from `from`, or is `from` itself, through edges
 * whose source option is not a fifo.
 */
function reachesWithoutFifo(program: Program, from: string, to: string): boolean {

  const channelOf = (processId: string, optionId: string) =>
    program.processes
      .find(process => process.id === processId)
      ?.options.find(option => option.id === optionId)?.channel;

  // A walk in depth over the processes, each visited once
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
 * Takes a program and the two ends of a new connection; returns whether
 * the connection may be added: from an output to an input, of another
 * process or of the same one (a self-loop). An output may feed several
 * inputs. It is refused when:
 * - the input takes its value from elsewhere: a flag, a command line
 *   option, or one taken from the process specifications;
 * - in a resident program, it does not join a business output to an
 *   input that it can make a business input;
 * - it breaks the pairing of a fanout family;
 * - the input is already connected, unless both ends are on "shared_dir";
 * - it adds a writer of another directory to an input that a "shared_dir"
 *   output already feeds, or comes from a "shared_dir" output that names no
 *   directory;
 * - it is not from a fifo and closes a cycle of connections none of which
 *   is from a fifo (see reachesWithoutFifo).
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

  // Script generation writes these before it looks at any connection
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

  // Several connections into one input only between "shared_dir" options
  // of the same directory, the one case where the engine sees every source
  // resolve to the same value (debasher::_dedup_resolved_opts); a fanout
  // family keeps its own single pairing
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

  // A "shared_dir" output that names no directory gives the input none.
  // An input that another writer already feeds names that writer's
  // directory, and a second writer of another one would resolve to a
  // different absolute path, which debasher::_dedup_resolved_opts rejects
  // at run time; an input not connected yet takes the directory of the
  // output (see getConnectedInputChannel)
  if (sourceIsSharedDir && !sourceOptionDef!.value) {
    return false;
  }
  if (
    sourceIsSharedDir &&
    targetIsSharedDir &&
    targetAlreadyConnected &&
    sourceOptionDef!.value !== targetOptionDef!.value
  ) {
    return false;
  }

  // A connection that is not from a fifo makes its target wait for its
  // source to finish (an afterok dependency), while one from a fifo makes
  // none (debasher::_get_procdeps_for_process_task). The engine refuses a
  // cycle of dependencies; it lets a self-loop pass, dropping the dependency
  // of a process on itself, but such a process would only read the file it
  // writes, so it is refused too
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

// An output that an input can be connected to, with the text that names it
// (see edgeEndText).
export interface ConnectionCandidate {
  sourceProcessId: string;
  sourceOptionId: string;
  text: string;
}

/**
 * The outputs that the input `targetOptionId` of `targetProcessId` can be
 * connected to, by the same rules as an edge drawn on the canvas (see
 * isValidEdge), in the order of the processes and of their options. An
 * output already connected to the input is left out.
 */
export function listConnectionCandidates(
  program: Program,
  targetProcessId: string,
  targetOptionId: string
): ConnectionCandidate[] {

  const connected = (sourceProcessId: string, sourceOptionId: string) =>
    program.edges.some(
      edge =>
        edge.sourceProcessId === sourceProcessId &&
        edge.sourceOptionId === sourceOptionId &&
        edge.targetProcessId === targetProcessId &&
        edge.targetOptionId === targetOptionId
    );

  return program.processes.flatMap(process =>
    process.options
      .filter(
        option =>
          option.direction === "output" &&
          !connected(process.id, option.id) &&
          isValidEdge(program, {
            sourceProcessId: process.id,
            sourceOptionId: option.id,
            targetProcessId,
            targetOptionId,
          })
      )
      .map(option => ({
        sourceProcessId: process.id,
        sourceOptionId: option.id,
        text: edgeEndText(process.name, option.label),
      }))
  );

}
