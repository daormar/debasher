import { isValidEdge } from "./connections";
import { findConnectedChannelProblem, findDataTypeProblem } from "./dataTypes";
import { hasSupervisor } from "./node";
import type { ProgramOption } from "./option";
import { DIRECTORY_CHANNELS } from "./option";
import type { ProgramProcess } from "./process";
import { findOptionLabelProblem, findProcessNameProblem } from "./process";
import type { Program } from "./program";
import type { EditOp, ProcessChanges } from "./programEdits";
import { applyEdit } from "./programEdits";
import { seqProcessesProblem } from "./seqProcess";

// The checks that the dialogs and the canvas of the editor make before an
// edit, gathered for code that builds edits without them (a tool that edits
// a program outside the browser): the same rules, from the same functions.
// What only the backend can tell, whether the engine accepts the name of a
// process, is not checked here.

/**
 * The problems of applying the edits one after another to `program`, each
 * checked against the program the edits before it leave, or an empty list
 * when there are none.
 */
export function validateEdits(program: Program, edits: EditOp[]): string[] {

  const problems: string[] = [];
  let current = program;

  for (const edit of edits) {
    const problem = findEditProblem(current, edit);
    if (problem) {
      problems.push(problem);
    } else {
      current = applyEdit(current, edit);
    }
  }

  return problems;

}

// The edit of one kind, as EditOp names it.
type EditOf<Op extends EditOp["op"]> = Extract<EditOp, { op: Op }>;

// Takes a program and an edit; returns why the edit cannot be applied to
// the program, or null. Each kind of edit has its own check.
function findEditProblem(program: Program, edit: EditOp): string | null {

  switch (edit.op) {

    case "addProcess":
      return findAddProcessProblem(program, edit);

    case "removeProcess":
    case "moveProcess":
      return findProcess(program, edit.processId) ? null : describeMissingProcess(edit.processId);

    case "updateProcess":
      return findUpdateProcessProblem(program, edit);

    case "addOption":
      return findAddOptionProblem(program, edit);

    case "updateOption":
      return findUpdateOptionProblem(program, edit);

    case "removeOption": {
      const process = findProcess(program, edit.processId);
      return process ? findMissingOptionProblem(process, edit.optionId) : describeMissingProcess(edit.processId);
    }

    case "connect":
      return findConnectProblem(program, edit);

    case "disconnect":
      return program.edges.some(edge => edge.id === edit.edgeId)
        ? null
        : `There is no edge with id "${edit.edgeId}".`;

    case "setEdgeDisplay": {
      const missing = edit.edgeIds.find(edgeId => !program.edges.some(edge => edge.id === edgeId));
      return missing === undefined ? null : `There is no edge with id "${missing}".`;
    }

    case "setSeqProcesses":
      return seqProcessesProblem(edit.seqProcesses, program.processes.map(process => process.name));

    // What "Add program" brings is checked before the edit is built (see
    // findMergeRefusal).
    case "addGroup":
      return null;

    case "setProgramFields":
      return findSetProgramFieldsProblem(program, edit);

    case "setEnvVar":
      return null;

  }

}

// Takes a program and the id of a process; returns the process, or
// undefined.
function findProcess(program: Program, id: string): ProgramProcess | undefined {
  return program.processes.find(process => process.id === id);
}

// Takes a program and, optionally, the id of a process or sequential
// process to leave out; returns the names that the others take.
function listTakenNames(program: Program, exceptId?: string): string[] {
  return [...program.processes, ...program.seqProcesses]
    .filter(member => member.id !== exceptId)
    .map(member => member.name);
}

// Takes the id of a process; returns the problem that it names no process.
function describeMissingProcess(id: string): string {
  return `There is no process with id "${id}".`;
}

// Takes a process and the id of an option; returns the problem that the
// process has no option with that id, or null when it has.
function findMissingOptionProblem(process: ProgramProcess, id: string): string | null {
  return process.options.some(option => option.id === id)
    ? null
    : `Process "${process.name}" has no option with id "${id}".`;
}

// Takes a program and an "addProcess" edit; returns why it cannot be
// applied, or null: an id already taken, a second Supervisor, or a name
// that the editor refuses.
function findAddProcessProblem(program: Program, edit: EditOf<"addProcess">): string | null {
  if (findProcess(program, edit.process.id)) {
    return `A process with id "${edit.process.id}" already exists.`;
  }
  if (
    program.programType === "resident" &&
    edit.process.nodeKind === "Supervisor" &&
    hasSupervisor(program.processes)
  ) {
    return "This program already has a Supervisor: a program has at most one.";
  }
  return findProcessNameProblem(listTakenNames(program), edit.process.name, program.programType);
}

// Takes a program and an "updateProcess" edit; returns why it cannot be
// applied, or null: a missing process, a name that the editor refuses, or
// an options handler or methods that script generation refuses.
function findUpdateProcessProblem(program: Program, edit: EditOf<"updateProcess">): string | null {
  const process = findProcess(program, edit.processId);
  if (!process) {
    return describeMissingProcess(edit.processId);
  }
  return (
    (edit.changes.name === undefined
      ? null
      : findProcessNameProblem(listTakenNames(program, edit.processId), edit.changes.name, program.programType)) ??
    findHandlerAndMethodsProblem(process, edit.changes)
  );
}

// Takes a program and an "addOption" edit; returns why it cannot be
// applied, or null: a missing process, an id already taken, a label that
// the editor refuses, or fields that make no sense together.
function findAddOptionProblem(program: Program, edit: EditOf<"addOption">): string | null {
  const process = findProcess(program, edit.processId);
  if (!process) {
    return describeMissingProcess(edit.processId);
  }
  if (process.options.some(option => option.id === edit.option.id)) {
    return `Process "${process.name}" already has an option with id "${edit.option.id}".`;
  }
  return (
    findOptionLabelProblem(process, edit.option.label, program.programType) ??
    findOptionFieldsProblem(process, edit.option)
  );
}

// Takes a program and an "updateOption" edit; returns why it cannot be
// applied, or null: a missing process or option, a label that the editor
// refuses, fields that make no sense together, a data type that the
// channel or the connection fixes to another, or a channel or directory
// of a connected input other than those of its connection.
function findUpdateOptionProblem(program: Program, edit: EditOf<"updateOption">): string | null {
  const process = findProcess(program, edit.processId);
  if (!process) {
    return describeMissingProcess(edit.processId);
  }
  const option = process.options.find(candidate => candidate.id === edit.optionId);
  if (!option) {
    return findMissingOptionProblem(process, edit.optionId);
  }
  const changed = { ...option, ...edit.changes };
  return (
    (edit.changes.label === undefined
      ? null
      : findOptionLabelProblem(process, edit.changes.label, program.programType, edit.optionId)) ??
    findOptionFieldsProblem(process, changed) ??
    // Otherwise the data type follows them (see normalizeDataTypes)
    (edit.changes.dataType === undefined ? null : findDataTypeProblem(program, process, changed)) ??
    (edit.changes.channel === undefined && edit.changes.value === undefined
      ? null
      : findConnectedChannelProblem(program, process, changed))
  );
}

// Takes a program and a "connect" edit; returns why it cannot be applied,
// or null: an id already taken, a missing process or option, a flag as the
// source, an input of a resident program on another channel than "none",
// or a connection that the rules of the canvas refuse (isValidEdge).
function findConnectProblem(program: Program, edit: EditOf<"connect">): string | null {
  const { edge } = edit;
  if (program.edges.some(existing => existing.id === edge.id)) {
    return `An edge with id "${edge.id}" already exists.`;
  }
  const source = findProcess(program, edge.sourceProcessId);
  const target = findProcess(program, edge.targetProcessId);
  if (!source || !target) {
    return describeMissingProcess(source ? edge.targetProcessId : edge.sourceProcessId);
  }
  const missing =
    findMissingOptionProblem(source, edge.sourceOptionId) ??
    findMissingOptionProblem(target, edge.targetOptionId);
  if (missing) {
    return missing;
  }
  // A flag carries no data; only a program edited by hand holds one that
  // is an output
  const sourceOption = source.options.find(option => option.id === edge.sourceOptionId)!;
  if (sourceOption.dataType === "None") {
    return (
      `Option "${sourceOption.label}" of process "${source.name}" is a flag, which carries no data and feeds no input: ` +
      "give it another data type, or a label that does not start with -out or --out, before connecting it."
    );
  }
  // A resident program takes a connection only into an input on "none",
  // which the connection makes a business input
  const targetOption = target.options.find(option => option.id === edge.targetOptionId)!;
  if (program.programType === "resident" && targetOption.direction === "input" && targetOption.channel !== "none") {
    return (
      `Option "${targetOption.label}" of process "${target.name}" uses the channel "${targetOption.channel}": ` +
      'in a resident program a connection reaches only an input on the channel "none", which it makes a business input.'
    );
  }
  if (!isValidEdge(program, edge)) {
    return (
      `The connection from "${source.name}" ${sourceOption.label} to ` +
      `"${target.name}" ${targetOption.label} is not allowed by the ` +
      `rules of the connections.`
    );
  }
  return null;
}

// Takes a program and a "setProgramFields" edit; returns why it cannot be
// applied, or null: only a resident program has a durability mode (see
// "The non-durable mode" in doc/design_doc_resident.md).
function findSetProgramFieldsProblem(program: Program, edit: EditOf<"setProgramFields">): string | null {
  if (
    edit.changes.durability !== undefined &&
    edit.changes.durability !== "durable" &&
    program.programType !== "resident"
  ) {
    return "Only a resident program has a durability mode.";
  }
  return null;
}

// Takes a process and one of its options; returns why the combination of
// the fields of the option makes no sense, or null. The editor of an option
// does not offer these combinations; script generation refuses them too,
// but for a flag on a channel and a flag that is an output.
function findOptionFieldsProblem(process: ProgramProcess, option: ProgramOption): string | null {
  const where = `Option "${option.label}" of process "${process.name}"`;
  if (option.direction === "output" && option.fromProcessSpec) {
    return `${where} is an output, which cannot take its value from the process specifications.`;
  }
  if (option.direction !== "output" && option.channel === "process_outdir") {
    return `${where} uses the channel "process_outdir", which only an output can use.`;
  }
  if (option.channel === "value_desc" && !/^--?out/.test(option.label)) {
    return `${where} uses the channel "value_desc", which only an output, labeled -out* or --out*, can use.`;
  }
  if (option.dataType === "None" && option.direction === "output") {
    return `${where} is a flag, which carries no data, and so is an input: its label cannot start with -out or --out.`;
  }
  if (option.dataType === "None" && option.channel !== "none") {
    return `${where} is a flag, which carries no data, and so no channel but "none".`;
  }
  if (option.subpath && !DIRECTORY_CHANNELS.has(option.channel)) {
    return `${where} has a subpath, which only the channels "shared_dir" and "process_outdir" take.`;
  }
  return null;
}

// The combinations of the options handler and of the additional methods of
// a process that script generation refuses: a manual handler in Python,
// whose code is a Bash function, and Conda environments or Docker images
// given both as data and as the body of their method. Each says what to
// change.
function findHandlerAndMethodsProblem(process: ProgramProcess, changes: ProcessChanges): string | null {

  const handler = changes.optionsHandler;
  if (handler && handler.mode === "manual" && handler.language === "python") {
    return `The options handler of "${process.name}" is in manual mode, whose code is a Bash function, and in Python: set optionsHandler.language to bash, or use the array or generator mode for a Python tasks file.`;
  }

  const methods = changes.additionalMethods;
  if (!methods) {
    return null;
  }
  for (const [list, body, what, field, key] of [
    [methods.condaEnvs, methods.condaEnvsCode, "Conda environments", "condaEnvs", "condaEnvsCode"],
    [methods.dockerImgs, methods.dockerImgsCode, "Docker images", "dockerImgs", "dockerImgsCode"],
  ] as const) {
    if (list?.length && body?.trim()) {
      return `"${process.name}" gives its ${what} both as data (${field}) and as a body (${key}): give one of them, with the other empty.`;
    }
  }
  return null;

}
