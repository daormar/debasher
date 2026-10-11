// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { ProgramOption } from "./option";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { fixedDataType, normalizeDataTypes, receivesPath } from "./dataTypes";
import { applyEdits } from "./programEdits";
import { validateEdits } from "./editValidation";

function process(name: string, options: ProgramOption[], language: ProgramProcess["language"] = "bash"): ProgramProcess {
  return {
    id: `id-${name}`,
    name,
    description: "",
    position: { x: 0, y: 0 },
    options,
    optionsHandler: { mode: "standard" },
    language,
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

// counter writes ints into a FIFO that adder reads; adder also keeps what it
// adds in a shared directory and in its process output directory
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
    sharedDirs: ["sums"],
    availableSharedDirs: [],
    seqProcesses: [],
    processes: [
      process("counter", [createOption("outf", "-outf", { dataType: "int", channel: "fifo" })]),
      process("adder", [
        createOption("inf", "-inf", { dataType: "string" }),
        createOption("sums", "-out-sums", { dataType: "file", channel: "shared_dir", value: "sums" }),
        createOption("outd", "-out-dir", { dataType: "string", channel: "process_outdir" }),
        createOption("n", "-n", { dataType: "float" }),
      ], "python"),
    ],
    edges: [{ id: "e", sourceProcessId: "id-counter", sourceOptionId: "outf", targetProcessId: "id-adder", targetOptionId: "inf" }],
  };
}

const optionOf = (p: Program, processName: string, id: string) =>
  p.processes.find(candidate => candidate.name === processName)!.options.find(o => o.id === id)!;

describe("data types", () => {

  it("fixes the data type of a directory channel and of a connected input, and leaves the others free", () => {
    const p = program();
    expect(fixedDataType(p, "id-adder", optionOf(p, "adder", "sums"))).toBe("dir");
    expect(fixedDataType(p, "id-adder", optionOf(p, "adder", "outd"))).toBe("dir");
    expect(fixedDataType(p, "id-adder", optionOf(p, "adder", "inf"))).toBe("int");
    expect(fixedDataType(p, "id-adder", optionOf(p, "adder", "n"))).toBeNull();
    expect(fixedDataType(p, "id-counter", optionOf(p, "counter", "outf"))).toBeNull();
  });

  it("brings a program in line with the fixed data types, and leaves alone one that already is", () => {
    const normalized = normalizeDataTypes(program());
    expect(optionOf(normalized, "adder", "inf").dataType).toBe("int");
    expect(optionOf(normalized, "adder", "sums").dataType).toBe("dir");
    expect(optionOf(normalized, "adder", "outd").dataType).toBe("dir");
    expect(optionOf(normalized, "adder", "n").dataType).toBe("float");
    expect(normalizeDataTypes(normalized)).toBe(normalized);
  });

  it("keeps a connected input in step with the output it reads", () => {
    const edited = applyEdits(program(), [
      { op: "updateOption", processId: "id-counter", optionId: "outf", changes: { dataType: "float" } },
    ]);
    expect(optionOf(edited, "adder", "inf").dataType).toBe("float");
  });

  it("refuses an edit that names a data type other than the fixed one, and takes one that names none", () => {
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "inf", changes: { dataType: "string" } },
    ])).toEqual([
      'Option "-inf" of process "adder" reads "-outf" of process "counter", whose data type is "int": it carries the same data, so its data type is "int", not "string".',
    ]);
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "sums", changes: { dataType: "int" } },
    ])).toEqual([
      'Option "-out-sums" of process "adder" uses the channel "shared_dir", which names a directory: its data type is "dir", not "int".',
    ]);
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "inf", changes: { dataType: "int" } },
      { op: "updateOption", processId: "id-adder", optionId: "n", changes: { channel: "process_outdir" } },
    ])).toEqual(['Option "-n" of process "adder" uses the channel "process_outdir", which only an output can use.']);
  });

  it("refuses a flag on a channel", () => {
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "n", changes: { dataType: "None", channel: "fifo" } },
    ])).toEqual(['Option "-n" of process "adder" is a flag, which carries no data, and so no channel but "none".']);
  });

  it("tells when a process receives a path instead of the data", () => {
    const p = program();
    const adder = p.processes[1];
    expect(receivesPath(p, adder, optionOf(p, "adder", "inf"))).toBe(true);
    expect(receivesPath(p, adder, optionOf(p, "adder", "sums"))).toBe(true);
    expect(receivesPath(p, adder, optionOf(p, "adder", "n"))).toBe(false);

    // Bash reads the value of a value descriptor, not its path
    const withDescriptor: Program = {
      ...p,
      processes: [
        process("counter", [createOption("outf", "-outf", { dataType: "int", channel: "value_desc" })]),
        process("adder", [createOption("inf", "-inf", { dataType: "int" })]),
      ],
    };
    const bashAdder = withDescriptor.processes[1];
    expect(receivesPath(withDescriptor, bashAdder, optionOf(withDescriptor, "adder", "inf"))).toBe(false);
    const pythonAdder = { ...bashAdder, language: "python" } as ProgramProcess;
    expect(receivesPath(withDescriptor, pythonAdder, optionOf(withDescriptor, "adder", "inf"))).toBe(true);
  });

});
