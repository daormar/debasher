import { getChannelDataType, getOwnDataType } from "./dataTypes";
import type { OptionChannel, OptionDataType, OptionDirection, ProgramOption } from "./option";
import { DIRECTORY_CHANNELS, getOptionDirection, isFanoutOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import type { OptionChanges } from "./programEdits";

// What the editor of an option (components/OptionEditor.tsx) decides, apart
// from how it shows it: the connections that it names, the data type and the
// channels that it offers, and what a save writes.

// The fields of an option as the editor holds them while the user edits.
export interface OptionDraft {
  label: string;
  dataType: OptionDataType;
  channel: OptionChannel;
  subpath: string;
  mirror: boolean;
  description: string;
  value: string;
  commandLine: boolean;
  fromProcessSpec: boolean;
  mandatory: boolean;
  taskShaping: boolean;
  // "" for none
  countSourceOptionId: string;
}

// Takes an option; returns the draft that the editor starts from.
export function createOptionDraft(option: ProgramOption): OptionDraft {
  return {
    label: option.label,
    dataType: option.dataType,
    channel: option.channel,
    subpath: option.subpath ?? "",
    mirror: option.mirror,
    description: option.description,
    value: option.value,
    commandLine: option.commandLine,
    fromProcessSpec: option.fromProcessSpec,
    mandatory: option.mandatory,
    taskShaping: option.taskShaping ?? false,
    countSourceOptionId: option.countSourceOptionId ?? "",
  };
}

// Takes a draft and whether the option is connected; returns it without the
// fields that its other fields rule out, so that the editor never shows a
// combination that it does not offer. One pass is enough: the mirror,
// which depends on the channel, comes last.
export function correctOptionDraft(draft: OptionDraft, isConnected: boolean): OptionDraft {
  const corrected = { ...draft };
  const direction = getOptionDirection(corrected.label.trim());
  // A flag is always an input
  if (direction === "output" && corrected.dataType === "None") {
    corrected.dataType = "string";
  }
  // Only an output has a value descriptor or a process output directory
  if (direction === "input" && (corrected.channel === "value_desc" || corrected.channel === "process_outdir")) {
    corrected.channel = "none";
  }
  // A connected input takes the channel of its connection (see
  // getConnectedInputChannel): "none", or "shared_dir" when it reads a
  // shared directory
  if (isConnected && corrected.channel !== "none" && corrected.channel !== "shared_dir") {
    corrected.channel = "none";
  }
  // An output names what the process produces, never an attribute of its
  // specifications
  if (direction === "output") {
    corrected.fromProcessSpec = false;
  }
  // A value taken from the specifications comes from one
  // define_procspec_opt, and from no channel
  if (corrected.fromProcessSpec) {
    corrected.channel = "none";
  }
  // Only a FIFO output has a mirror
  if (!(corrected.channel === "fifo" && direction === "output")) {
    corrected.mirror = false;
  }
  return corrected;
}

// An output that the option reads, with its process and the sentinel that
// names it.
export interface ConnectedSource {
  process: ProgramProcess;
  option: ProgramOption;
  sentinel: string;
}

// Modes whose _define_opts/_generate_opts produces one save_opt_list call
// per task, numbered 0..N-1 (script_generation.py's _TASK_INDEXED_MODES).
const TASK_INDEXED_MODES = new Set(["generator", "array"]);

// Takes the process of an option, the option and the first output that it
// reads; returns whether the option gathers a fanout family: a family of a
// "standard" process that reads an "array" or "generator" process, which
// script generation expands into a loop of its own, one connection per task.
export function isFanoutGather(
  owner: ProgramProcess | undefined,
  option: ProgramOption,
  first: { process: ProgramProcess } | undefined
): boolean {
  return (
    isFanoutOption(option.label) &&
    owner?.optionsHandler.mode === "standard" &&
    !!first &&
    TASK_INDEXED_MODES.has(first.process.optionsHandler.mode)
  );
}

// Takes a program, the process of an option and the option; returns the
// outputs that the option reads, each with the sentinel that names it:
// with "${task_idx}" when both processes run several tasks, which script
// generation reads task by task, with "${i}" in the loop of a gathering
// family, and bare otherwise.
export function listConnectedSources(
  program: Program,
  owner: ProgramProcess | undefined,
  option: ProgramOption
): ConnectedSource[] {
  const resolved: { process: ProgramProcess; option: ProgramOption }[] = [];
  for (const edge of program.edges) {
    if (edge.targetProcessId !== owner?.id || edge.targetOptionId !== option.id) {
      continue;
    }
    const process = program.processes.find(candidate => candidate.id === edge.sourceProcessId);
    const source = process?.options.find(candidate => candidate.id === edge.sourceOptionId);
    if (process && source) {
      resolved.push({ process, option: source });
    }
  }
  const gather = isFanoutGather(owner, option, resolved[0]);
  return resolved.map(entry => {
    const names = `${entry.process.name};${entry.option.label}`;
    const taskIndexed =
      !!owner &&
      TASK_INDEXED_MODES.has(owner.optionsHandler.mode) &&
      TASK_INDEXED_MODES.has(entry.process.optionsHandler.mode);
    if (taskIndexed) {
      return { ...entry, sentinel: `[${names};\${task_idx}]` };
    }
    return { ...entry, sentinel: gather ? `[${names};\${i}]` : `[${names}]` };
  });
}

// Takes the first output that an option reads; returns whether the option
// reads a fanout family of a "standard" process (a scatter), so that its
// process has to run as many tasks as the family has members.
export function isScatterConsumer(first: ConnectedSource | undefined): boolean {
  return (
    !!first &&
    first.process.optionsHandler.mode === "standard" &&
    isFanoutOption(first.option.label)
  );
}

// Takes the first output that an option reads, a scatter (see
// isScatterConsumer); returns the count source option of its family, or
// undefined when the family counts the tasks of the process that reads it.
export function findScatterCountSource(first: ConnectedSource): ProgramOption | undefined {
  return first.process.options.find(candidate => candidate.id === first.option.countSourceOptionId);
}

// Takes the channel and the command line field of the draft and the first
// output that the option reads; returns the data type that they fix, or
// null when the user chooses it: a directory channel names a directory, and
// a connected input carries what the output it reads carries. A command
// line option has the channel "none", whatever the disabled channel
// selector still holds.
export function getLockedDataType(
  channel: OptionChannel,
  commandLine: boolean,
  first: ConnectedSource | undefined
): OptionDataType | null {
  return getChannelDataType(commandLine ? "none" : channel) ?? (first ? getOwnDataType(first.option) : null);
}

// Takes the same as getLockedDataType, for a data type that is locked;
// returns what the editor says fixes it.
export function describeLockedDataType(
  channel: OptionChannel,
  commandLine: boolean,
  first: ConnectedSource | undefined
): string {
  return first && !getChannelDataType(commandLine ? "none" : channel) ? "(from connection)" : "(directory channel)";
}

// Takes the process of an option, the option, the draft and whether the
// draft is a fanout family; returns whether the option can be a task
// shaping option: a command line input with a value, neither a fanout
// family nor the count source of one, which script generation refuses
// otherwise.
export function canShapeTasks(
  owner: ProgramProcess | undefined,
  option: ProgramOption,
  draft: Pick<OptionDraft, "label" | "dataType" | "commandLine">,
  isFanout: boolean
): boolean {
  const countsAFamily = owner?.options.some(candidate => candidate.countSourceOptionId === option.id) ?? false;
  return (
    draft.commandLine &&
    draft.dataType !== "None" &&
    getOptionDirection(draft.label.trim()) === "input" &&
    !isFanout &&
    !countsAFamily
  );
}

// Takes the processes that a fanout family without a count source option
// would count (see findFanoutCountProcesses); returns the text of that
// choice: the one process, with why an array is costlier, or why none or
// several leave the count to an option.
export function describeFanoutCount(countProcesses: ProgramProcess[]): string {
  if (countProcesses.length === 0) {
    return "Number of tasks of the connected array or generator (not connected yet)";
  }
  if (countProcesses.length > 1) {
    return "Number of tasks of the connected process (connected to several: choose an option)";
  }
  const [process] = countProcesses;
  // The engine counts an array not defined yet by running its whole option
  // definition again, so a generator is cheaper
  const note =
    process.optionsHandler.mode === "generator" ? ""
      : process.optionsHandler.mode === "array" ? " (an array: a generator is cheaper to count)"
        : " (not an array nor a generator: choose an option)";
  return `Number of tasks of ${process.name}${note}`;
}

// Takes the direction of an option and whether it is connected; returns the
// data types that the editor offers. A flag takes no connection and is
// always an input.
export function listOfferedDataTypes(direction: OptionDirection, isConnected: boolean): OptionDataType[] {
  const types: OptionDataType[] = ["int", "float", "string", "file", "dir"];
  return direction === "input" && !isConnected ? [...types, "None"] : types;
}

// Takes the direction of an option and whether its program is resident;
// returns the channels that the editor offers, each with its text. A
// resident program offers neither value descriptors nor directories, and
// its FIFOs are business outputs or external inputs; a value descriptor and
// a process output directory are for outputs only.
export function listOfferedChannels(
  direction: OptionDirection,
  isResident: boolean
): { channel: OptionChannel; text: string }[] {
  const fifoText = !isResident
    ? "FIFO"
    : direction === "output"
      ? "FIFO (business output)"
      : "External input (FIFO written from outside the program)";
  const channels: { channel: OptionChannel; text: string }[] = [{ channel: "none", text: "Direct value" }];
  if (direction === "output" && !isResident) {
    channels.push({ channel: "value_desc", text: "Value descriptor" });
  }
  channels.push({ channel: "fifo", text: fifoText });
  if (direction === "output" && !isResident) {
    channels.push({ channel: "process_outdir", text: "Process output directory" });
  }
  if (!isResident) {
    channels.push({ channel: "shared_dir", text: "Shared directory" });
  }
  return channels;
}

// What a save depends on besides the draft.
export interface SaveContext {
  isResident: boolean;
  // Whether the option reads an output
  isConnected: boolean;
  // See getLockedDataType
  lockedDataType: OptionDataType | null;
  // See canShapeTasks
  canShapeTasks: boolean;
  // Whether the draft is a fanout family of a "standard" process
  isFanout: boolean;
}

// Takes the draft and what the save depends on; returns the changes that a
// save writes to the option: the fields that the draft holds, without those
// that its other fields rule out, so that what is saved never holds a
// combination that script generation refuses.
export function buildOptionChanges(draft: OptionDraft, context: SaveContext): OptionChanges {
  const label = draft.label.trim();
  const direction = getOptionDirection(label);
  const isFlag = draft.dataType === "None";

  // An output names what the process produces, never an attribute of its
  // specifications
  const fromProcessSpec = !isFlag && direction === "input" && draft.fromProcessSpec;

  // A command line option takes its value from the command line only, never
  // through a channel, whatever the disabled channel selector still holds
  const commandLine = draft.commandLine && !fromProcessSpec;

  const taskShaping = commandLine && context.canShapeTasks && draft.taskShaping;

  // A connected input takes the channel of its connection, and
  // normalizeProgram gives it that of a shared directory it reads
  const channel: OptionChannel =
    isFlag || commandLine ? "none"
      : draft.channel === "shared_dir" ? "shared_dir"
        : context.isConnected ? "none"
          : draft.channel;

  return {
    label,
    direction,
    dataType: context.lockedDataType ?? draft.dataType,
    channel,
    // Only a FIFO output of a general program has a mirror
    mirror:
      !context.isResident && !isFlag && !commandLine && draft.channel === "fifo" &&
      direction === "output" && !context.isConnected && draft.mirror,
    // A FIFO input of a resident program is an external input
    fifoTag: context.isResident && channel === "fifo" && direction === "input" ? "external" : undefined,
    description: draft.description,
    // A flag, a value descriptor and a process output directory have no
    // value of their own
    value: isFlag || draft.channel === "value_desc" || channel === "process_outdir" ? "" : draft.value,
    subpath: DIRECTORY_CHANNELS.has(channel) ? draft.subpath.trim() : "",
    commandLine,
    fromProcessSpec,
    // A task shaping option is always mandatory
    mandatory: draft.commandLine && !fromProcessSpec && (draft.mandatory || taskShaping) && !isFlag,
    taskShaping,
    countSourceOptionId: context.isFanout ? (draft.countSourceOptionId || undefined) : undefined,
  };
}
