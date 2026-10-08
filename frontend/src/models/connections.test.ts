import { describe, expect, it } from "vitest";

import { connectionCandidates } from "./connections";
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

describe("connectionCandidates", () => {

  it("lists the outputs an input can be connected to, named by process and option", () => {
    expect(connectionCandidates(programWith(), "b", "b-in")).toEqual([
      { sourceProcessId: "a", sourceOptionId: "a-outf", text: "a -outf" },
      { sourceProcessId: "a", sourceOptionId: "a-outq", text: "a -outq" },
    ]);
  });

  it("follows the rules of an edge drawn on the canvas", () => {
    expect(connectionCandidates(programWith(), "b", "b-flag")).toEqual([]);
    const connected = programWith([
      { id: "e1", sourceProcessId: "a", sourceOptionId: "a-outf", targetProcessId: "b", targetOptionId: "b-in" },
    ]);
    expect(connectionCandidates(connected, "b", "b-in")).toEqual([]);
  });

});
