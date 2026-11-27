import { isFanoutOption, type OptionChannel, type OptionDataType, type ProgramOption } from "./option";
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
// data type. It also receives it through the channel of that output, so its
// own channel follows from the output too (see getConnectedInputChannel).

// The data type that an option channel fixes, or null when the data type
// is free: the directory channels name a directory, whatever is in it.
export function getChannelDataType(channel: OptionChannel): OptionDataType | null {
  return channel === "shared_dir" || channel === "process_outdir" ? "dir" : null;
}

// Takes a connected input, its process and the output it reads; returns
// the option channel that the connection gives the input: "shared_dir"
// when the output names a shared directory, and "none" otherwise, since
// the channel of the output says how the data travels. The input of a
// fanout family is on "none" whatever its output, since it reads each
// task of the process at the other end. Script generation keeps the same
// rule (_normalize_connected_inputs).
export function getConnectedInputChannel(
  process: ProgramProcess,
  option: ProgramOption,
  sourceOption: ProgramOption
): OptionChannel {
  const isFanout = process.optionsHandler.mode === "standard" && isFanoutOption(option.label);
  return sourceOption.channel === "shared_dir" && !isFanout ? "shared_dir" : "none";
}

// Takes a connected input with the fields an edit gives it, its process
// and the output it reads, with its process; returns why the input cannot
// have that channel, or that directory, or null. The connection gives
// both (see getConnectedInputChannel), and an edit that sets another is
// refused rather than undone, so that its author learns it.
export function findConnectedInputChannelProblem(
  process: ProgramProcess,
  option: ProgramOption,
  sourceProcess: ProgramProcess,
  sourceOption: ProgramOption
): string | null {
  const where = `Option "${option.label}" of process "${process.name}" reads "${sourceOption.label}" of process "${sourceProcess.name}"`;
  const channel = getConnectedInputChannel(process, option, sourceOption);
  if (option.channel !== channel) {
    return `${where}, so its channel is "${channel}", which the connection gives it, not "${option.channel}". Leave channel and value out of the edit, or disconnect the input first.`;
  }
  if (channel === "shared_dir" && option.value !== sourceOption.value) {
    return `${where}, so it names the shared directory "${sourceOption.value}", which the connection gives it, not "${option.value}". Leave channel and value out of the edit, or disconnect the input first.`;
  }
  return null;
}

// The incoming edge of an input, if it is connected. Only inputs on a
// shared directory take several, all of which name the same directory.
function findIncomingEdge(program: Program, processId: string, optionId: string) {
  return program.edges.find(edge => edge.targetProcessId === processId && edge.targetOptionId === optionId);
}

// The output that a connected input reads, and its process, or null.
export function findConnectedSource(
  program: Program,
  processId: string,
  optionId: string
): { process: ProgramProcess; option: ProgramOption } | null {
  const edge = findIncomingEdge(program, processId, optionId);
  const process = edge && program.processes.find(candidate => candidate.id === edge.sourceProcessId);
  const option = process?.options.find(candidate => candidate.id === edge!.sourceOptionId);
  return process && option ? { process, option } : null;
}

// The data type of an option that nothing but its own fields decide, as
// that of an output, which no connection fixes.
export function getOwnDataType(option: ProgramOption): OptionDataType {
  return getChannelDataType(option.channel) ?? option.dataType;
}

// The data type that the option channel or the connection of an option
// fixes, or null when the user chooses it.
export function getFixedDataType(program: Program, processId: string, option: ProgramOption): OptionDataType | null {
  const fromChannel = getChannelDataType(option.channel);
  if (fromChannel) {
    return fromChannel;
  }
  const source = findConnectedSource(program, processId, option.id);
  return source ? getOwnDataType(source.option) : null;
}

// The option channel through which the data of an option gets to its
// process: its own, or, for a connected input, that of the output it
// reads, since a connected input's own channel is "none" (or
// "shared_dir").
export function getDeliveryChannel(program: Program, processId: string, option: ProgramOption): OptionChannel {
  if (option.channel !== "none") {
    return option.channel;
  }
  return findConnectedSource(program, processId, option.id)?.option.channel ?? "none";
}

// Whether the process receives a path rather than the data itself: through
// a FIFO, a value descriptor or a directory channel. A Bash process is the
// exception for a value descriptor that it reads, whose value
// read_opt_value_from_func_args gives instead of the path.
export function receivesPath(program: Program, process: ProgramProcess, option: ProgramOption): boolean {
  const channel = getDeliveryChannel(program, process.id, option);
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
      const fixed = getFixedDataType(program, process.id, option);
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

// Takes a program; returns it with every connected input on the channel
// that its connection gives it (see getConnectedInputChannel): on
// "shared_dir", with the directory of the output it reads, or on "none",
// without the fields that only the channel it leaves takes. The edges are
// the one source of truth about what is connected, so this keeps an input
// in step with its output, and repairs a program saved against the rule,
// such as one edited by hand.
export function normalizeConnectedInputChannels(program: Program): Program {
  let changed = false;
  const processes = program.processes.map(process => {
    let processChanged = false;
    const options = process.options.map(option => {
      const source = findConnectedSource(program, process.id, option.id);
      if (!source || !findConnectedInputChannelProblem(process, option, source.process, source.option)) {
        return option;
      }
      processChanged = true;
      const { fifoTag: _fifoTag, subpath, ...rest } = option;
      // A subpath names a subdirectory of the shared directory; on "none"
      // script generation refuses it
      if (getConnectedInputChannel(process, option, source.option) === "shared_dir") {
        return { ...rest, ...(subpath ? { subpath } : {}), channel: "shared_dir" as const, value: source.option.value, mirror: false };
      }
      return { ...rest, channel: "none" as const, mirror: false };
    });
    if (!processChanged) {
      return process;
    }
    changed = true;
    return { ...process, options };
  });
  return changed ? { ...program, processes } : program;
}

// Takes a program, a process and one of its options, with the fields an
// edit gives it; returns why a connected input cannot have that channel or
// directory, or null (see findConnectedInputChannelProblem).
export function findConnectedChannelProblem(program: Program, process: ProgramProcess, option: ProgramOption): string | null {
  const source = findConnectedSource(program, process.id, option.id);
  return source ? findConnectedInputChannelProblem(process, option, source.process, source.option) : null;
}

// Why the data type of an option cannot be the one it has, or null: the
// one that its option channel or its connection fixes is another.
export function findDataTypeProblem(program: Program, process: ProgramProcess, option: ProgramOption): string | null {
  const fixed = getFixedDataType(program, process.id, option);
  if (fixed === null || fixed === option.dataType) {
    return null;
  }
  const where = `Option "${option.label}" of process "${process.name}"`;
  if (getChannelDataType(option.channel)) {
    return `${where} uses the channel "${option.channel}", which names a directory: its data type is "dir", not "${option.dataType}".`;
  }
  const source = findConnectedSource(program, process.id, option.id)!;
  return `${where} reads "${source.option.label}" of process "${source.process.name}", whose data type is "${fixed}": it carries the same data, so its data type is "${fixed}", not "${option.dataType}".`;
}
