import { describe, expect, it } from "vitest";

import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import { optionLabelProblem, repeatedOptionLabels } from "./process";

function process(labels: string[]): ProgramProcess {
  return {
    id: "id-a",
    name: "a",
    description: "",
    position: { x: 0, y: 0 },
    options: labels.map((label, i) => createOption(`o${i}`, label)),
    optionsHandler: { mode: "standard" },
    language: "bash",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

describe("optionLabelProblem", () => {

  it("accepts a new label, and the option's own label when it is relabeled", () => {
    expect(optionLabelProblem(process(["-in"]), "-outf", "general")).toBeNull();
    expect(optionLabelProblem(process(["-in"]), " -in ", "general", "o0")).toBeNull();
  });

  it("refuses a label that another option has, ignoring the spaces around it", () => {
    expect(optionLabelProblem(process(["-in"]), " -in", "general")).toMatch(/already has an option labeled -in/);
  });

  it("tells labels apart by case, as the engine does", () => {
    expect(optionLabelProblem(process(["-in"]), "-IN", "general")).toBeNull();
  });

  it("refuses a label without a hyphen, and one of the Supervisor wiring in a resident program", () => {
    expect(optionLabelProblem(process([]), "in", "general")).toMatch(/has to start with "-"/);
    expect(optionLabelProblem(process([]), "-outhb", "resident")).toMatch(/Supervisor wiring/);
    expect(optionLabelProblem(process([]), "-outhb", "general")).toBeNull();
  });

});

describe("repeatedOptionLabels", () => {

  it("lists each label that more than one option has, once", () => {
    expect(repeatedOptionLabels(process(["-in", "-x", "-in", "-in"]))).toEqual(["-in"]);
    expect(repeatedOptionLabels(process(["-in", "-x"]))).toEqual([]);
  });

});
