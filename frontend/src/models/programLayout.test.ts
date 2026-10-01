// @vitest-environment node
import { describe, expect, it } from "vitest";

import type { ProgramEdge } from "./edge";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { layoutProcesses, nextFreePosition } from "./programLayout";

function process(name: string, x = 0): ProgramProcess {
  return {
    id: name,
    name,
    description: "",
    position: { x, y: 0 },
    options: [],
    optionsHandler: { mode: "standard" },
    language: "bash",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

function edge(source: string, target: string): ProgramEdge {
  return { id: `${source}-${target}`, sourceProcessId: source, sourceOptionId: "o", targetProcessId: target, targetOptionId: "i" };
}

function program(processes: ProgramProcess[], edges: ProgramEdge[] = []): Program {
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
    processes,
    edges,
  };
}

function positions(laidOut: Program) {
  return Object.fromEntries(laidOut.processes.map(p => [p.name, p.position]));
}

describe("layoutProcesses", () => {

  it("places a process below the processes that feed it, by the depth of its connections", () => {
    const laidOut = layoutProcesses(program(
      [process("sink"), process("a"), process("b"), process("c")],
      [edge("a", "b"), edge("b", "sink"), edge("a", "sink"), edge("c", "b")]
    ));

    expect(positions(laidOut)).toEqual({
      a: { x: 100, y: 100 },
      c: { x: 320, y: 100 },
      b: { x: 100, y: 260 },
      sink: { x: 100, y: 420 },
    });
  });

  it("keeps a process with a self-loop in its layer, above the process it feeds", () => {
    const y = positions(layoutProcesses(program(
      [process("counter"), process("sink")],
      [edge("counter", "counter"), edge("counter", "sink")]
    )));

    expect(y.counter.y).toBeLessThan(y.sink.y);
    expect(y.counter.y).toBe(100);
  });

  it("ends with some layering for a cycle", () => {
    const laidOut = layoutProcesses(program(
      [process("a"), process("b")],
      [edge("a", "b"), edge("b", "a")]
    ));

    expect(laidOut.processes.every(p => Number.isFinite(p.position.y))).toBe(true);
  });

  it("leaves the program it is given as it was", () => {
    const original = program([process("a"), process("b")], [edge("a", "b")]);
    const snapshot = structuredClone(original);

    layoutProcesses(original);

    expect(original).toEqual(snapshot);
  });

});

describe("nextFreePosition", () => {

  it("is to the right of the rightmost process, or where the first one goes", () => {
    expect(nextFreePosition(program([]))).toEqual({ x: 100, y: 100 });
    expect(nextFreePosition(program([process("a", 40), process("b", 300)]))).toEqual({ x: 520, y: 100 });
  });

});
