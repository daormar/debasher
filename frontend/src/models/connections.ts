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

// One end of a connection, its process and its option resolved.
interface ConnectionEnd {
  process: ProgramProcess;
  option: ProgramOption;
}

// Takes a program and the ids of a process and of one of its options;
// returns them resolved, or null when either is missing.
function findConnectionEnd(program: Program, processId: string, optionId: string): ConnectionEnd | null {
  const process = program.processes.find(candidate => candidate.id === processId);
  const option = process?.options.find(candidate => candidate.id === optionId);
  return process && option ? { process, option } : null;
}

// Takes a program and an input; returns whether an edge already reaches it.
function isConnected(program: Program, target: ConnectionEnd): boolean {
  return program.edges.some(
    edge => edge.targetProcessId === target.process.id && edge.targetOptionId === target.option.id
  );
}

// Takes the input of a connection; returns whether its value comes from
// elsewhere: a flag, a command line option or the process specifications,
// which script generation writes before it looks at any connection.
function takesValueElsewhere(target: ConnectionEnd): boolean {
  const { option } = target;
  return option.dataType === "None" || option.commandLine || option.fromProcessSpec;
}

// Takes a program and the two ends of a connection; returns whether it is
// a resident program and the connection does not join a business output
// to an input that it makes a business input: every channel between its
// nodes is a FIFO, an external input takes none, and the Supervisor wiring
// is never drawn by hand.
function breaksResidentPairing(program: Program, source: ConnectionEnd, target: ConnectionEnd): boolean {
  return (
    program.programType === "resident" &&
    !(isBusinessOutput(source.option) && isBusinessInputCandidate(target.option))
  );
}

// Takes the two ends of a connection; returns whether it breaks the
// pairing of a fanout family (see isFanoutOption): a family pairs only with
// a process in "array" or "generator" mode (script_generation.py's
// _FANOUT_PARTNER_MODES), and never with another family.
function breaksFanoutPairing(source: ConnectionEnd, target: ConnectionEnd): boolean {
  const sourceIsFanout = isFanoutEndpoint(source.process, source.option);
  const targetIsFanout = isFanoutEndpoint(target.process, target.option);
  if (sourceIsFanout && (!isFanoutPartnerMode(target.process) || targetIsFanout)) {
    return true;
  }
  return targetIsFanout && (!isFanoutPartnerMode(source.process) || sourceIsFanout);
}

// Takes a program and the two ends of a connection; returns whether it
// would be a second connection into an input that takes one. Only
// "shared_dir" options take several, the one case where the engine sees
// every source resolve to the same value (debasher::_dedup_resolved_opts);
// a fanout family keeps its own single pairing.
function isRefusedFanIn(program: Program, source: ConnectionEnd, target: ConnectionEnd): boolean {
  const allowsSeveral =
    source.option.channel === "shared_dir" &&
    target.option.channel === "shared_dir" &&
    !isFanoutEndpoint(target.process, target.option);
  return isConnected(program, target) && !allowsSeveral;
}

// Takes a program and the two ends of a connection; returns whether it
// comes from a "shared_dir" output that names no directory, or adds a
// writer of another directory to an input that a "shared_dir" output
// already feeds: the input names the first writer's directory, and the
// second would resolve to another path, which
// debasher::_dedup_resolved_opts rejects at run time. An input not
// connected yet takes the directory of the output (see
// getConnectedInputChannel).
function breaksSharedDirectory(program: Program, source: ConnectionEnd, target: ConnectionEnd): boolean {
  if (source.option.channel !== "shared_dir") {
    return false;
  }
  if (!source.option.value) {
    return true;
  }
  return (
    target.option.channel === "shared_dir" &&
    isConnected(program, target) &&
    source.option.value !== target.option.value
  );
}

// Takes a program and the two ends of a connection; returns whether it is
// not from a fifo and closes a cycle of connections none of which is from
// a fifo. Such a connection makes its target wait for its source to
// finish (an afterok dependency), one from a fifo makes none
// (debasher::_get_procdeps_for_process_task), and the engine refuses a
// cycle of dependencies. It lets a self-loop pass, dropping the dependency
// of a process on itself, but such a process would only read the file it
// writes, so it is refused too.
function closesCycleWithoutFifo(program: Program, source: ConnectionEnd, target: ConnectionEnd): boolean {
  return source.option.channel !== "fifo" && reachesWithoutFifo(program, target.process.id, source.process.id);
}

/**
 * Takes a program and the two ends of a new connection; returns whether
 * the connection may be added: from an output that is not a flag, which
 * carries no data, to an input, of another process or of the same one (a
 * self-loop), with none of the rules below broken. An output may feed
 * several inputs.
 */
export function isValidEdge(
  program: Program,
  endpoints: EdgeEndpoints
): boolean {

  const source = findConnectionEnd(program, endpoints.sourceProcessId, endpoints.sourceOptionId);
  const target = findConnectionEnd(program, endpoints.targetProcessId, endpoints.targetOptionId);
  if (!source || !target) {
    return false;
  }

  return (
    source.option.direction === "output" &&
    target.option.direction === "input" &&
    source.option.dataType !== "None" &&
    !takesValueElsewhere(target) &&
    !breaksResidentPairing(program, source, target) &&
    !breaksFanoutPairing(source, target) &&
    !isRefusedFanIn(program, source, target) &&
    !breaksSharedDirectory(program, source, target) &&
    !closesCycleWithoutFifo(program, source, target)
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
