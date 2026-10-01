import { isValidEdge } from "./connections";
import { hasSupervisor } from "./node";
import type { ProgramProcess } from "./process";
import { optionLabelProblem, processNameProblem } from "./process";
import type { Program } from "./program";
import type { EditOp } from "./programEdits";
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
      return edit.changes.name === undefined
        ? null
        : processNameProblem(takenNames(edit.processId), edit.changes.name, program.programType);
    }

    case "addOption": {
      const process = processById(edit.processId);
      if (!process) {
        return missingProcess(edit.processId);
      }
      if (process.options.some(option => option.id === edit.option.id)) {
        return `Process "${process.name}" already has an option with id "${edit.option.id}".`;
      }
      return optionLabelProblem(process, edit.option.label, program.programType);
    }

    case "updateOption": {
      const process = processById(edit.processId);
      if (!process) {
        return missingProcess(edit.processId);
      }
      return (
        missingOption(process, edit.optionId) ??
        (edit.changes.label === undefined
          ? null
          : optionLabelProblem(process, edit.changes.label, program.programType, edit.optionId))
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
