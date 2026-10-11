import type { OptionChannel, OptionDataType, ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

// The data type of an option is the type of the data that the option
// carries, and its option channel how the data gets to the process (see
// "Data type and option channel" in doc/design_doc_webui.md). With option
// channel "none" the process receives the data itself; through a FIFO or a
// value descriptor it receives a path, and the data type is that of each
// line of the FIFO, or of the value in the descriptor. A directory channel
// carries no data of a type of its own: its data type is always "dir". A
// connected input carries what the output it reads carries, and so has its
// data type.

// The data type that an option channel fixes, or null when the data type
// is free: the directory channels name a directory, whatever is in it.
export function channelDataType(channel: OptionChannel): OptionDataType | null {
  return channel === "shared_dir" || channel === "process_outdir" ? "dir" : null;
}

// The incoming edge of an input, if it is connected. Only inputs on a
// shared directory take several, all of which name the same directory.
function incomingEdge(program: Program, processId: string, optionId: string) {
  return program.edges.find(edge => edge.targetProcessId === processId && edge.targetOptionId === optionId);
}

// The output that a connected input reads, and its process, or null.
export function connectedSource(
  program: Program,
  processId: string,
  optionId: string
): { process: ProgramProcess; option: ProgramOption } | null {
  const edge = incomingEdge(program, processId, optionId);
  const process = edge && program.processes.find(candidate => candidate.id === edge.sourceProcessId);
  const option = process?.options.find(candidate => candidate.id === edge!.sourceOptionId);
  return process && option ? { process, option } : null;
}

// The data type of an option that nothing but its own fields decide, as
// that of an output, which no connection fixes.
export function ownDataType(option: ProgramOption): OptionDataType {
  return channelDataType(option.channel) ?? option.dataType;
}

// The data type that the option channel or the connection of an option
// fixes, or null when the user chooses it.
export function fixedDataType(program: Program, processId: string, option: ProgramOption): OptionDataType | null {
  const fromChannel = channelDataType(option.channel);
  if (fromChannel) {
    return fromChannel;
  }
  const source = connectedSource(program, processId, option.id);
  return source ? ownDataType(source.option) : null;
}

// The option channel through which the data of an option gets to its
// process: its own, or, for a connected input, that of the output it
// reads, since a connected input's own channel is "none" (or
// "shared_dir").
export function deliveryChannel(program: Program, processId: string, option: ProgramOption): OptionChannel {
  if (option.channel !== "none") {
    return option.channel;
  }
  return connectedSource(program, processId, option.id)?.option.channel ?? "none";
}

// Whether the process receives a path rather than the data itself: through
// a FIFO, a value descriptor or a directory channel. A Bash process is the
// exception for a value descriptor that it reads, whose value
// read_opt_value_from_func_args gives instead of the path.
export function receivesPath(program: Program, process: ProgramProcess, option: ProgramOption): boolean {
  const channel = deliveryChannel(program, process.id, option);
  if (channel === "none") {
    return false;
  }
  return !(channel === "value_desc" && option.direction === "input" && process.language === "bash");
}

// The program with the data type of every option that its option channel or
// its connection fixes set to that type, which keeps a connected input in
// step with the output it reads.
export function normalizeDataTypes(program: Program): Program {
  let changed = false;
  const processes = program.processes.map(process => {
    let processChanged = false;
    const options = process.options.map(option => {
      const fixed = fixedDataType(program, process.id, option);
      if (fixed === null || fixed === option.dataType) {
        return option;
      }
      processChanged = true;
      return { ...option, dataType: fixed };
    });
    if (!processChanged) {
      return process;
    }
    changed = true;
    return { ...process, options };
  });
  return changed ? { ...program, processes } : program;
}

// Why the data type of an option cannot be the one it has, or null: the
// one that its option channel or its connection fixes is another.
export function dataTypeProblem(program: Program, process: ProgramProcess, option: ProgramOption): string | null {
  const fixed = fixedDataType(program, process.id, option);
  if (fixed === null || fixed === option.dataType) {
    return null;
  }
  const where = `Option "${option.label}" of process "${process.name}"`;
  if (channelDataType(option.channel)) {
    return `${where} uses the channel "${option.channel}", which names a directory: its data type is "dir", not "${option.dataType}".`;
  }
  const source = connectedSource(program, process.id, option.id)!;
  return `${where} reads "${source.option.label}" of process "${source.process.name}", whose data type is "${fixed}": it carries the same data, so its data type is "${fixed}", not "${option.dataType}".`;
}
