import { fanoutCountText } from "./connections";
import { deliveryChannel, receivesPath } from "./dataTypes";
import type { ProgramOption } from "./option";
import { fanoutBaseLabel, isFanoutOption } from "./option";
import type { ProcessLanguage, ProgramProcess } from "./process";
import type { Program } from "./program";
import type { SeqProcess } from "./seqProcess";
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
  const code = draft.trim() === "" ? generateCodeTemplate(program, process) : draft;

  const sections = [
    [
      `# Write the code of the DeBasher process \`${process.name}\``,
      "",
      "DeBasher runs programs made of processes, each of which receives its options from the engine; the options of two processes are connected when one reads what the other writes. Write the code of the process described below.",
    ],
    ["## How the engine runs the code", "", ...languageRules(process.language, process.name, process.files?.code)],
    ["## The program", "", `- Name: \`${program.name}\``, ...describedAs(program.description)],
    processSection(process, language),
    optionsSection(program, process),
    seqProcessesSection(program, process),
    codeSection(process, code),
    [
      "## What the code has to do",
      "",
      request.trim() === ""
        ? "Write the code that the description of the process asks for."
        : request.trim(),
    ],
    commentSection(process.language),
    returnSection(process, language),
  ];

  return sections.filter(lines => lines.length > 0).map(lines => lines.join("\n")).join("\n\n") + "\n";
}

// The sequential processes that a Bash process can run as steps with
// seq_execute, or nothing when the program has none or the process is in
// another language, which cannot call seq_execute. Their descriptions are
// all that tells the arguments they take, since they have no options.
function seqProcessesSection(program: Program, process: ProgramProcess): string[] {
  const seqProcesses = program.seqProcesses ?? [];
  if (process.language !== "bash" || seqProcesses.length === 0) {
    return [];
  }
  const onSlurm = seqProcesses.some(seqProcess => seqProcess.additionalSpecs.sched === "SLURM");
  return [
    "## The sequential processes",
    "",
    "The program has sequential processes: code that the process can run as a step with `seq_execute <name> <args>`, which runs it, waits for it to end and returns a status other than 0 when it fails. It receives the arguments exactly as they are given, as positional arguments or as options, which its description lists.",
    "",
    ...seqProcesses.map(seqProcessLine),
    "",
    "- Call `seq_execute` for these steps, not `seq_execute_slurm`: whether a step runs in the shell of the task or on Slurm is set by its sequential process.",
    "- Inside a loop that reads its standard input, give the step `< /dev/null`, or the step takes the rest of the loop's input.",
    ...(onSlurm
      ? ["- A step on Slurm runs in a new shell, possibly on another machine: give it everything it needs as arguments, and pass it files, never a FIFO."]
      : []),
  ];
}

// A sequential process as a line of the list: its name, its language or
// the code it takes from an alias, whether its steps go to Slurm, and its
// description, which says what arguments it takes.
function seqProcessLine(seqProcess: SeqProcess): string {
  const { alias, aliasOptMap, externalAlias, sched } = seqProcess.additionalSpecs;
  const renamed = (aliasOptMap ?? []).map(mapping => `\`${mapping.fromLabel}\` passed on as \`${mapping.toLabel}\``);
  const traits = [
    alias ? `alias of \`${alias}\`` : externalAlias ? `external alias \`${externalAlias}\`` : LANGUAGE_NAMES[seqProcess.language],
    ...((alias || externalAlias) ? renamed : []),
    sched === "SLURM" ? "steps on Slurm" : null,
    seqProcess.description.trim() === "" ? "arguments not described" : null,
  ].filter(Boolean);
  const description = seqProcess.description.trim() === "" ? "" : `: ${oneLine(seqProcess.description)}`;
  return `- \`${seqProcess.name}\` (${traits.join(", ")})${description}`;
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

// The direction of an option and the type of what the code receives for
// it: the data itself, or a path that leads to the data, whose data type
// says what is there (see receivesPath).
function optionKind(program: Program, process: ProgramProcess, option: ProgramOption): string {
  if (option.dataType === "None") {
    return "flag";
  }
  if (!receivesPath(program, process, option)) {
    return `${option.direction}, ${option.dataType}`;
  }
  switch (deliveryChannel(program, process.id, option)) {
    case "fifo":
      return `${option.direction}, the path of a FIFO, each line a ${option.dataType}`;
    case "value_desc":
      return `${option.direction}, the path of a value descriptor that holds a ${option.dataType}`;
    default:
      return `${option.direction}, the path of a directory`;
  }
}

function optionLines(program: Program, process: ProgramProcess, option: ProgramOption): string[] {
  const facts = [optionKind(program, process, option)];
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
    notes.push(`A fanout family: the options \`${base}0\`, \`${base}1\`, ..., as many as ${fanoutCountText(program, process, option)}.`);
    if (!option.countSourceOptionId) {
      notes.push("The task does not receive that number: count the options of the family among the arguments.");
    }
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

// The dependency types that make a process wait for another one to end.
const END_DEPTYPES = ["afterok", "afterany", "afternotok", "aftercorr"];

// The modes in which the generated code connects the task of an index to
// the task of the same index of the other process (see _TASK_INDEXED_MODES
// in api/script_generation.py), so that the engine infers aftercorr.
const TASK_INDEXED_MODES = ["array", "generator"];

// When a process starts with respect to the process whose file an input
// reads. With no processdeps, the inferred dependency waits for that
// process to finish, or, between two processes of task-indexed modes, for
// the task of the same index (aftercorr), which a manual options handler
// may ask for too; processdeps replaces every inferred dependency, and the
// elements on that process of a type that waits for its end say how
// complete the file is. In a list joined by "," every element holds, so
// they are taken together, as the engine merges them; in a list joined by
// "?" another element may be enough, so none of them is sure to hold.
function fileWaitNote(process: ProgramProcess, producerProcess: ProgramProcess): string {
  const producer = producerProcess.name;
  const counterpart = `Each task of this process runs once the task of \`${producer}\` with the same index has finished, while other tasks of \`${producer}\` may still be running`;
  const processdeps = process.additionalSpecs?.processdeps?.trim();
  if (!processdeps) {
    const readerMode = process.optionsHandler.mode;
    const producerMode = producerProcess.optionsHandler.mode;
    if (TASK_INDEXED_MODES.includes(readerMode) && TASK_INDEXED_MODES.includes(producerMode)) {
      return `${counterpart}.`;
    }
    if (readerMode === "manual" && producerMode !== "standard") {
      return `This process runs once \`${producer}\` has finished, unless its options handler connects each task to the task of \`${producer}\` with the same index (\`define_opt_from_proc_task_out\`), in which case each task waits only for that task of \`${producer}\`.`;
    }
    return `This process runs once \`${producer}\` has finished.`;
  }
  const alternatives = processdeps.includes("?");
  const types = new Set(processdeps.split(alternatives ? "?" : ",")
    .map(dep => dep.split(":"))
    .filter(([type, proc]) => proc === producer && END_DEPTYPES.includes(type))
    .map(([type]) => type));
  if (types.size === 0) {
    return `The \`processdeps\` of this process do not wait for \`${producer}\` to finish, so the file may not be complete when it starts.`;
  }
  if (alternatives) {
    return `The \`processdeps\` of this process may let it start before \`${producer}\` finishes (one dependency joined by "?" is enough), so the file may not be complete when it starts.`;
  }
  if (types.has("afternotok")) {
    return `This process runs once \`${producer}\` has failed, so the file may be incomplete or missing.`;
  }
  if (types.has("afterok") || (types.has("afterany") && types.has("aftercorr"))) {
    return `This process runs once \`${producer}\` has finished.`;
  }
  if (types.has("aftercorr")) {
    return `${counterpart} (a task with no such counterpart waits for every task of \`${producer}\`).`;
  }
  return `This process runs once \`${producer}\` has ended, whether it finished or failed, so the file may be incomplete or missing.`;
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
      notes.push(fileWaitNote(process, end.process));
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
    process,
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

// How the code of a process is commented, in the style of the code of
// DeBasher itself (the Bash modules of the engine and of data/programs, the
// runtime library of the nodes): what a reader cannot get from the code,
// never what the code already says.
export const COMMENT_SECTION_TITLE = "## How to comment the code";
export const COMMENT_STEPS =
  "- A comment for each step whose reason does not follow from the code: the format of an input, why something is skipped or dropped, a choice made so that the code can run again on what an earlier run left.";
export const NO_REDUNDANT_COMMENTS = "- No comment that only repeats what the code says.";

// The section on comments of the code prompt of code in `language`, with
// `extra` rules for what that code is (the body of a method, the code of an
// options handler).
export function commentSection(language: ProcessLanguage, extra: string[] = []): string[] {
  const functions = language === "bash"
    ? "- Before each helper function, a block of `#` comments, as the modules of DeBasher have: what the function does, and why when it is not obvious, then its arguments (`# $1 - ...`) and what it prints or returns."
    : language === "python"
      ? "- A docstring for each helper function and class: what it does, and why when it is not obvious."
      : "- Before each helper function, a comment: what it does, and why when it is not obvious.";
  return [
    COMMENT_SECTION_TITLE,
    "",
    "Comment the code for someone who did not write it:",
    "",
    functions,
    ...extra,
    COMMENT_STEPS,
    NO_REDUNDANT_COMMENTS,
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
