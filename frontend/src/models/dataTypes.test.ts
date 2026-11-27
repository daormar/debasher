// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { ProgramOption } from "./option";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { isValidEdge } from "./connections";
import { getFixedDataType, normalizeDataTypes, receivesPath } from "./dataTypes";
import { normalizeProgram } from "./programEdits";
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
    expect(getFixedDataType(p, "id-adder", optionOf(p, "adder", "sums"))).toBe("dir");
    expect(getFixedDataType(p, "id-adder", optionOf(p, "adder", "outd"))).toBe("dir");
    expect(getFixedDataType(p, "id-adder", optionOf(p, "adder", "inf"))).toBe("int");
    expect(getFixedDataType(p, "id-adder", optionOf(p, "adder", "n"))).toBeNull();
    expect(getFixedDataType(p, "id-counter", optionOf(p, "counter", "outf"))).toBeNull();
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

describe("the channel of a connected input", () => {

  // reader has an input on a FIFO of its own, and another that names the
  // shared directory "sums"
  function withReader(): Program {
    const p = program();
    return {
      ...p,
      processes: [
        ...p.processes,
        process("reader", [
          createOption("in", "-in", { dataType: "int", channel: "fifo", value: "in" }),
          createOption("sums", "-sums", { dataType: "dir", channel: "shared_dir", value: "sums" }),
        ]),
      ],
    };
  }

  const edge = (sourceProcessId: string, sourceOptionId: string, targetOptionId: string) => ({
    sourceProcessId, sourceOptionId, targetProcessId: "id-reader", targetOptionId,
  });

  it("connects an input on a channel of its own, which the connection replaces", () => {
    const p = withReader();
    expect(isValidEdge(p, edge("id-counter", "outf", "in"))).toBe(true);
    expect(isValidEdge(p, edge("id-counter", "outf", "sums"))).toBe(true);
    const edits = [
      { op: "connect" as const, edge: { id: "e2", ...edge("id-counter", "outf", "in") } },
      { op: "connect" as const, edge: { id: "e3", ...edge("id-counter", "outf", "sums") } },
    ];
    // An agent is not refused either
    expect(validateEdits(p, edits)).toEqual([]);
    const connected = applyEdits(p, edits);
    for (const id of ["in", "sums"]) {
      expect(optionOf(connected, "reader", id).channel).toBe("none");
      expect(optionOf(connected, "reader", id).value).toBe("[counter;-outf]");
    }
  });

  it("tells an agent that a resident program connects only an input on the channel \"none\"", () => {
    // The connection makes it a business input; an input on a FIFO of its
    // own is an external input
    const p: Program = {
      ...withReader(),
      programType: "resident",
      processes: [
        process("counter", [createOption("outf", "-outf", { dataType: "int", channel: "fifo" })]),
        process("reader", [createOption("in", "-in", { dataType: "int", channel: "fifo", value: "in", fifoTag: "external" })]),
      ],
      edges: [],
    };
    expect(validateEdits(p, [{ op: "connect", edge: { id: "e2", ...edge("id-counter", "outf", "in") } }])).toEqual([
      'Option "-in" of process "reader" uses the channel "fifo": in a resident program a connection reaches only ' +
      'an input on the channel "none", which it makes a business input.',
    ]);
  });

  it("refuses an edit that gives a connected input another channel or directory than its connection, and takes it on an input that is not connected", () => {
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "inf", changes: { channel: "fifo", value: "inf" } },
    ])).toEqual([
      'Option "-inf" of process "adder" reads "-outf" of process "counter", so its channel is "none", ' +
      'which the connection gives it, not "fifo". Leave channel and value out of the edit, or disconnect the input first.',
    ]);
    expect(validateEdits(program(), [
      { op: "updateOption", processId: "id-adder", optionId: "n", changes: { channel: "fifo", value: "n" } },
    ])).toEqual([]);
    const connected = applyEdits(withReader(), [{ op: "connect", edge: { id: "e2", ...edge("id-adder", "sums", "sums") } }]);
    expect(validateEdits(connected, [
      { op: "updateOption", processId: "id-reader", optionId: "sums", changes: { value: "other" } },
    ])).toEqual([
      'Option "-sums" of process "reader" reads "-out-sums" of process "adder", so it names the shared ' +
      'directory "sums", which the connection gives it, not "other". Leave channel and value out of the edit, or disconnect the input first.',
    ]);
  });

  it("moves a connected input that metadata put on such a channel to the channel \"none\"", () => {
    const p = withReader();
    const broken: Program = {
      ...p,
      processes: p.processes.map(candidate => candidate.name !== "reader" ? candidate : {
        ...candidate,
        // A subpath too, which script generation refuses on the channel "none"
        options: candidate.options.map(option => ({ ...option, fifoTag: "external" as const, mirror: true, subpath: "sub" })),
      }),
      edges: [
        ...p.edges,
        { id: "e2", ...edge("id-counter", "outf", "in") },
        { id: "e3", ...edge("id-counter", "outf", "sums") },
      ],
    };
    const normalized = normalizeProgram(broken);
    for (const id of ["in", "sums"]) {
      const option = optionOf(normalized, "reader", id);
      expect(option.channel).toBe("none");
      expect(option.value).toBe("[counter;-outf]");
      expect(option.fifoTag).toBeUndefined();
      expect(option.mirror).toBe(false);
      expect(option.subpath).toBeUndefined();
    }
    expect(normalizeProgram(normalized)).toEqual(normalized);
  });

  it("keeps a shared directory input on the directory of the output it reads, with its own subpath", () => {
    const p = withReader();
    const connected = applyEdits(p, [{ op: "connect", edge: { id: "e2", ...edge("id-adder", "sums", "sums") } }]);
    const withSubpath = applyEdits(connected, [
      { op: "updateOption", processId: "id-reader", optionId: "sums", changes: { subpath: "3" } },
    ]);
    const renamed = applyEdits({ ...withSubpath, sharedDirs: ["sums", "totals"] }, [
      { op: "updateOption", processId: "id-adder", optionId: "sums", changes: { value: "totals" } },
    ]);
    expect(optionOf(renamed, "reader", "sums").channel).toBe("shared_dir");
    expect(optionOf(renamed, "reader", "sums").value).toBe("totals");
    expect(optionOf(renamed, "reader", "sums").subpath).toBe("3");
  });

  it("leaves the input of a fanout family that reads a shared directory on the channel \"none\"", () => {
    // It reads each task of the process at the other end, which script
    // generation writes only on "none"
    const p: Program = {
      ...program(),
      processes: [
        { ...process("split", [createOption("outd", "-outd", { dataType: "dir", channel: "shared_dir", value: "sums" })]), optionsHandler: { mode: "array" } },
        process("merge", [createOption("ind", "-ind-ith", { dataType: "dir" })]),
      ],
      edges: [],
    };
    const connected = applyEdits(p, [
      { op: "connect", edge: { id: "e1", sourceProcessId: "id-split", sourceOptionId: "outd", targetProcessId: "id-merge", targetOptionId: "ind" } },
    ]);
    expect(optionOf(connected, "merge", "ind").channel).toBe("none");
    expect(optionOf(connected, "merge", "ind").value).toBe("[split;-outd]");
  });

  it("keeps a shared directory input in step when the output it reads leaves the shared directory", () => {
    const p = withReader();
    const connected = applyEdits(p, [{ op: "connect", edge: { id: "e2", ...edge("id-adder", "sums", "sums") } }]);
    expect(optionOf(connected, "reader", "sums").channel).toBe("shared_dir");
    const moved = applyEdits(connected, [
      { op: "updateOption", processId: "id-adder", optionId: "sums", changes: { channel: "none", value: "" } },
    ]);
    expect(optionOf(moved, "reader", "sums").channel).toBe("none");
    expect(optionOf(moved, "reader", "sums").value).toBe("[adder;-out-sums]");
  });

});
