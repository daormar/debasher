import type { ComputationalSpecs, OptionsHandler, ProgramProcess } from "./process";
import type { OptionValueSource, ProgramOption } from "./option";
import { getCommandLineOptions, optionValueSource } from "./option";
import type { Program } from "./program";

// The node kinds of a resident program: the classes of the engine's runtime
// library with the same names (see doc/design_doc_resident.md). A program
// has at most one Supervisor.
export type NodeKind =
  | "FBPProcess"
  | "ProgramLauncher"
  | "DirectoryWatcher"
  | "Supervisor";

export const NODE_KINDS: { value: NodeKind; label: string; description: string }[] = [
  {
    value: "FBPProcess",
    label: "FBPProcess",
    description: "A business node: its code processes what arrives on its ports.",
  },
  {
    value: "ProgramLauncher",
    label: "ProgramLauncher",
    description: "Launches a general program for every request it receives.",
  },
  {
    value: "DirectoryWatcher",
    label: "DirectoryWatcher",
    description: "Brings in the files that arrive in a directory.",
  },
  {
    value: "Supervisor",
    label: "Supervisor",
    description:
      "Watches the other nodes and relaunches those that go down. Script " +
      "generation writes all of its code and options.",
  },
];

/**
 * The code of a node, in parts that script generation assembles into the
 * Python heredoc of its process, each kept without the indentation that all
 * its lines share. A hook with an empty body is not written.
 */
export interface NodeCode {

  preamble: string;

  classBody: string;

  processData: string;

  captureNodeState: string;

  restoreNodeState: string;

  initializeRuntime: string;

  observe: string;

}

export type NodeHookPart = Exclude<keyof NodeCode, "preamble" | "classBody">;

// The hooks of a node, in the order script generation writes them, each
// with its fixed signature.
export const NODE_HOOKS: { part: NodeHookPart; name: string; signature: string }[] = [
  { part: "processData", name: "process_data", signature: "def process_data(self, port_name, packet):" },
  { part: "captureNodeState", name: "capture_node_state", signature: "def capture_node_state(self):" },
  { part: "restoreNodeState", name: "restore_node_state", signature: "def restore_node_state(self, node_state):" },
  { part: "initializeRuntime", name: "initialize_runtime", signature: "def initialize_runtime(self):" },
  { part: "observe", name: "observe", signature: "def observe(self):" },
];

export function emptyNodeCode(): NodeCode {
  return {
    preamble: "",
    classBody: "",
    processData: "",
    captureNodeState: "",
    restoreNodeState: "",
    initializeRuntime: "",
    observe: "",
  };
}

/**
 * Whether a node of `kind` has to give a body for `part`: an FBPProcess the
 * first four hooks, and observe only if it watches something outside the
 * program. A ProgramLauncher and a DirectoryWatcher implement every hook,
 * so a body given for them overrides that of their class.
 */
export function isRequiredHook(kind: NodeKind, part: NodeHookPart): boolean {
  return kind === "FBPProcess" && part !== "observe";
}

// The classes of the runtime library, which the class of a node may not
// hide, and the Python builtins whose names a class named in CamelCase can
// take (those that start with a capital letter): the engine refuses a node
// whose class hides either (see debasher::_resident_class_name_checker_src
// in engine/debasher_lib_programs.sh).
const RUNTIME_CLASSES = ["FBPProcess", "Supervisor", "ProgramLauncher", "DirectoryWatcher"];

const CAPITALIZED_PYTHON_BUILTINS = [
  "ArithmeticError", "AssertionError", "AttributeError", "BaseException",
  "BaseExceptionGroup", "BlockingIOError", "BrokenPipeError", "BufferError",
  "BytesWarning", "ChildProcessError", "ConnectionAbortedError",
  "ConnectionError", "ConnectionRefusedError", "ConnectionResetError",
  "DeprecationWarning", "EOFError", "Ellipsis", "EncodingWarning",
  "EnvironmentError", "Exception", "ExceptionGroup", "False",
  "FileExistsError", "FileNotFoundError", "FloatingPointError",
  "FutureWarning", "GeneratorExit", "IOError", "ImportError",
  "ImportWarning", "IndentationError", "IndexError", "InterruptedError",
  "IsADirectoryError", "KeyError", "KeyboardInterrupt", "LookupError",
  "MemoryError", "ModuleNotFoundError", "NameError", "None",
  "NotADirectoryError", "NotImplemented", "NotImplementedError", "OSError",
  "OverflowError", "PendingDeprecationWarning", "PermissionError",
  "ProcessLookupError", "PythonFinalizationError", "RecursionError",
  "ReferenceError", "ResourceWarning", "RuntimeError", "RuntimeWarning",
  "StopAsyncIteration", "StopIteration", "SyntaxError", "SyntaxWarning",
  "SystemError", "SystemExit", "TabError", "TimeoutError", "True",
  "TypeError", "UnboundLocalError", "UnicodeDecodeError",
  "UnicodeEncodeError", "UnicodeError", "UnicodeTranslateError",
  "UnicodeWarning", "UserWarning", "ValueError", "Warning",
  "ZeroDivisionError",
];

/**
 * The name of the class of a node, after its process, in CamelCase, as the
 * engine requires: every part of the process name between dots and
 * underscores, with its first letter in upper case ("counter" gives
 * "Counter", "org.ns.count_words" gives "OrgNsCountWords").
 */
export function nodeClassName(processName: string): string {
  return processName
    .replace(/\./g, "_")
    .split("_")
    .filter(part => part.length > 0)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

/**
 * Why a process of a resident program cannot take `processName`, or null if
 * it can: its class would hide a class of the runtime library or a Python
 * builtin.
 */
export function nodeNameProblem(processName: string): string | null {
  const className = nodeClassName(processName);
  if (RUNTIME_CLASSES.includes(className)) {
    return (
      `The class of this node would be named ${className}, which is a class ` +
      "of the runtime library that it would hide."
    );
  }
  if (CAPITALIZED_PYTHON_BUILTINS.includes(className)) {
    return (
      `The class of this node would be named ${className}, which is a ` +
      "Python builtin that it would hide."
    );
  }
  return null;
}

// The labels of the options of the Supervisor wiring on a node, which
// script generation writes and no option of the user may take.
export const RESERVED_NODE_OPTION_LABELS = ["-outhb", "-trigger"];

export function isReservedNodeOptionLabel(label: string): boolean {
  return RESERVED_NODE_OPTION_LABELS.includes(label.trim());
}

/**
 * A business output: an output with option channel "fifo" and no fifo tag,
 * which the node writes. The one end of a connection in a resident program.
 */
export function isBusinessOutput(option: ProgramOption): boolean {
  return option.direction === "output" && option.channel === "fifo" && !option.fifoTag;
}

/**
 * An input that a connection can reach in a resident program, to become a
 * business input: one with option channel "none" whose value comes from no
 * command line option and no process specification. An external input
 * takes no connection, and neither does a flag, which takes no value.
 */
export function isBusinessInputCandidate(option: ProgramOption): boolean {
  return (
    option.direction === "input" &&
    option.channel === "none" &&
    option.dataType !== "None" &&
    !option.commandLine &&
    !option.fromProcessSpec
  );
}

/**
 * The sorts of the options of a node, as the canvas draws them: a business
 * output, an input that a connection can reach (a business input once
 * connected), an external input, or a configuration option, which no
 * connection feeds.
 */
export type NodeOptionRole =
  | "businessOutput"
  | "businessInput"
  | "externalInput"
  | "configuration";

export function nodeOptionRole(option: ProgramOption): NodeOptionRole {
  if (isBusinessOutput(option)) {
    return "businessOutput";
  }
  if (isBusinessInputCandidate(option)) {
    return "businessInput";
  }
  if (option.direction === "input" && option.channel === "fifo" && option.fifoTag === "external") {
    return "externalInput";
  }
  return "configuration";
}

/**
 * Whether a node observes the world outside the program: an FBPProcess with
 * a body for observe, and every ProgramLauncher and DirectoryWatcher, whose
 * classes implement it.
 */
export function observesOutside(process: ProgramProcess): boolean {
  switch (process.nodeKind) {
    case "FBPProcess":
      return (process.nodeCode?.observe.trim() ?? "") !== "";
    case "ProgramLauncher":
    case "DirectoryWatcher":
      return true;
    default:
      return false;
  }
}

/**
 * Where the value of a configuration option of a node comes from, as the
 * canvas tags its hollow handle: see optionValueSource, and "fixed" for an
 * output with option channel "none", whose value the module gives.
 */
export function configurationSource(option: ProgramOption): OptionValueSource | "fixed" {
  return optionValueSource(option) ?? "fixed";
}

// The flag of the Supervisor, a command line option, with which a run tells
// it not to hold the business channels. Script generation writes it, and
// the program model does not hold it, but the canvas draws it as an option
// of the Supervisor, as it draws the others.
export const NO_HOLD_FIFOS_LABEL = "-no-hold-fifos";

export function noHoldFifosOption(): ProgramOption {
  return {
    id: "supervisor:no-hold-fifos",
    label: NO_HOLD_FIFOS_LABEL,
    direction: "input",
    dataType: "None",
    channel: "none",
    mirror: false,
    description: "do not hold the FIFOs of the business channels",
    value: "",
    commandLine: true,
    mandatory: false,
    fromProcessSpec: false,
  };
}

// The computational specifications that each node kind reads, besides
// cpus, mem and time.
type ResidentSpecField = Exclude<keyof ComputationalSpecs, "cpus" | "mem" | "time">;

const NODE_SPEC_FIELDS: ResidentSpecField[] = [
  "input_log_max_mb",
  "out_backlog_max_mb",
  "out_backlog_fail_mb",
  "gil_switch_interval_ms",
  "startup_timeout_s",
];

export const RESIDENT_SPEC_FIELDS: Record<NodeKind, ResidentSpecField[]> = {
  FBPProcess: NODE_SPEC_FIELDS,
  DirectoryWatcher: NODE_SPEC_FIELDS,
  ProgramLauncher: [...NODE_SPEC_FIELDS, "max_concurrent_runs", "batch_sched"],
  Supervisor: ["heartbeat_timeout_s", "startup_timeout_s"],
};

export const RESIDENT_SPEC_LABELS: Record<ResidentSpecField, string> = {
  input_log_max_mb: "Input log cap (MiB)",
  out_backlog_max_mb: "Outbound backlog in a checkpoint, at most (MiB)",
  out_backlog_fail_mb: "Outbound backlog that stops the node (MiB)",
  gil_switch_interval_ms: "GIL switch interval (ms)",
  startup_timeout_s: "Startup deadline (s)",
  max_concurrent_runs: "Batch runs at a time",
  batch_sched: "Scheduler of the batch runs",
  heartbeat_timeout_s: "Heartbeat timeout (s)",
};

export function hasSupervisor(processes: ProgramProcess[]): boolean {
  return processes.some(process => process.nodeKind === "Supervisor");
}

/**
 * The command line options that "Set program options" offers: those of the
 * processes and, in a resident program with a Supervisor, its flag
 * -no-hold-fifos, which the program model does not hold, so that each run
 * can choose whether the Supervisor holds the business channels.
 */
export function programCommandLineOptions(
  program: Pick<Program, "programType" | "processes">
): ProgramOption[] {

  const options = getCommandLineOptions(program.processes);

  return program.programType === "resident" && hasSupervisor(program.processes)
    ? [...options, noHoldFifosOption()]
    : options;

}

/**
 * A node that a module of the preamble defines, suggested by the dialog that
 * names a new process of a resident program: its node kind, shown before it
 * is chosen.
 */
export interface SuggestedNode {

  name: string;

  nodeKind: NodeKind;

}

/**
 * What a node of a module brings to the resident program it is added to,
 * read by the rules of import: its description, node kind, code and
 * options, without the Supervisor wiring, which script generation derives
 * again, nor its connections, which belong to the program it came from.
 */
export interface NodeInfo {

  description: string;

  nodeKind: NodeKind;

  nodeCode: NodeCode;

  options: ProgramOption[];

  optionsHandler: OptionsHandler;

}
