import { describe, expect, it } from "vitest";

import { isValidEdge, listConnectionCandidates } from "./connections";
import type { ProgramEdge } from "./edge";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { createEmptyProgram } from "../storage/programStorage";

function option(id: string, label: string, fields: Partial<ProgramOption> = {}): ProgramOption {
  return {
    id,
    label,
    direction: label.startsWith("-out") ? "output" : "input",
    dataType: "string",
    channel: "none",
    mirror: false,
    description: "",
    value: "",
    commandLine: false,
    mandatory: false,
    fromProcessSpec: false,
    ...fields,
  };
}

function process(name: string, options: ProgramOption[]): ProgramProcess {
  return {
    id: name,
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

function processIn(mode: "standard" | "array", name: string, options: ProgramOption[]): ProgramProcess {
  return { ...process(name, options), optionsHandler: { mode } };
}

function edgeOf(source: string, sourceOption: string, target: string, targetOption: string) {
  return { sourceProcessId: source, sourceOptionId: sourceOption, targetProcessId: target, targetOptionId: targetOption };
}

function programWith(edges: ProgramEdge[] = []): Program {
  return {
    ...createEmptyProgram("p"),
    processes: [
      process("a", [option("a-outf", "-outf"), option("a-outq", "-outq", { channel: "fifo", value: "a_q" })]),
      process("b", [option("b-in", "-in"), option("b-flag", "-v", { dataType: "None" }), option("b-outf", "-outf")]),
    ],
    edges,
  };
}

describe("listConnectionCandidates", () => {

  it("lists the outputs an input can be connected to, named by process and option", () => {
    expect(listConnectionCandidates(programWith(), "b", "b-in")).toEqual([
      { sourceProcessId: "a", sourceOptionId: "a-outf", text: "a -outf" },
      { sourceProcessId: "a", sourceOptionId: "a-outq", text: "a -outq" },
    ]);
  });

  it("adds a writer of a shared directory to an input that it already feeds only for the same directory, whatever their subpaths", () => {
    const program: Program = {
      ...createEmptyProgram("p"),
      processes: [
        process("split", [
          option("split-outd", "-outd", { channel: "shared_dir", value: "data", subpath: "${task_idx}" }),
          option("split-outo", "-outo", { channel: "shared_dir", value: "other", subpath: "${task_idx}" }),
        ]),
        process("more", [option("more-outd", "-outd", { channel: "shared_dir", value: "data" })]),
        process("merge", [option("merge-ind", "-ind", { channel: "shared_dir", value: "data" })]),
      ],
      edges: [],
    };
    // An input not connected yet takes the directory of the output it reads
    expect(listConnectionCandidates(program, "merge", "merge-ind").map(candidate => candidate.text)).toEqual([
      "split -outd", "split -outo", "more -outd",
    ]);
    const fed = { ...program, edges: [{ id: "e1", ...edgeOf("more", "more-outd", "merge", "merge-ind") }] };
    expect(listConnectionCandidates(fed, "merge", "merge-ind")).toEqual([
      { sourceProcessId: "split", sourceOptionId: "split-outd", text: "split -outd" },
    ]);
  });

  it("follows the rules of an edge drawn on the canvas", () => {
    expect(listConnectionCandidates(programWith(), "b", "b-flag")).toEqual([]);
    const connected = programWith([
      { id: "e1", sourceProcessId: "a", sourceOptionId: "a-outf", targetProcessId: "b", targetOptionId: "b-in" },
    ]);
    expect(listConnectionCandidates(connected, "b", "b-in")).toEqual([]);
  });

});

describe("isValidEdge", () => {

  it("connects an input on a shared directory to several outputs that name the same directory", () => {
    const program: Program = {
      ...createEmptyProgram("p"),
      processes: [
        process("a", [option("a-outd", "-outd", { channel: "shared_dir", value: "data" })]),
        process("b", [option("b-outd", "-outd", { channel: "shared_dir", value: "data" })]),
        process("c", [
          option("c-ind", "-ind", { channel: "shared_dir", value: "data" }),
          option("c-in", "-in"),
        ]),
        process("d", [option("d-outf", "-outf"), option("d-outg", "-outg")]),
      ],
      edges: [
        { id: "e1", ...edgeOf("a", "a-outd", "c", "c-ind") },
        { id: "e2", ...edgeOf("d", "d-outf", "c", "c-in") },
      ],
    };
    expect(isValidEdge(program, edgeOf("b", "b-outd", "c", "c-ind"))).toBe(true);
    // Any other input takes one connection
    expect(isValidEdge(program, edgeOf("d", "d-outg", "c", "c-in"))).toBe(false);
  });

  it("connects no flag, which carries no data, to an input", () => {
    // Only a program edited by hand, or an edit refused to an agent, holds a
    // flag that is an output
    const program: Program = {
      ...createEmptyProgram("p"),
      processes: [
        process("a", [option("a-outx", "-outx", { dataType: "None" }), option("a-outf", "-outf")]),
        process("b", [option("b-in", "-in")]),
      ],
      edges: [],
    };
    expect(isValidEdge(program, edgeOf("a", "a-outx", "b", "b-in"))).toBe(false);
    expect(isValidEdge(program, edgeOf("a", "a-outf", "b", "b-in"))).toBe(true);
  });

  it("pairs a fanout family only with a process of several tasks, and never with another family", () => {
    const program: Program = {
      ...createEmptyProgram("p"),
      processes: [
        processIn("standard", "scatter", [option("scatter-outf", "-outf-ith")]),
        processIn("array", "work", [option("work-in", "-in"), option("work-outf", "-outf")]),
        processIn("standard", "plain", [option("plain-in", "-in"), option("plain-outf", "-outf")]),
        processIn("standard", "gather", [option("gather-in", "-in-ith")]),
      ],
      edges: [],
    };
    expect(isValidEdge(program, edgeOf("scatter", "scatter-outf", "work", "work-in"))).toBe(true);
    expect(isValidEdge(program, edgeOf("work", "work-outf", "gather", "gather-in"))).toBe(true);
    expect(isValidEdge(program, edgeOf("scatter", "scatter-outf", "plain", "plain-in"))).toBe(false);
    expect(isValidEdge(program, edgeOf("plain", "plain-outf", "gather", "gather-in"))).toBe(false);
    expect(isValidEdge(program, edgeOf("scatter", "scatter-outf", "gather", "gather-in"))).toBe(false);
  });

});
