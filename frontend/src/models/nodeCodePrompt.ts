import { fanoutCountText } from "./connections";
import type { ProgramOption } from "./option";
import { fanoutBaseLabel, isFanoutOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import type { NodeCode, NodeHookPart, NodeKind } from "./node";
import {
  DONE_PORT_LABEL,
  NODE_CODE_PARTS,
  NODE_HOOKS,
  PFILE_OPTION_LABEL,
  PROCESS_OPTION_LABEL,
  REQUESTS_PORT_LABEL,
  RUNS_ROOT_OPTION_LABEL,
  WATCH_DIR_OPTION_LABEL,
  inheritsHooks,
  isRequiredHook,
  nodeClassName,
  nodeOptionRole,
  superCall,
} from "./node";
import {
  ASK_BEFORE_GUESSING,
  COMMENT_SECTION_TITLE,
  NO_REDUNDANT_COMMENTS,
  describedAs,
  edgeEnd,
  fenceFor,
} from "./codePrompt";

// What the code prompt of a node takes from the runtime library, which the
// backend reads from the library itself: the reference of what the code of
// the node uses (empty, with the reason, when it could not be read), and
// the code of each hook that the node inherits from its class (with the
// reason, when it could not be read).
export interface NodeLibrary {
  reference: string;
  referenceError: string | null;
  inherited: Partial<Record<NodeHookPart, string>>;
  inheritedError?: string | null;
}

// Whether a node of `kind` has a code prompt: every node kind but the
// Supervisor, for which script generation writes all the code.
export function offersNodeCodePrompt(kind: NodeKind): boolean {
  return kind !== "Supervisor";
}

// The code prompt of a node: as that of a process (see buildCodePrompt),
// for code in parts. It asks for the parts that change, each whole, in a
// block of its own under the name of the part, so that the user pastes each
// one into its part; a part that the answer leaves out stays as it is.
export function buildNodeCodePrompt(
  program: Program,
  process: ProgramProcess,
  draft: NodeCode,
  request: string,
  library: NodeLibrary,
): string {
  const kind: NodeKind = process.nodeKind ?? "FBPProcess";

  const sections = [
    [
      `# Write the code of the DeBasher node \`${process.name}\``,
      "",
      "DeBasher runs resident programs: long-lived Python nodes that exchange JSON messages through FIFOs, keep a node state, and recover from a crash with a checkpoint of that state and a replay of the messages received since. Write the code of the node described below.",
    ],
    rulesSection(process, kind),
    librarySection(library),
    ["## The program", "", `- Name: \`${program.name}\``, ...describedAs(program.description)],
    nodeSection(process, kind),
    portsSection(program, process),
    codeSection(kind, draft, library),
    [
      "## What the code has to do",
      "",
      request.trim() === ""
        ? "Write the code that the description of the node asks for."
        : request.trim(),
    ],
    commentSection(),
    returnSection(),
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}

function rulesSection(process: ProgramProcess, kind: NodeKind): string[] {
  const className = nodeClassName(process.name);
  const signatures = NODE_HOOKS.map(h => `\`${h.signature}\``).join(", ");
  const lines = [
    "## How the code is put together",
    "",
    `- The node is a Python class, \`${className}\`, that derives from \`${kind}\` of the runtime library. The module that runs it is assembled from parts, in this order: \`from debasher_runtime_lib import ${kind}\`, the node preamble, \`class ${className}(${kind}):\`, the class body, each hook that has a body under its fixed signature, and \`${className}().run()\`.`,
    "- You write only the parts, each without the indentation of the class: the node preamble, the code before the class (imports, helper functions, constants); the class body (class attributes, the constructor, which calls `super().__init__()` and gives the node state its first value, and helper methods); and the body of each hook, without its `def` line.",
    `- The signatures of the hooks are fixed: ${signatures}. A hook with an empty body is left out of the class.`,
    "- The class never declares the ports of the node: the engine gives them from the options of its process (see the ports and options below).",
    "- Use the methods of the runtime library rather than writing your own: `self.sleep()`, not `time.sleep()`, to set the pace; `observe` with `self.inject()` to bring in what the node sees outside the program, never `process_data`; and `self.set_notice()` for what whoever watches the program should know (a missing configuration file), set again in `restore_node_state` when it follows from the node state.",
  ];
  if (kind === "FBPProcess") {
    lines.push("- This node has to give a body to `process_data`, `capture_node_state`, `restore_node_state` and `initialize_runtime` (`pass` when it has nothing to open), and to `observe` only if it looks at something outside the program, with `OBSERVE_PORT` set in the class body.");
  } else {
    lines.push(`- \`${kind}\` already implements every hook, so this node mostly sets class attributes. A hook with an empty body runs the one of \`${kind}\` (shown with the code below); a body replaces it, and can call the inherited one, such as \`${superCall(NODE_HOOKS[0].signature)}\`, to keep what it does.`);
  }
  return lines;
}

function librarySection(library: NodeLibrary): string[] {
  const header = ["## The runtime library", ""];
  if (library.reference.trim() === "") {
    return [...header, `The reference of the runtime library could not be read${library.referenceError ? ` (${library.referenceError})` : ""}. Follow the rules above.`];
  }
  return [
    ...header,
    "What the code of the node uses of its classes, from their own documentation:",
    "",
    library.reference.trim(),
  ];
}

function nodeSection(process: ProgramProcess, kind: NodeKind): string[] {
  const lines = [
    "## The node",
    "",
    `- Name: \`${process.name}\` (class \`${nodeClassName(process.name)}\`)`,
    `- Node kind: \`${kind}\``,
    ...describedAs(process.description),
  ];
  const mode = process.optionsHandler.mode;
  if (mode !== "standard") {
    lines.push(`- Tasks: the node runs as several tasks (options handler mode \`${mode}\`), each a node of its own with the options of that task.`);
  }
  return lines;
}

// A port is named after its option, without the leading dashes.
function portName(label: string): string {
  return label.replace(/^-+/, "");
}

function portsSection(program: Program, process: ProgramProcess): string[] {
  if (process.options.length === 0) {
    return ["## The ports and options", "", "The node has no options."];
  }
  return [
    "## The ports and options",
    "",
    ...process.options.flatMap(option => optionLines(program, process, option)),
  ];
}

function optionLines(program: Program, process: ProgramProcess, option: ProgramOption): string[] {
  const name = portName(option.label);
  const incoming = program.edges.filter(e => e.targetProcessId === process.id && e.targetOptionId === option.id);
  const outgoing = program.edges.filter(e => e.sourceProcessId === process.id && e.sourceOptionId === option.id);
  let role = nodeOptionRole(option);
  if (role === "businessInput" && incoming.length === 0) {
    // An input that a connection could reach, but none does: its value is
    // that of a configuration option.
    role = "configuration";
  }

  const notes: string[] = [];
  const description = option.description.trim();
  if (description !== "") {
    notes.push(...description.split("\n"));
  }

  const fanoutFamily = process.optionsHandler.mode === "standard" && isFanoutOption(option.label);
  let heading: string;

  switch (role) {
    case "businessOutput":
      heading = `business output, port \`${name}\``;
      if (classSends(process, option)) {
        notes.push(...classOptionNotes(process, option, false));
      } else if (fanoutFamily) {
        const base = portName(fanoutBaseLabel(option.label));
        notes.push(`A fanout family: the ports \`${base}0\`, \`${base}1\`, ..., as many as ${fanoutCountText(program, process, option)}; send on one with \`self.send_data(f"${base}{i}", payload)\`.`);
        if (!option.countSourceOptionId) {
          notes.push(`The node does not receive that number: count the ports of \`self.OUTPUT_PORTS\` named \`${base}<i>\`.`);
        }
      } else {
        notes.push(`Send on it with \`self.send_data("${name}", payload)\`, from \`process_data\` only.`);
      }
      for (const edge of outgoing) {
        const end = edgeEnd(program, edge.targetProcessId, edge.targetOptionId, "node");
        if (end) {
          notes.push(`Read by ${end.text}`, ...end.processNote);
        }
      }
      if (outgoing.length === 0 && !fanoutFamily) {
        notes.push("Nothing in the program reads it: someone outside the program reads it.");
      }
      break;
    case "businessInput":
      heading = `business input, port \`${name}\``;
      notes.push(`What arrives on it reaches \`process_data\` with \`port_name\` \`"${name}"\`.`);
      notes.push(...classOptionNotes(process, option, true));
      for (const edge of incoming) {
        const end = edgeEnd(program, edge.sourceProcessId, edge.sourceOptionId, "node");
        if (end) {
          notes.push(`Sent by ${end.text}`, ...end.processNote);
          const sender = program.processes.find(p => p.id === edge.sourceProcessId);
          if (sender) {
            notes.push(...sentMessageNotes(sender, end.option));
          }
        }
      }
      break;
    case "externalInput":
      heading = `external input, port \`${name}\``;
      notes.push(`Written by someone outside the program; what arrives on it reaches \`process_data\` with \`port_name\` \`"${name}"\`.`);
      break;
    default:
      heading = option.dataType === "None" ? "flag" : `configuration option, ${option.dataType}`;
      notes.push(...configurationNotes(option, name));
      notes.push(...classOptionNotes(process, option, false));
      break;
  }

  const facts = [heading];
  if (option.mandatory) {
    facts.push("mandatory");
  }
  if (option.commandLine) {
    facts.push("command line option");
  }
  if (option.taskShaping) {
    facts.push("task shaping option");
    notes.push("Only the options handler reads it, to decide the tasks of the node: no task receives it, so the code of the node cannot read it.");
  }
  return [`- \`${option.label}\` (${facts.join(", ")})`, ...notes.map(note => `  ${note}`)];
}

// The request that a ProgramLauncher takes, and the message that it sends on
// DONE_PORT for each batch run that ends (see ProgramLauncher in
// engine/debasher_runtime_launcher.py).
const LAUNCHER_REQUEST =
  '`{"opts": {"-<option>": "<value>", ...}, "run": "<run directory>"}`: the options of the general program, names with their dash and values as strings, and, optionally, the name of the run directory of the batch run';
const LAUNCHER_DONE_MESSAGE =
  '`{"run": ..., "run_dir": ..., "status": ..., "exit_code": ...}`, with `run_dir` the absolute path of the run directory, where the results of the batch run are, and `status` `"finished"` for an exit code of 0 and `"failed"` for any other';

// The request that the default request_for() of a DirectoryWatcher makes of
// the path of a complete file, with FILE_OPTION as the option of the path.
const WATCHER_REQUEST =
  '`{"opts": {"-infile": "<path of the file>"}, "run": "<name of the file without its extension>"}`';

// Whether the class of the node, not its code, sends on a business output:
// the requests of a DirectoryWatcher and the ends of the batch runs of a
// ProgramLauncher.
function classSends(process: ProgramProcess, option: ProgramOption): boolean {
  return (process.nodeKind === "DirectoryWatcher" && option.label === REQUESTS_PORT_LABEL)
    || (process.nodeKind === "ProgramLauncher" && option.label === DONE_PORT_LABEL);
}

// What the class of a DirectoryWatcher or a ProgramLauncher does with an
// option of the node: the options it looks for by name, and, for a
// launcher, a business input (`businessInput`), each of which takes
// requests. None for an FBPProcess.
function classOptionNotes(process: ProgramProcess, option: ProgramOption, businessInput: boolean): string[] {
  if (process.nodeKind === "DirectoryWatcher") {
    switch (option.label) {
      case WATCH_DIR_OPTION_LABEL:
        return ["The class `DirectoryWatcher` reads it (`WATCH_DIR_OPTION`): the directory it watches, in place of `WATCH_DIR`."];
      case REQUESTS_PORT_LABEL:
        return [`The class \`DirectoryWatcher\` sends on it (\`REQUESTS_PORT\`), once for each complete file, what \`request_for()\` makes of its path, by default ${WATCHER_REQUEST}. Redefine \`request_for\` in the class body to send something else; the code does not send on it.`];
      default:
        return [];
    }
  }
  if (process.nodeKind === "ProgramLauncher") {
    switch (option.label) {
      case PFILE_OPTION_LABEL:
        return ["The class `ProgramLauncher` reads it (`PFILE_OPTION`): the general program to launch, in place of `PFILE`."];
      case PROCESS_OPTION_LABEL:
        return ["The class `ProgramLauncher` reads it (`PROCESS_OPTION`): the process of the general program to launch alone, in place of `PROCESS`."];
      case RUNS_ROOT_OPTION_LABEL:
        return ["The class `ProgramLauncher` reads it (`RUNS_ROOT_OPTION`): the absolute path under which the run directories go, in place of `RUNS_ROOT`."];
      case DONE_PORT_LABEL:
        return [`The class \`ProgramLauncher\` sends on it (\`DONE_PORT\`), for each batch run that ends, ${LAUNCHER_DONE_MESSAGE}; the code does not send on it.`];
      default:
        return businessInput
          ? [`The class \`ProgramLauncher\` takes every message on it as a request for a batch run: ${LAUNCHER_REQUEST}.`]
          : [];
    }
  }
  return [];
}

// What each message on a business input holds when the class of the node
// at the other end sends it: the requests of a DirectoryWatcher and the
// ends of the batch runs of a ProgramLauncher.
function sentMessageNotes(sender: ProgramProcess, output: ProgramOption): string[] {
  if (!classSends(sender, output)) {
    return [];
  }
  if (sender.nodeKind === "ProgramLauncher") {
    return [`Each message is ${LAUNCHER_DONE_MESSAGE}.`];
  }
  const redefined = /\bdef request_for\b/.test(sender.nodeCode?.classBody ?? "");
  return [redefined
    ? `Each message is what \`request_for()\` of \`${sender.name}\`, redefined in its class body, makes of the path of a complete file.`
    : `Each message is ${WATCHER_REQUEST}, for one complete file.`];
}

function configurationNotes(option: ProgramOption, name: string): string[] {
  const notes = option.dataType === "None"
    ? [`\`self.opts["${name}"]\` is True when the flag is given; list \`"${name}"\` in the class attribute \`FLAGS\`.`]
    : [`Its value, a string, is \`self.opts["${name}"]\`.`];
  if (option.channel === "shared_dir") {
    notes.push(`The absolute path of the shared directory \`${option.value}\`.`);
  } else if (option.fromProcessSpec) {
    notes.push(`Its value is the \`${option.value}\` of the specifications of the node.`);
  } else if (!option.commandLine && option.dataType !== "None" && option.value.trim() !== "") {
    notes.push(`Its value: \`${option.value}\`.`);
  }
  return notes;
}

function codeSection(kind: NodeKind, draft: NodeCode, library: NodeLibrary): string[] {
  const lines = [
    "## The code to complete",
    "",
    "The parts of the node as they are now, each under its name:",
  ];
  if (inheritsHooks(kind) && library.inheritedError) {
    lines.push("", `The code of the hooks that the node inherits from \`${kind}\` could not be read (${library.inheritedError}).`);
  }
  for (const { part, label } of NODE_CODE_PARTS) {
    lines.push("", `### ${label}`, "");
    const code = draft[part].replace(/\n+$/, "");
    const hook = NODE_HOOKS.find(h => h.part === part);
    const inherited = hook ? library.inherited[hook.part] : undefined;
    if (code.trim() !== "") {
      const fence = fenceFor(code);
      lines.push(`${fence}python`, code, fence);
    } else if (hook && inheritsHooks(kind)) {
      lines.push(`Empty: the node runs \`${hook.name}\` of \`${kind}\`${inherited ? ", which is:" : "."}`);
    } else if (hook && isRequiredHook(kind, hook.part)) {
      lines.push("Empty, and required.");
    } else {
      lines.push("Empty.");
    }
    if (inherited && inheritsHooks(kind)) {
      const fence = fenceFor(inherited);
      if (code.trim() !== "") {
        lines.push("", `It replaces \`${hook!.name}\` of \`${kind}\`, which is:`);
      }
      lines.push("", `${fence}python`, inherited.replace(/\n+$/, ""), fence);
    }
  }
  return lines;
}

// How the code of a node is commented: as the runtime library documents its
// own classes, with a docstring for each method, and a word on the node
// state, which the hooks have to agree on.
function commentSection(): string[] {
  return [
    COMMENT_SECTION_TITLE,
    "",
    "Comment the code for someone who did not write it, as the runtime library documents its own classes:",
    "",
    "- A docstring for each helper function and method, and for each hook or method that the node redefines (for a hook, the first line of its body): what it does, and why when it is not obvious.",
    "- A comment for each step whose reason does not follow from the code: the format of a message, a choice made for the recovery of the node or the idempotence of an effect outside the program, why something is dropped.",
    "- A comment in the constructor on what the node state holds, which the constructor, `process_data`, `capture_node_state` and `restore_node_state` have to agree on.",
    NO_REDUNDANT_COMMENTS,
  ];
}

function returnSection(): string[] {
  const names = NODE_CODE_PARTS.map(({ label }) => `\`${label}\``).join(", ");
  return [
    "## What to return",
    "",
    ASK_BEFORE_GUESSING,
    "",
    `Return each part that you change, whole, in a fenced code block tagged \`python\`, under a heading \`### <part>\` with the name of the part: one of ${names}. Write each part as above: without the indentation of the class and, for a hook, without its \`def\` line. A part that you do not return stays as it is, so return every part that the change needs, and none that it does not.`,
  ];
}
