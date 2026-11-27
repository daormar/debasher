import { describe, expect, it } from "vitest";

import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import { findOptionLabelProblem, listRepeatedOptionLabels } from "./process";

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

describe("findOptionLabelProblem", () => {

  it("accepts a new label, and the option's own label when it is relabeled", () => {
    expect(findOptionLabelProblem(process(["-in"]), "-outf", "general")).toBeNull();
    expect(findOptionLabelProblem(process(["-in"]), "-in", "general", "o0")).toBeNull();
  });

  it("refuses a label that another option has, ignoring the spaces around the other", () => {
    // Only a program edited by hand holds a label with spaces around it
    expect(findOptionLabelProblem(process([" -in"]), "-in", "general")).toMatch(/already has an option labeled -in/);
  });

  it("refuses a label with spaces around it", () => {
    expect(findOptionLabelProblem(process([]), " -in", "general")).toMatch(/has spaces around it/);
    expect(findOptionLabelProblem(process([]), "-in ", "general")).toMatch(/has spaces around it/);
  });

  it("tells labels apart by case, as the engine does", () => {
    expect(findOptionLabelProblem(process(["-in"]), "-IN", "general")).toBeNull();
  });

  it("refuses a label that the engine refuses, and one of the Supervisor wiring in a resident program", () => {
    // The engine takes "-" or "--" followed by an ASCII letter or an underscore
    for (const label of ["in", "-1n", "---x", "- x", "-é"]) {
      expect(findOptionLabelProblem(process([]), label, "general")).toMatch(/followed by an ASCII letter or an underscore/);
    }
    for (const label of ["-in", "--in", "-_x", "-Ax9"]) {
      expect(findOptionLabelProblem(process([]), label, "general")).toBeNull();
    }
    expect(findOptionLabelProblem(process([]), "-outhb", "resident")).toMatch(/Supervisor wiring/);
    expect(findOptionLabelProblem(process([]), "-outhb", "general")).toBeNull();
  });

});

describe("listRepeatedOptionLabels", () => {

  it("lists each label that more than one option has, once", () => {
    expect(listRepeatedOptionLabels(process(["-in", "-x", "-in", "-in"]))).toEqual(["-in"]);
    expect(listRepeatedOptionLabels(process(["-in", "-x"]))).toEqual([]);
  });

});
