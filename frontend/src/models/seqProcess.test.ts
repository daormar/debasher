import { describe, expect, it } from "vitest";

import {
  aliasOptMapFromText,
  aliasOptMapToText,
  createSeqProcess,
  seqProcessesProblem,
} from "./seqProcess";

describe("seqProcessesProblem", () => {

  it("accepts sequential processes with names of their own", () => {
    expect(seqProcessesProblem([createSeqProcess("a"), createSeqProcess("b")], ["worker"])).toBeNull();
  });

  it("refuses a blank name", () => {
    expect(seqProcessesProblem([createSeqProcess("  ")], [])).toMatch(/no name/);
  });

  it("refuses the name of a process", () => {
    expect(seqProcessesProblem([createSeqProcess("worker")], ["worker"])).toMatch(/name of a process/);
  });

  it("refuses two sequential processes with one name", () => {
    expect(seqProcessesProblem([createSeqProcess("a"), createSeqProcess("a")], [])).toMatch(/Two/);
  });

  it("refuses an alias together with an external alias", () => {
    const both = { ...createSeqProcess("a"), additionalSpecs: { alias: "b", externalAlias: "b.py" } };
    expect(seqProcessesProblem([both], [])).toMatch(/only one/);
  });

});

describe("the option map of an alias as text", () => {

  it("goes to text and back", () => {
    const mappings = [{ fromLabel: "-a", toLabel: "-b" }, { fromLabel: "-c", toLabel: "-d" }];
    expect(aliasOptMapToText(mappings)).toBe("-a:-b,-c:-d");
    expect(aliasOptMapFromText("-a:-b, -c:-d,")).toEqual(mappings);
  });

});
