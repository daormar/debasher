// @vitest-environment node
import { describe, expect, it } from "vitest";

import { validateEdits } from "./editValidation";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { applyEdits } from "./programEdits";
import type { NamedEdit } from "./programRefs";
import { resolveNamedEdits } from "./programRefs";
import { createSeqProcess } from "./seqProcess";

function process(name: string, labels: string[]): ProgramProcess {
  return {
    id: `id-${name}`,
    name,
    description: "",
    position: { x: 0, y: 0 },
    options: labels.map(label => createOption(`${name}${label}`, label)),
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
    seqProcesses: [createSeqProcess("step", "s-step")],
    processes: [process("a", ["-outf"]), process("b", ["-in", "-x"])],
    edges: [],
  };
}

function counter() {
  let next = 0;
  return () => `new-${next++}`;
}

function resolved(named: NamedEdit[], from: Program = program()) {
  const resolution = resolveNamedEdits(from, named, counter());
  if ("error" in resolution) {
    throw new Error(resolution.error);
  }
  return resolution.edits;
}

describe("resolveNamedEdits", () => {

  it("names processes by name and options by label, with no id in sight", () => {
    const edits = resolved([
      { op: "connect", from: { process: "a", option: "-outf" }, to: { process: "b", option: "-in" } },
    ]);

    expect(edits).toEqual([{
      op: "connect",
      edge: { id: "new-0", sourceProcessId: "id-a", sourceOptionId: "a-outf", targetProcessId: "id-b", targetOptionId: "b-in" },
    }]);
  });

  it("lets an edit name what an earlier one added", () => {
    const named: NamedEdit[] = [
      { op: "addProcess", name: "c", options: [{ label: "-in" }, { label: "-n", commandLine: true }] },
      { op: "connect", from: { process: "a", option: "-outf" }, to: { process: "c", option: "-in" } },
      { op: "updateProcess", process: "c", changes: { name: "sink", code: "echo" } },
    ];

    const edits = resolved(named);
    const edited = applyEdits(program(), edits);

    expect(validateEdits(program(), edits)).toEqual([]);
    const sink = edited.processes.find(p => p.name === "sink")!;
    expect(sink.code).toBe("echo");
    expect(sink.options.map(o => [o.label, o.direction, o.commandLine])).toEqual([
      ["-in", "input", false],
      ["-n", "input", true],
    ]);
    expect(sink.options[0].value).toBe("[a;-outf]");
  });

  it("resolves the count source of a fanout family by its label", () => {
    const [edit] = resolved([
      { op: "addProcess", name: "c", options: [{ label: "-w", commandLine: true }, { label: "-outfith", countSource: "-w" }] },
    ]);

    if (edit.op !== "addProcess") {
      throw new Error(edit.op);
    }
    const [count, family] = edit.process.options;
    expect(family.countSourceOptionId).toBe(count.id);
  });

  it("gives a relabeled option the direction of its new label", () => {
    const [edit] = resolved([{ op: "updateOption", process: "b", option: "-x", changes: { label: "-outx" } }]);

    expect(edit).toEqual({ op: "updateOption", processId: "id-b", optionId: "b-x", changes: { label: "-outx", direction: "output" } });
  });

  it("finds an edge by its two ends to remove it", () => {
    const connected = applyEdits(program(), resolved([
      { op: "connect", from: { process: "a", option: "-outf" }, to: { process: "b", option: "-in" } },
    ]));

    const edits = resolved(
      [{ op: "disconnect", from: { process: "a", option: "-outf" }, to: { process: "b", option: "-in" } }],
      connected
    );

    expect(edits).toEqual([{ op: "disconnect", edgeId: "new-0" }]);
  });

  it("edits the sequential processes one by one", () => {
    const edits = resolved([
      { op: "addSeqProcess", name: "extra" },
      { op: "updateSeqProcess", name: "step", changes: { description: "first" } },
      { op: "removeSeqProcess", name: "extra" },
    ]);

    const edited = applyEdits(program(), edits);
    expect(edited.seqProcesses.map(s => [s.name, s.description])).toEqual([["step", "first"]]);
  });

  it("reports the first name that matches nothing, with the position of its edit", () => {
    const resolution = resolveNamedEdits(program(), [
      { op: "moveProcess", process: "a", position: { x: 1, y: 1 } },
      { op: "removeOption", process: "b", option: "-nope" },
      { op: "removeProcess", process: "ghost" },
    ], counter());

    expect(resolution).toEqual({ error: "Edit 2 (removeOption): Process \"b\" has no option labeled -nope." });
  });

  it("refuses to pick one of two options with the same label", () => {
    const repeated = program();
    repeated.processes[1].options.push(createOption("dup", "-in"));

    const resolution = resolveNamedEdits(repeated, [{ op: "removeOption", process: "b", option: "-in" }], counter());

    expect(resolution).toEqual({ error: expect.stringMatching(/more than one option labeled -in/) });
  });

  it("refuses a connection that does not exist", () => {
    const resolution = resolveNamedEdits(program(), [
      { op: "disconnect", from: { process: "a", option: "-outf" }, to: { process: "b", option: "-in" } },
    ], counter());

    expect(resolution).toEqual({ error: expect.stringMatching(/no connection from "a" -outf to "b" -in/) });
  });

});
