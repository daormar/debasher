// @vitest-environment node
// Run without a DOM, which guards that the edits stay usable outside the
// browser.
import { describe, expect, it } from "vitest";

import type { Program } from "./program";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import { connect, disconnect, normalizeProgram, removeProcess, updateProcess } from "./programEdits";

function option(id: string, label: string): ProgramOption {
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
  };
}

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
    seqProcesses: [],
    processes: [process("a", [option("ao", "-outf")]), process("b", [option("bi", "-in")])],
    edges: [],
  };
}

const ab = { id: "e1", sourceProcessId: "id-a", sourceOptionId: "ao", targetProcessId: "id-b", targetOptionId: "bi" };

describe("the edits of a program", () => {

  it("leave the program they are given as it was", () => {
    const original = program();
    const snapshot = structuredClone(original);

    const connected = connect(original, ab);
    disconnect(connected, "e1");
    updateProcess(original, "id-a", { name: "renamed" });
    removeProcess(original, "id-a");

    expect(original).toEqual(snapshot);
  });

  it("connect and disconnect, with the reference in the target", () => {
    const connected = connect(program(), ab);
    expect(connected.processes[1].options[0].value).toBe("[a;-outf]");

    const disconnected = disconnect(connected, "e1");
    expect(disconnected.edges).toEqual([]);
    expect(disconnected.processes[1].options[0].value).toBe("");
  });

  it("leave the reference to normalizeProgram after a rename", () => {
    const renamed = updateProcess(connect(program(), ab), "id-a", { name: "producer" });
    expect(renamed.processes[1].options[0].value).toBe("[a;-outf]");

    expect(normalizeProgram(renamed).processes[1].options[0].value).toBe("[producer;-outf]");
  });

});
