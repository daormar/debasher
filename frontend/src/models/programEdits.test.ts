// @vitest-environment node
// Run without a DOM, which guards that the edits stay usable outside the
// browser.
import { describe, expect, it } from "vitest";

import type { Program } from "./program";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import {
  addGroup,
  applyEdits,
  connect,
  disconnect,
  groupsTouchedBy,
  mergeRefusal,
  normalizeProgram,
  prepareMerge,
  removeProcess,
  updateProcess,
} from "./programEdits";
import { createSeqProcess } from "./seqProcess";

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

describe("Add program", () => {

  function counter() {
    let next = 0;
    return () => `new-${next++}`;
  }

  function other(): Program {
    return {
      ...program(),
      name: "other",
      processes: [
        { ...process("x", [option("xo", "-outf")]), position: { x: 40, y: 10 } },
        { ...process("y", [option("yi", "-in")]), position: { x: 90, y: 60 } },
      ],
      seqProcesses: [{ ...createSeqProcess("step"), id: "s1" }],
      edges: [{ id: "e9", sourceProcessId: "id-x", sourceOptionId: "xo", targetProcessId: "id-y", targetOptionId: "yi" }],
    };
  }

  it("refuses a name that the program has already, whatever its case", () => {
    const loaded = { ...other(), processes: [process("A", [])] };
    expect(mergeRefusal(program(), loaded)).toMatch(/named "A"/);
    expect(mergeRefusal(program(), other())).toBeNull();
  });

  it("brings in copies with new ids, as one group, to the right of the canvas", () => {
    const target = { ...program(), processes: [{ ...process("a", []), position: { x: 300, y: 0 } }] };

    const group = prepareMerge(target, other(), "/src/other", counter());

    const groupSource = { programName: "other", groupId: "new-0", groupSize: 3, sourceDir: "/src/other" };
    expect(group.processes.map(p => [p.name, p.id, p.position, p.groupSource])).toEqual([
      ["x", "new-1", { x: 520, y: 10 }, groupSource],
      ["y", "new-2", { x: 570, y: 60 }, groupSource],
    ]);
    expect(group.seqProcesses.map(s => [s.name, s.id, s.groupSource])).toEqual([["step", "new-3", groupSource]]);
    expect(group.edges).toEqual([
      { id: "new-4", sourceProcessId: "new-1", sourceOptionId: "xo", targetProcessId: "new-2", targetOptionId: "yi" },
    ]);
    expect(group.modDir).toBe("/src/other");
  });

  it("brings the nodes of a resident program one by one, loading nothing from where they came from", () => {
    const resident = (p: Program): Program => ({ ...p, programType: "resident", seqProcesses: [] });

    const group = prepareMerge(resident(program()), resident(other()), "/src/other", counter());

    expect(group.processes.every(p => p.groupSource === undefined)).toBe(true);
    expect(group.modDir).toBeNull();
  });

  it("adds the directory of the group to DEBASHER_MOD_DIR once", () => {
    const group = prepareMerge(program(), other(), "/src/other", counter());

    const once = addGroup({ ...program(), envVars: { DEBASHER_MOD_DIR: "/lib" } }, group);
    expect(once.envVars.DEBASHER_MOD_DIR).toBe("/lib:/src/other");
    expect(once.processes.map(p => p.name)).toEqual(["a", "b", "x", "y"]);

    expect(addGroup(once, group).envVars.DEBASHER_MOD_DIR).toBe("/lib:/src/other");
  });

});

describe("edits as data", () => {

  it("are applied one after another, then normalized", () => {
    const edited = applyEdits(program(), [
      { op: "connect", edge: ab },
      { op: "updateProcess", processId: "id-a", changes: { name: "producer" } },
      { op: "moveProcess", processId: "id-b", position: { x: 3, y: 4 } },
    ]);

    expect(edited.processes[0].name).toBe("producer");
    expect(edited.processes[1].position).toEqual({ x: 3, y: 4 });
    expect(edited.processes[1].options[0].value).toBe("[producer;-outf]");
  });

  it("touch the group of what they change, and nothing when they only move or connect out of it", () => {
    const groupSource = { programName: "other", groupId: "g1", groupSize: 1, sourceDir: "/src" };
    const grouped = { ...program(), edges: [ab] };
    grouped.processes = grouped.processes.map(p => p.name === "b" ? { ...p, groupSource } : p);
    const touched = (ops: Parameters<typeof groupsTouchedBy>[1]) => [...groupsTouchedBy(grouped, ops).keys()];

    expect(touched([{ op: "moveProcess", processId: "id-b", position: { x: 0, y: 0 } }])).toEqual([]);
    expect(touched([{ op: "updateProcess", processId: "id-a", changes: { code: "x" } }])).toEqual([]);
    expect(touched([{ op: "updateProcess", processId: "id-b", changes: { code: "x" } }])).toEqual(["g1"]);
    expect(touched([{ op: "disconnect", edgeId: "e1" }])).toEqual(["g1"]);
    expect(touched([{ op: "removeOption", processId: "id-b", optionId: "bi" }])).toEqual(["g1"]);
    expect(touched([{ op: "setProgramFields", changes: { name: "renamed" } }])).toEqual([]);
  });

});
