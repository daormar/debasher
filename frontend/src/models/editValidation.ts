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

function findEditProblem(program: Program, edit: EditOp): string | null {

  const processById = (id: string) => program.processes.find(process => process.id === id);

  const takenNames = (exceptId?: string) =>
    [...program.processes, ...program.seqProcesses]
      .filter(member => member.id !== exceptId)
      .map(member => member.name);

  const missingProcess = (id: string) => `There is no process with id "${id}".`;

  const missingOption = (process: ProgramProcess, id: string) =>
    process.options.some(option => option.id === id)
      ? null
      : `Process "${process.name}" has no option with id "${id}".`;

  switch (edit.op) {

    case "addProcess": {
      if (processById(edit.process.id)) {
        return `A process with id "${edit.process.id}" already exists.`;
      }
      if (
        program.programType === "resident" &&
        edit.process.nodeKind === "Supervisor" &&
        hasSupervisor(program.processes)
      ) {
        return "This program already has a Supervisor: a program has at most one.";
      }
      return findProcessNameProblem(takenNames(), edit.process.name, program.programType);
    }

    case "removeProcess":
    case "moveProcess":
      return processById(edit.processId) ? null : missingProcess(edit.processId);

    case "updateProcess": {
      if (!processById(edit.processId)) {
        return missingProcess(edit.processId);
      }
      return (
        (edit.changes.name === undefined
          ? null
          : findProcessNameProblem(takenNames(edit.processId), edit.changes.name, program.programType)) ??
        findHandlerAndMethodsProblem(processById(edit.processId)!, edit.changes)
      );
    }

    case "addOption": {
      const process = processById(edit.processId);
      if (!process) {
        return missingProcess(edit.processId);
      }
      if (process.options.some(option => option.id === edit.option.id)) {
        return `Process "${process.name}" already has an option with id "${edit.option.id}".`;
      }
      return (
        findOptionLabelProblem(process, edit.option.label, program.programType) ??
        findOptionFieldsProblem(process, edit.option)
      );
    }

    case "updateOption": {
      const process = processById(edit.processId);
      if (!process) {
        return missingProcess(edit.processId);
      }
      const option = process.options.find(candidate => candidate.id === edit.optionId);
      return (
        missingOption(process, edit.optionId) ??
        (edit.changes.label === undefined
          ? null
          : findOptionLabelProblem(process, edit.changes.label, program.programType, edit.optionId)) ??
        findOptionFieldsProblem(process, { ...option!, ...edit.changes }) ??
        // A data type that the edit names, and that the option channel or
        // the connection of the option fixes to another; otherwise the
        // data type follows them (see normalizeDataTypes)
        (edit.changes.dataType === undefined
          ? null
          : findDataTypeProblem(program, process, { ...option!, ...edit.changes })) ??
        // A channel or a directory of a connected input other than those
        // that its connection gives it
        (edit.changes.channel === undefined && edit.changes.value === undefined
          ? null
          : findConnectedChannelProblem(program, process, { ...option!, ...edit.changes }))
      );
    }

    case "removeOption": {
      const process = processById(edit.processId);
      return process ? missingOption(process, edit.optionId) : missingProcess(edit.processId);
    }

    case "connect": {
      const { edge } = edit;
      if (program.edges.some(existing => existing.id === edge.id)) {
        return `An edge with id "${edge.id}" already exists.`;
      }
      const source = processById(edge.sourceProcessId);
      const target = processById(edge.targetProcessId);
      if (!source || !target) {
        return missingProcess(source ? edge.targetProcessId : edge.sourceProcessId);
      }
      const missing = missingOption(source, edge.sourceOptionId) ?? missingOption(target, edge.targetOptionId);
      if (missing) {
        return missing;
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
        const label = (process: ProgramProcess, optionId: string) =>
          process.options.find(option => option.id === optionId)!.label;
        return (
          `The connection from "${source.name}" ${label(source, edge.sourceOptionId)} to ` +
          `"${target.name}" ${label(target, edge.targetOptionId)} is not allowed by the ` +
          `rules of the connections.`
        );
      }
      return null;
    }

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
      // Only a resident program has a durability mode (see "The non-durable
      // mode" in doc/design_doc_resident.md)
      if (
        edit.changes.durability !== undefined &&
        edit.changes.durability !== "durable" &&
        program.programType !== "resident"
      ) {
        return "Only a resident program has a durability mode.";
      }
      return null;

    case "setEnvVar":
      return null;

  }

}

// Takes a process and one of its options; returns why the combination of
// the fields of the option makes no sense, or null. The editor of an option
// does not offer these combinations; script generation refuses them too,
// but for a flag on a channel and a subpath on a fanout family.
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
