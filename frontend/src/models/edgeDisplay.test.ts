import { describe, expect, it } from "vitest";

import type { ProgramEdge } from "./edge";
import { edgeDisplayActions } from "./edgeDisplay";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { createEmptyProgram } from "../storage/programStorage";

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

function edge(id: string, target: string, display?: "line" | "label"): ProgramEdge {
  return { id, sourceProcessId: "a", sourceOptionId: "a-out", targetProcessId: target, targetOptionId: `${target}-in`, display };
}

function programWith(edges: ProgramEdge[]): Program {
  return {
    ...createEmptyProgram("p"),
    processes: [
      process("a", [option("a-out", "-out")]),
      process("b", [option("b-in", "-in")]),
      process("c", [option("c-in", "-in")]),
    ],
    edges,
  };
}

const labels = (actions: ReturnType<typeof edgeDisplayActions>) => actions.map(action => action.label);

describe("edgeDisplayActions", () => {

  it("offers the other way of drawing a lone edge, and nothing for its output", () => {
    expect(edgeDisplayActions(programWith([edge("e1", "b")]), "e1")).toEqual([
      { label: "Show as label", edgeIds: ["e1"], display: "label" },
    ]);
    expect(labels(edgeDisplayActions(programWith([edge("e1", "b", "label")]), "e1"))).toEqual(["Show as line"]);
  });

  it("offers to draw every edge of the output one way when one of them is drawn the other", () => {
    const mixed = programWith([edge("e1", "b"), edge("e2", "c", "label")]);
    expect(edgeDisplayActions(mixed, "e1")).toEqual([
      { label: "Show as label", edgeIds: ["e1"], display: "label" },
      { label: "Show the 2 edges of a -out as labels", edgeIds: ["e1", "e2"], display: "label" },
      { label: "Show the 2 edges of a -out as lines", edgeIds: ["e1", "e2"], display: "line" },
    ]);
    const allLabels = programWith([edge("e1", "b", "label"), edge("e2", "c", "label")]);
    expect(labels(edgeDisplayActions(allLabels, "e2"))).toEqual(["Show as line", "Show the 2 edges of a -out as lines"]);
  });

  it("offers only the actions on the output from a source stub shared by several edges", () => {
    const allLabels = programWith([edge("e1", "b", "label"), edge("e2", "c", "label")]);
    expect(labels(edgeDisplayActions(allLabels, "e1", true))).toEqual(["Show the 2 edges of a -out as lines"]);
  });

  it("offers nothing for an edge that is not in the program", () => {
    expect(edgeDisplayActions(programWith([]), "wiring:hb:x")).toEqual([]);
  });

});
