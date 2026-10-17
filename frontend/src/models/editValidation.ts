import { isValidEdge } from "./connections";
import { connectedChannelProblem, connectedInputChannelProblem, dataTypeProblem } from "./dataTypes";
import { hasSupervisor } from "./node";
import type { ProgramOption } from "./option";
import { DIRECTORY_CHANNELS } from "./option";
import type { ProgramProcess } from "./process";
import { optionLabelProblem, processNameProblem } from "./process";
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
    const problem = editProblem(current, edit);
    if (problem) {
      problems.push(problem);
    } else {
      current = applyEdit(current, edit);
    }
  }

  return problems;

}

function editProblem(program: Program, edit: EditOp): string | null {

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
      return processNameProblem(takenNames(), edit.process.name, program.programType);
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
          : processNameProblem(takenNames(edit.processId), edit.changes.name, program.programType)) ??
        pythonFilesProblem(processById(edit.processId)!, edit.changes)
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
        optionLabelProblem(process, edit.option.label, program.programType) ??
        optionFieldsProblem(process, edit.option)
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
          : optionLabelProblem(process, edit.changes.label, program.programType, edit.optionId)) ??
        optionFieldsProblem(process, { ...option!, ...edit.changes }) ??
        // A data type that the edit names, and that the option channel or
        // the connection of the option fixes to another; otherwise the
        // data type follows them (see normalizeDataTypes)
        (edit.changes.dataType === undefined
          ? null
          : dataTypeProblem(program, process, { ...option!, ...edit.changes })) ??
        // A channel that would hide the connection of a connected input
        (edit.changes.channel === undefined
          ? null
          : connectedChannelProblem(program, process, { ...option!, ...edit.changes }))
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
      const sourceOption = source.options.find(option => option.id === edge.sourceOptionId)!;
      const targetOption = target.options.find(option => option.id === edge.targetOptionId)!;
      const channelProblem =
        sourceOption.direction === "output" && targetOption.direction === "input"
          ? connectedInputChannelProblem(target, targetOption, source, sourceOption)
          : null;
      if (channelProblem) {
        return channelProblem;
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
    // mergeRefusal).
    case "addGroup":
      return null;

    case "setProgramFields":
    case "setEnvVar":
      return null;

  }

}

// The combinations of the fields of an option that make no sense, which the
// editor of an option does not offer and script generation refuses.
function optionFieldsProblem(process: ProgramProcess, option: ProgramOption): string | null {
  const where = `Option "${option.label}" of process "${process.name}"`;
  if (option.direction === "output" && option.fromProcessSpec) {
    return `${where} is an output, which cannot take its value from the process specifications.`;
  }
  if (option.direction !== "output" && option.channel === "process_outdir") {
    return `${where} uses the channel "process_outdir", which only an output can use.`;
  }
  if (option.dataType === "None" && option.channel !== "none") {
    return `${where} is a flag, which carries no data, and so no channel but "none".`;
  }
  if (option.subpath && !DIRECTORY_CHANNELS.has(option.channel)) {
    return `${where} has a subpath, which only the channels "shared_dir" and "process_outdir" take.`;
  }
  return null;
}

// An edit of the code that a process keeps in a Python function file, its
// tasks file or its skip file, which the edit would fill with code of
// another kind, and an edit of the body of the conda_envs or docker_imgs
// method of a process that gives them as data, which script generation
// would refuse: each names the way that does change it.
function pythonFilesProblem(process: ProgramProcess, changes: ProcessChanges): string | null {

  const handler = changes.optionsHandler;
  const oldHandler = process.optionsHandler;
  if (
    handler &&
    oldHandler.language === "python" &&
    (handler.language ?? "python") === "python" &&
    handler.mode !== "standard" &&
    (handler.mode !== oldHandler.mode ||
      handler.arrayCode !== oldHandler.arrayCode ||
      handler.generatorSizeCode !== oldHandler.generatorSizeCode)
  ) {
    const path = process.files?.tasks || `${process.name}_tasks.py`;
    return `The options handler of "${process.name}" is the Python tasks file ${path}, which defines tasks(run): change that file with write_program_file, not its mode or code here.`;
  }

  const methods = changes.additionalMethods;
  if (!methods) {
    return null;
  }
  const oldMethods = process.additionalMethods;
  if (
    oldMethods.skipLanguage === "python" &&
    (methods.skipLanguage ?? "python") === "python" &&
    methods.skipCode !== oldMethods.skipCode
  ) {
    const path = process.files?.methods?.skip || `${process.name}_skip.py`;
    return `The skip method of "${process.name}" is the Python skip file ${path}, which defines skip(task): change that file with write_program_file.`;
  }
  for (const [list, body, oldBody, what, key] of [
    [methods.condaEnvs ?? oldMethods.condaEnvs, methods.condaEnvsCode, oldMethods.condaEnvsCode, "Conda environments", "conda_envs"],
    [methods.dockerImgs ?? oldMethods.dockerImgs, methods.dockerImgsCode, oldMethods.dockerImgsCode, "Docker images", "docker_imgs"],
  ] as const) {
    if (list?.length && body && body !== oldBody) {
      return `"${process.name}" gives its ${what} as a list, under ${key} in program.yaml: change them there, or remove that key before giving the body of the method.`;
    }
  }
  return null;

}
