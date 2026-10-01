import { RevisionConflict } from "../../src/api/revisionConflict";
import { validateEdits } from "../../src/models/editValidation";
import type { NodeInfo } from "../../src/models/node";
import type { ProcessInfo } from "../../src/models/process";
import type { Program } from "../../src/models/program";
import type { EditOp } from "../../src/models/programEdits";
import { applyEdit, applyEdits, dissolveGroups, groupsTouchedBy, normalizeProgram } from "../../src/models/programEdits";
import { nextFreePosition } from "../../src/models/programLayout";
import type { NamedEdit } from "../../src/models/programRefs";
import { resolveNamedEdits } from "../../src/models/programRefs";
import type { Backend } from "./backend";
import { describeChanges } from "./describe";

// An edit of a program from an agent, with the steps that the store takes
// and an answer in place of each of its dialogs (see "Edits from an agent"
// in doc/design_doc_webui.md).

// A call that the MCP server refuses, with the reason for the agent.
export class Refusal extends Error {}

// What an MCP tool answers: text for the model, and, for a proposal, the
// edits it stands for, as data for a client that applies them.
export interface Answer {
  text: string;
  structured?: Record<string, unknown>;
}

export interface EditCall {
  // Answer with a proposal, and save nothing.
  dryRun?: boolean;
  // Dissolve the groups of processes added with another program that the
  // edits touch, rather than refuse them.
  detachGroups?: boolean;
}

// The program saved in `homeDir`, as the store holds it once loaded.
export async function loadProgram(backend: Backend, homeDir: string): Promise<Program> {
  return normalizeProgram(await backend.loadProgram(homeDir));
}

/**
 * The named edits with what the library brings for each process that they
 * add, as the dialog that names a new process takes it: in a general
 * program, a process that a module of the preamble defines comes with its
 * description, options and code; in a resident program, a node that a module
 * defines comes with what that module brings, and any other name needs the
 * node kind of the new node.
 */
async function withLibrary(backend: Backend, program: Program, named: NamedEdit[]): Promise<NamedEdit[]> {

  const adds = named.filter(edit => edit.op === "addProcess" && !edit.info && !edit.nodeInfo);

  if (adds.length === 0) {
    return named;
  }

  const { preamble, envVars } = program;

  if (program.programType === "resident") {
    const suggested = new Set((await backend.suggestNodes(preamble, envVars).catch(() => [])).map(node => node.name));
    const nodeInfos = new Map<string, NodeInfo>();
    for (const edit of adds) {
      if (edit.op !== "addProcess" || edit.nodeKind) {
        continue;
      }
      if (!suggested.has(edit.name)) {
        throw new Refusal(
          `No module of the preamble defines a node named "${edit.name}": give the node kind of the new node.`
        );
      }
      nodeInfos.set(edit.name, await backend.getNodeInfo(preamble, envVars, edit.name));
    }
    return named.map(edit =>
      edit.op === "addProcess" && nodeInfos.has(edit.name) ? { ...edit, nodeInfo: nodeInfos.get(edit.name) } : edit
    );
  }

  const suggested = new Set(await backend.suggestProcessNames(preamble, envVars).catch(() => []));
  const infos = new Map<string, ProcessInfo | null>();
  for (const edit of adds) {
    if (edit.op === "addProcess" && suggested.has(edit.name)) {
      infos.set(edit.name, await backend.getProcessInfo(preamble, envVars, edit.name).catch(() => null));
    }
  }
  return named.map(edit =>
    edit.op === "addProcess" && infos.has(edit.name) ? { ...edit, info: infos.get(edit.name) } : edit
  );

}

// The names that the named edits give to a process or a sequential process.
function newNames(named: NamedEdit[]): string[] {
  return named.flatMap(edit => {
    switch (edit.op) {
      case "addProcess":
      case "addSeqProcess":
        return [edit.name];
      case "updateProcess":
      case "updateSeqProcess":
        return edit.changes.name === undefined ? [] : [edit.changes.name];
      default:
        return [];
    }
  });
}

// Refuses a name that the engine does not accept for a process, which only
// the backend can tell.
async function checkNamesWithEngine(backend: Backend, named: NamedEdit[]): Promise<void> {
  for (const name of new Set(newNames(named).map(name => name.trim()))) {
    if (!(await backend.validateProcessName(name))) {
      throw new Refusal(`"${name}" is not a valid process name for the engine.`);
    }
  }
}

/**
 * The edits with a position for each process added by a named edit that
 * gives none: where a process added to the program goes, each after the
 * ones before it.
 */
function placeAddedProcesses(program: Program, named: NamedEdit[], edits: EditOp[]): EditOp[] {
  let current = program;
  return edits.map((edit, index) => {
    const source = named[index];
    const placed = edit.op === "addProcess" && source.op === "addProcess" && !source.position
      ? { ...edit, process: { ...edit.process, position: nextFreePosition(current) } }
      : edit;
    current = applyEdit(current, placed);
    return placed;
  });
}

function groupList(groups: Map<string, string>): string {
  return [...new Set(groups.values())].map(name => `"${name}"`).join(", ");
}

/**
 * Applies the named edits to the program saved in `homeDir`, whole or not at
 * all, and saves it, naming the revision it was loaded with; or, with
 * `dryRun`, answers with the proposal of the edits and saves nothing.
 */
export async function editProgram(
  backend: Backend,
  homeDir: string,
  named: NamedEdit[],
  { dryRun = false, detachGroups = false }: EditCall
): Promise<Answer> {

  const program = await loadProgram(backend, homeDir);

  const enriched = await withLibrary(backend, program, named);
  await checkNamesWithEngine(backend, enriched);

  const resolution = resolveNamedEdits(program, enriched, () => crypto.randomUUID());
  if ("error" in resolution) {
    throw new Refusal(resolution.error);
  }

  const problems = validateEdits(program, resolution.edits);
  if (problems.length > 0) {
    throw new Refusal(["Nothing was changed. The edits break these rules:", ...problems.map(p => `- ${p}`)].join("\n"));
  }

  const edits = placeAddedProcesses(program, enriched, resolution.edits);

  const groups = groupsTouchedBy(program, edits);
  if (groups.size > 0 && !detachGroups) {
    throw new Refusal(
      `Nothing was changed. The edits change processes added with program ${groupList(groups)} ` +
      `("Add program"), which is generated as one add_debasher_program call. Changing them dissolves ` +
      "the whole group: each of its processes is then generated on its own. Call again with " +
      "detach_groups to do so."
    );
  }

  const edited = applyEdits(dissolveGroups(program, new Set(groups.keys())), edits);
  const changes = describeChanges(program, edited);
  const dissolved = groups.size > 0 ? `\nDissolves the groups of program ${groupList(groups)}.` : "";

  if (dryRun) {
    return {
      text: `Proposal, nothing saved. Changes:\n${changes}${dissolved}`,
      structured: { edits, dissolvedGroups: [...groups.keys()] },
    };
  }

  let revision: number;
  try {
    ({ revision } = await backend.saveProgram(edited, homeDir));
  } catch (err) {
    if (err instanceof RevisionConflict) {
      throw new Refusal(
        `Nothing was saved: ${err.message} Read the program again with get_program and make the edits again.`
      );
    }
    throw err;
  }

  return { text: `Saved (revision ${revision}). Changes:\n${changes}${dissolved}` };

}
