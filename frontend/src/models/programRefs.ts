import type { ProgramEdge } from "./edge";
import type { NodeInfo, NodeKind } from "./node";
import type { ProgramOption } from "./option";
import { createOption, getOptionDirection } from "./option";
import type { Position } from "./position";
import type { ProcessInfo, ProgramProcess } from "./process";
import { createProcess } from "./process";
import type { ExecutionOptions, Program } from "./program";
import type { EditOp, OptionChanges, ProcessChanges, ProgramFields } from "./programEdits";
import { applyEdit } from "./programEdits";
import type { SeqProcess } from "./seqProcess";
import { createSeqProcess, withSeqProcessChanges } from "./seqProcess";

// Edits written with names instead of ids, as an agent writes them: a process
// or a sequential process by its name, an option by its process and its
// label, and an edge by its two ends. resolveNamedEdits turns them into edits
// (see programEdits.ts), giving new ids to what they add. It only resolves
// names: whether the edits are allowed is for validateEdits. A named edit
// gives, of a field that holds an object, such as the computational
// specifications of a process, only what it changes.

// One end of an edge: a process and the label of one of its options.
export interface OptionRef {
  process: string;
  option: string;
}

// The fields of an option that a named edit sets: its label and direction
// are given apart, and the option whose value gives the count of a fanout
// family is named by its label.
export type NamedOptionFields = Omit<OptionChanges, "label" | "direction" | "countSourceOptionId"> & {
  countSource?: string;
};

// The fields of a process that hold an object, of which a named edit gives
// only the fields that it changes: the rest keep their values.
const NESTED_PROCESS_FIELDS = [
  "optionsHandler",
  "computationalSpecs",
  "additionalSpecs",
  "additionalMethods",
  "nodeCode",
] as const;

type NestedProcessField = typeof NESTED_PROCESS_FIELDS[number];

// What a named edit may change in a process: its options, position and
// group are changed by edits of their own.
export type NamedProcessChanges =
  Omit<ProcessChanges, "options" | "position" | "groupSource" | NestedProcessField> &
  { [Field in NestedProcessField]?: Partial<NonNullable<ProgramProcess[Field]>> };

// The same for a sequential process, whose name is given apart.
const NESTED_SEQ_PROCESS_FIELDS = ["computationalSpecs", "additionalSpecs"] as const;

type NestedSeqProcessField = typeof NESTED_SEQ_PROCESS_FIELDS[number];

export type NamedSeqProcessChanges =
  Partial<Omit<SeqProcess, "id" | "name" | "groupSource" | NestedSeqProcessField>> &
  { [Field in NestedSeqProcessField]?: Partial<SeqProcess[Field]> };

// `changes` with each of the `fields` that hold an object merged into the
// value that `current` holds.
function withNestedFields<T extends object>(
  current: T,
  changes: object,
  fields: readonly (keyof T)[]
): Partial<T> {
  const merged: Partial<T> = { ...changes };
  for (const field of fields) {
    const change = (changes as Partial<T>)[field];
    if (change !== undefined) {
      merged[field] = { ...current[field], ...change };
    }
  }
  return merged;
}

// The fields of the program that a named edit sets.
export type NamedProgramFields = Omit<ProgramFields, "executionOptions"> & {
  executionOptions?: Partial<ExecutionOptions>;
};

export type NamedEdit =
  | { op: "setProgramFields"; changes: NamedProgramFields }
  | { op: "setEnvVar"; name: string; value: string }
  | {
      op: "addProcess";
      name: string;
      // What the library brings for the name, or, in a resident program,
      // the node kind of the new process or what the module that defines
      // the node brings (see createProcess).
      info?: ProcessInfo | null;
      nodeKind?: NodeKind;
      nodeInfo?: NodeInfo;
      changes?: NamedProcessChanges;
      options?: ({ label: string } & NamedOptionFields)[];
      position?: Position;
    }
  | { op: "removeProcess"; process: string }
  | { op: "moveProcess"; process: string; position: Position }
  | { op: "updateProcess"; process: string; changes: NamedProcessChanges }
  | { op: "addOption"; process: string; label: string; fields?: NamedOptionFields }
  | { op: "updateOption"; process: string; option: string; changes: NamedOptionFields & { label?: string } }
  | { op: "removeOption"; process: string; option: string }
  | { op: "connect"; from: OptionRef; to: OptionRef }
  | { op: "disconnect"; from: OptionRef; to: OptionRef }
  | { op: "addSeqProcess"; name: string; changes?: NamedSeqProcessChanges }
  | { op: "updateSeqProcess"; name: string; changes: NamedSeqProcessChanges & { name?: string } }
  | { op: "removeSeqProcess"; name: string };

export type Resolution = { edits: EditOp[] } | { error: string };

class NameError extends Error {}

function processNamed(program: Program, name: string): ProgramProcess {
  const process = program.processes.find(candidate => candidate.name === name);
  if (!process) {
    throw new NameError(`There is no process named "${name}".`);
  }
  return process;
}

function optionLabeled(process: ProgramProcess, label: string): ProgramOption {
  const matches = process.options.filter(option => option.label.trim() === label.trim());
  if (matches.length === 0) {
    throw new NameError(`Process "${process.name}" has no option labeled ${label}.`);
  }
  if (matches.length > 1) {
    throw new NameError(
      `Process "${process.name}" has more than one option labeled ${label}: relabel them in the editor first.`
    );
  }
  return matches[0];
}

function seqProcessNamed(program: Program, name: string): SeqProcess {
  const seqProcess = program.seqProcesses.find(candidate => candidate.name === name);
  if (!seqProcess) {
    throw new NameError(`There is no sequential process named "${name}".`);
  }
  return seqProcess;
}

// The fields of an option with the count source named by its label resolved
// to the id of that option of `process`.
function optionFields(process: ProgramProcess | null, fields: NamedOptionFields): OptionChanges {
  const { countSource, ...rest } = fields;
  if (countSource === undefined) {
    return rest;
  }
  if (!process) {
    throw new NameError(`The count source ${countSource} names an option of a process that does not exist yet.`);
  }
  return { ...rest, countSourceOptionId: optionLabeled(process, countSource).id };
}

function edgeBetween(program: Program, from: OptionRef, to: OptionRef): ProgramEdge {
  const source = processNamed(program, from.process);
  const target = processNamed(program, to.process);
  const sourceOption = optionLabeled(source, from.option);
  const targetOption = optionLabeled(target, to.option);
  const edge = program.edges.find(candidate =>
    candidate.sourceProcessId === source.id &&
    candidate.sourceOptionId === sourceOption.id &&
    candidate.targetProcessId === target.id &&
    candidate.targetOptionId === targetOption.id
  );
  if (!edge) {
    throw new NameError(
      `There is no connection from "${from.process}" ${from.option} to "${to.process}" ${to.option}.`
    );
  }
  return edge;
}

function seqProcessWithChanges(seqProcess: SeqProcess, changes: NamedSeqProcessChanges): SeqProcess {
  return withSeqProcessChanges(seqProcess, withNestedFields(seqProcess, changes, NESTED_SEQ_PROCESS_FIELDS));
}

function resolveOne(program: Program, named: NamedEdit, newId: () => string): EditOp {
  switch (named.op) {

    case "setProgramFields":
      return { op: "setProgramFields", changes: withNestedFields(program, named.changes, ["executionOptions"]) };

    case "setEnvVar":
      return named;

    case "addProcess": {
      const process = createProcess(
        newId(), named.name, { info: named.info, nodeKind: named.nodeKind, nodeInfo: named.nodeInfo }, newId
      );
      const namedOptions = named.options ?? [];
      const created = namedOptions.map(({ label }) => createOption(newId(), label));
      const draft: ProgramProcess = {
        ...process,
        ...withNestedFields(process, named.changes ?? {}, NESTED_PROCESS_FIELDS),
        position: named.position ?? process.position,
        options: [...process.options, ...created],
      };
      // The fields go in once every option exists, so that a count source
      // may name an option added with it.
      const options = draft.options.map(option => {
        const index = created.indexOf(option);
        if (index === -1) {
          return option;
        }
        const { label: _label, ...fields } = namedOptions[index];
        return { ...option, ...optionFields(draft, fields) };
      });
      return { op: "addProcess", process: { ...draft, options } };
    }

    case "removeProcess":
      return { op: "removeProcess", processId: processNamed(program, named.process).id };

    case "moveProcess":
      return { op: "moveProcess", processId: processNamed(program, named.process).id, position: named.position };

    case "updateProcess": {
      const process = processNamed(program, named.process);
      return {
        op: "updateProcess",
        processId: process.id,
        changes: withNestedFields(process, named.changes, NESTED_PROCESS_FIELDS),
      };
    }

    case "addOption": {
      const process = processNamed(program, named.process);
      const option = createOption(newId(), named.label, optionFields(process, named.fields ?? {}));
      return { op: "addOption", processId: process.id, option };
    }

    case "updateOption": {
      const process = processNamed(program, named.process);
      const option = optionLabeled(process, named.option);
      const { label, ...fields } = named.changes;
      const changes = optionFields(process, fields);
      return {
        op: "updateOption",
        processId: process.id,
        optionId: option.id,
        // A new label brings the direction that follows from it.
        changes: label === undefined ? changes : { ...changes, label, direction: getOptionDirection(label) },
      };
    }

    case "removeOption": {
      const process = processNamed(program, named.process);
      return { op: "removeOption", processId: process.id, optionId: optionLabeled(process, named.option).id };
    }

    case "connect": {
      const source = processNamed(program, named.from.process);
      const target = processNamed(program, named.to.process);
      return {
        op: "connect",
        edge: {
          id: newId(),
          sourceProcessId: source.id,
          sourceOptionId: optionLabeled(source, named.from.option).id,
          targetProcessId: target.id,
          targetOptionId: optionLabeled(target, named.to.option).id,
        },
      };
    }

    case "disconnect":
      return { op: "disconnect", edgeId: edgeBetween(program, named.from, named.to).id };

    case "addSeqProcess":
      return {
        op: "setSeqProcesses",
        seqProcesses: [
          ...program.seqProcesses,
          seqProcessWithChanges(createSeqProcess(named.name, newId()), named.changes ?? {}),
        ],
      };

    case "updateSeqProcess": {
      const seqProcess = seqProcessNamed(program, named.name);
      return {
        op: "setSeqProcesses",
        seqProcesses: program.seqProcesses.map(candidate =>
          candidate === seqProcess ? seqProcessWithChanges(candidate, named.changes) : candidate
        ),
      };
    }

    case "removeSeqProcess": {
      const seqProcess = seqProcessNamed(program, named.name);
      return {
        op: "setSeqProcesses",
        seqProcesses: program.seqProcesses.filter(candidate => candidate !== seqProcess),
      };
    }

  }
}

/**
 * The edits that the named edits stand for in `program`, each resolved
 * against the program that the edits before it leave, so that an edit may
 * name what an earlier one added; or the first name that matches nothing,
 * with the position of its edit.
 */
export function resolveNamedEdits(program: Program, named: NamedEdit[], newId: () => string): Resolution {
  const edits: EditOp[] = [];
  let current = program;
  for (const [index, namedEdit] of named.entries()) {
    try {
      const edit = resolveOne(current, namedEdit, newId);
      edits.push(edit);
      current = applyEdit(current, edit);
    } catch (err) {
      if (err instanceof NameError) {
        return { error: `Edit ${index + 1} (${namedEdit.op}): ${err.message}` };
      }
      throw err;
    }
  }
  return { edits };
}
