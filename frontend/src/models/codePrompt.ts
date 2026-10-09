import type { ProgramOption } from "./option";
import { fanoutBaseLabel, isFanoutOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import {
  LANGUAGE_NAMES,
  TEMPLATE_MARKER,
  generateCodeTemplate,
  languageRules,
} from "./codeTemplates";

// The code prompt of a process: a text that asks an AI tool for the code
// of the process and gives what the program model knows of it, for the
// user to copy into an AI tool of their choice. It is built from the
// program in the store and the draft of the code editor, not from what
// is saved, and the same arguments always give the same text.
export function buildCodePrompt(
  program: Program,
  process: ProgramProcess,
  draft: string,
  request: string,
): string {
  const language = LANGUAGE_NAMES[process.language];
  const code = draft.trim() === "" ? generateCodeTemplate(process) : draft;

  const sections = [
    [
      `# Write the code of the DeBasher process \`${process.name}\``,
      "",
      "DeBasher runs programs made of processes, each of which receives its options from the engine; the options of two processes are connected when one reads what the other writes. Write the code of the process described below.",
    ],
    ["## How the engine runs the code", "", ...languageRules(process.language, process.name)],
    ["## The program", "", `- Name: \`${program.name}\``, ...describedAs(program.description)],
    processSection(process, language),
    optionsSection(program, process),
    codeSection(process, code),
    [
      "## What the code has to do",
      "",
      request.trim() === ""
        ? "Write the code that the description of the process asks for."
        : request.trim(),
    ],
    returnSection(process, language),
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}

// A description as the lines of a list item, or nothing when it is blank.
export function describedAs(description: string, label = "Description"): string[] {
  const text = description.trim();
  if (text === "") {
    return [];
  }
  const [first, ...rest] = text.split("\n");
  return [`- ${label}: ${first}`, ...rest.map(line => `  ${line}`)];
}

function processSection(process: ProgramProcess, language: string): string[] {
  const lines = [
    "## The process",
    "",
    `- Name: \`${process.name}\``,
    `- Language: ${language}`,
    ...describedAs(process.description),
  ];
  switch (process.optionsHandler.mode) {
    case "array":
    case "generator":
    case "manual":
      lines.push(`- Tasks: the process runs the code once for each of its tasks (options handler mode \`${process.optionsHandler.mode}\`), each with the option list of that task.`);
      break;
    default:
      break;
  }
  return lines;
}

export function optionsSection(program: Program, process: ProgramProcess): string[] {
  if (process.options.length === 0) {
    return ["## The options", "", "The process has no options."];
  }
  return [
    "## The options",
    "",
    ...process.options.flatMap(option => optionLines(program, process, option)),
  ];
}

function optionKind(option: ProgramOption): string {
  if (option.dataType === "None") {
    return "flag";
  }
  return `${option.direction}, ${option.dataType}`;
}

function optionLines(program: Program, process: ProgramProcess, option: ProgramOption): string[] {
  const facts = [optionKind(option)];
  if (option.mandatory) {
    facts.push("mandatory");
  }
  if (option.commandLine) {
    facts.push("command line option");
  }
  if (option.taskShaping) {
    facts.push("task shaping option");
  }

  const lines = [`- \`${option.label}\` (${facts.join(", ")})`];
  const notes: string[] = [];

  const description = option.description.trim();
  if (description !== "") {
    notes.push(...description.split("\n"));
  }
  if (option.taskShaping) {
    notes.push("Only the options handler reads it, to decide the tasks of the process: no task receives it, so the code of the process cannot read it.");
  }

  const fanoutFamily = process.optionsHandler.mode === "standard" && isFanoutOption(option.label);
  if (fanoutFamily) {
    const base = fanoutBaseLabel(option.label);
    const countSource = process.options.find(o => o.id === option.countSourceOptionId);
    notes.push(countSource
      ? `A fanout family: the options \`${base}0\`, \`${base}1\`, ..., as many as the value of \`${countSource.label}\`.`
      : `A fanout family: the options \`${base}0\`, \`${base}1\`, ..., as many as an option that is not chosen yet says.`);
  }

  const connected = program.edges.some(e => e.targetProcessId === process.id && e.targetOptionId === option.id);
  notes.push(...channelNotes(process, option, fanoutFamily, connected));
  notes.push(...connectionNotes(program, process, option, fanoutFamily));

  return [...lines, ...notes.map(note => `  ${note}`)];
}

// What the option channel, or the literal value, of an option says about
// how the code reads or writes it.
function channelNotes(process: ProgramProcess, option: ProgramOption, fanoutFamily: boolean, connected: boolean): string[] {
  const bash = process.language === "bash";
  switch (option.channel) {
    case "fifo":
      return [option.direction === "output"
        ? "A FIFO that this process writes: close it once everything is written."
        : "A FIFO that this process reads until its end."];
    case "value_desc":
      return [bash
        ? "A value descriptor: write the value with `write_value_to_desc <value> <path>`, not into a file of your own."
        : "A value descriptor: write the value, alone, into the file that the option names."];
    case "shared_dir":
      return option.subpath?.trim()
        ? [`The absolute path of the directory \`${option.subpath.trim()}\` below the shared directory \`${option.value}\`, a directory of the task's own that exists when the code starts: write only into it, never elsewhere in the shared directory.`]
        : [`The absolute path of the shared directory \`${option.value}\`, which every process that names it shares.`];
    case "process_outdir":
      return processOutdirNotes(process, option);
    default:
      break;
  }
  if (option.fromProcessSpec) {
    return [`Its value is the \`${option.value}\` of the specifications of the process.`];
  }
  if (!option.commandLine && !fanoutFamily && !connected && option.value.trim() !== "") {
    return [`Its value: \`${option.value}\`.`];
  }
  return [];
}

// What an option with option channel "process_outdir" gives the code: a
// directory of the task's own, which the engine empties before the task
// runs unless the process has a _reset_outfiles method, or, without a
// subpath, the process output directory, which the tasks of an array or a
// generator share.
function processOutdirNotes(process: ProgramProcess, option: ProgramOption): string[] {
  const resetByProcess = (process.additionalMethods?.resetOutfilesCode ?? "").trim() !== "";
  const emptied = resetByProcess
    ? "it exists when the code starts, and its `reset_outfiles` method, not the engine, decides what is left in it from an earlier run"
    : "it exists and is empty when the code starts, so the code may write files of fixed names into it";
  const subpath = option.subpath?.trim();
  if (subpath) {
    return [`The absolute path of the directory \`${subpath}\` below the output directory of the process, a directory of the task's own: ${emptied}.`];
  }
  if (process.optionsHandler.mode === "array" || process.optionsHandler.mode === "generator") {
    return ["The absolute path of the output directory of the process, which every task of the process shares and which is not emptied before each of them: give each task files of names of its own."];
  }
  return [`The absolute path of the output directory of the process: ${emptied}.`];
}

// What the option is connected to: the outputs that an input reads, the
// inputs that read an output, or someone outside the program at the
// other end of an unconnected FIFO.
function connectionNotes(program: Program, process: ProgramProcess, option: ProgramOption, fanoutFamily: boolean): string[] {
  const bash = process.language === "bash";
  const notes: string[] = [];
  const incoming = program.edges.filter(e => e.targetProcessId === process.id && e.targetOptionId === option.id);
  const outgoing = program.edges.filter(e => e.sourceProcessId === process.id && e.sourceOptionId === option.id);

  for (const edge of incoming) {
    const end = edgeEnd(program, edge.sourceProcessId, edge.sourceOptionId);
    if (!end) {
      continue;
    }
    notes.push(`Reads ${end.text}`, ...end.processNote);
    if (end.option.channel === "fifo") {
      notes.push("That output is a FIFO: both processes run at the same time, so read it as it arrives, until its end.");
    } else if (end.option.channel === "value_desc") {
      notes.push(bash
        ? "That output is a value descriptor: `read_opt_value_from_func_args` gives the value, not the path."
        : "That output is a value descriptor: the option gives the path of a file that holds the value.");
    } else if (end.option.channel !== "shared_dir") {
      notes.push(`This process runs once \`${end.processName}\` has finished.`);
    }
  }

  for (const edge of outgoing) {
    const end = edgeEnd(program, edge.targetProcessId, edge.targetOptionId);
    if (end) {
      notes.push(`Read by ${end.text}`, ...end.processNote);
    }
  }

  if (option.channel === "fifo" && incoming.length === 0 && outgoing.length === 0 && !fanoutFamily) {
    notes.push(option.direction === "output"
      ? "Nothing in the program reads it: someone outside the program reads it."
      : "Nothing in the program writes it: someone outside the program writes it.");
  }

  return notes;
}

// One end of a connection: the option and its process, each with its
// description, if it has one.
export function edgeEnd(program: Program, processId: string, optionId: string, noun = "process") {
  const process = program.processes.find(p => p.id === processId);
  const option = process?.options.find(o => o.id === optionId);
  if (!process || !option) {
    return null;
  }
  const optionDescription = oneLine(option.description);
  const processDescription = oneLine(process.description);
  return {
    processName: process.name,
    option,
    text: `the option \`${option.label}\` of the ${noun} \`${process.name}\``
      + (optionDescription === "" ? "." : `: ${optionDescription}`),
    processNote: processDescription === "" ? [] : [`(\`${process.name}\`: ${processDescription})`],
  };
}

function oneLine(text: string): string {
  return text.trim().replace(/\s*\n\s*/g, " ");
}

// A fence longer than any run of backquotes in the code, so that the code
// cannot close it.
export function fenceFor(code: string): string {
  const longest = Math.max(2, ...[...code.matchAll(/`+/g)].map(m => m[0].length));
  return "`".repeat(longest + 1);
}

function codeSection(process: ProgramProcess, code: string): string[] {
  const fence = fenceFor(code);
  const instruction = code.includes(TEMPLATE_MARKER)
    ? `Keep the lines that read the options, and write the code of the process where the comment \`${TEMPLATE_MARKER}\` is.`
    : "Change this code as the next section says, and keep the rest of it.";
  return [
    "## The code to complete",
    "",
    `${fence}${process.language}`,
    code.replace(/\n+$/, ""),
    fence,
    "",
    instruction,
  ];
}

// What every code prompt says before the form of the answer: the program
// model never knows what the data hold, so the AI tool asks rather than
// guesses, and the answer is either its questions or the code.
export const ASK_BEFORE_GUESSING =
  "If something that the code depends on is missing or ambiguous, such as the format of an input or what each message holds, ask about it before writing any code, all your questions at once, instead of guessing. Otherwise, return the code as follows.";

function returnSection(process: ProgramProcess, language: string): string[] {
  const whole = process.language === "bash"
    ? `Return the whole code of the process, the line \`${process.name}()\` that names the function included, in a single fenced code block tagged \`bash\`, with nothing else inside the block.`
    : `Return the whole code of the process in a single fenced code block tagged \`${process.language}\`, with nothing else inside the block.`;
  return [
    "## What to return",
    "",
    ASK_BEFORE_GUESSING,
    "",
    whole,
    `Return all of it, not only what changed: the code of the block replaces the ${language} code of the process as it is.`,
  ];
}
