// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { ProgramOption } from "./option";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { createSeqProcess } from "./seqProcess";
import { validateEdits } from "./editValidation";

function process(name: string, options: ProgramOption[]): ProgramProcess {
  return {
    id: `id-${name}`,
    name,
    description: "",
    position: { x: 0, y: 0 },
    options,
    optionsHandler: { mode: "standard" },
    language: "bash",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

function program(): Program {
  return {
    id: "p",
    name: "p",
    programType: "general",
    description: "",
    preamble: "",
    envVars: {},
    homeDir: "",
    outputDir: "",
    sourceDir: "",
    executionOptions: { scheduler: "BUILTIN" },
    programOptions: {},
    sharedDirs: [],
    availableSharedDirs: [],
    seqProcesses: [createSeqProcess("step")],
    processes: [
      process("a", [createOption("ao", "-outf"), createOption("ai", "-in")]),
      process("b", [createOption("bi", "-in")]),
    ],
    edges: [],
  };
}

const edge = (id: string, source: [string, string], target: [string, string]) => ({
  id,
  sourceProcessId: `id-${source[0]}`,
  sourceOptionId: source[1],
  targetProcessId: `id-${target[0]}`,
  targetOptionId: target[1],
});

describe("validateEdits", () => {

  it("accepts edits that the editor allows", () => {
    expect(validateEdits(program(), [
      { op: "addProcess", process: process("c", [createOption("ci", "-in")]) },
      { op: "connect", edge: edge("e1", ["a", "ao"], ["c", "ci"]) },
      { op: "updateProcess", processId: "id-c", changes: { name: "sink" } },
    ])).toEqual([]);
  });

  it("refuses a name that a process or a sequential process has, whatever its case", () => {
    expect(validateEdits(program(), [{ op: "addProcess", process: process("A", []) }]))
      .toEqual(["A process with this name already exists."]);
    expect(validateEdits(program(), [{ op: "updateProcess", processId: "id-b", changes: { name: "Step" } }]))
      .toEqual(["A process with this name already exists."]);
  });

  it("refuses a connection that the rules of the connections forbid", () => {
    const [problem] = validateEdits(program(), [
      { op: "connect", edge: edge("e1", ["a", "ao"], ["b", "bi"]) },
      { op: "connect", edge: edge("e2", ["a", "ao"], ["b", "bi"]) },
    ]);
    expect(problem).toMatch(/"a" -outf to "b" -in is not allowed/);
  });

  it("refuses a cycle with no fifo in it", () => {
    const withAB = { ...program(), processes: [...program().processes] };
    withAB.processes[1] = process("b", [createOption("bi", "-in"), createOption("bo", "-outb")]);
    expect(validateEdits(withAB, [
      { op: "connect", edge: edge("e1", ["a", "ao"], ["b", "bi"]) },
      { op: "connect", edge: edge("e2", ["b", "bo"], ["a", "ai"]) },
    ])).toHaveLength(1);
  });

  it("refuses an option label that does not start with a hyphen, and missing references", () => {
    expect(validateEdits(program(), [
      { op: "addOption", processId: "id-a", option: createOption("x", "bad") },
      { op: "removeOption", processId: "id-a", optionId: "nope" },
      { op: "disconnect", edgeId: "nope" },
      { op: "moveProcess", processId: "nope", position: { x: 0, y: 0 } },
      { op: "setEdgeDisplay", edgeIds: ["nope2"], display: "label" },
    ])).toEqual([
      '"bad" is not an option label: it has to start with "-".',
      'Process "a" has no option with id "nope".',
      'There is no edge with id "nope".',
      'There is no process with id "nope".',
      'There is no edge with id "nope2".',
    ]);
  });

  it("refuses a label that another option of the process has", () => {
    expect(validateEdits(program(), [
      { op: "addOption", processId: "id-a", option: createOption("x", "-in") },
      { op: "updateOption", processId: "id-a", optionId: "ai", changes: { label: "-outf" } },
      { op: "updateOption", processId: "id-a", optionId: "ai", changes: { label: "-in" } },
    ])).toEqual([
      'Process "a" already has an option labeled -in.',
      'Process "a" already has an option labeled -outf.',
    ]);
  });

  it("refuses the combinations of the fields of an option that make no sense", () => {
    expect(validateEdits(program(), [
      { op: "addOption", processId: "id-a", option: createOption("x", "-outn", { direction: "output", fromProcessSpec: true, value: "cpus" }) },
      { op: "addOption", processId: "id-a", option: createOption("y", "-ind", { channel: "process_outdir" }) },
      { op: "addOption", processId: "id-a", option: createOption("z", "-outs", { direction: "output", subpath: "${task_idx}" }) },
      { op: "addOption", processId: "id-a", option: createOption("w", "-outd", { direction: "output", channel: "process_outdir", subpath: "${task_idx}" }) },
    ])).toEqual([
      'Option "-outn" of process "a" is an output, which cannot take its value from the process specifications.',
      'Option "-ind" of process "a" uses the channel "process_outdir", which only an output can use.',
      'Option "-outs" of process "a" has a subpath, which only the channels "shared_dir" and "process_outdir" take.',
    ]);
  });

});
