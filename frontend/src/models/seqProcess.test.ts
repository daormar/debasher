import { describe, expect, it } from "vitest";

import {
  aliasOptMapFromText,
  aliasOptMapToText,
  createSeqProcess,
  definesBashFunction,
  seqProcessesProblem,
  withSeqProcessChanges,
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

describe("the code of a sequential process", () => {

  it("follows a rename while it is still the code it started with", () => {
    const step = createSeqProcess("step1");
    expect(withSeqProcessChanges(step, { name: "addone" }).code).toBe("addone()\n{\n    :\n}");
  });

  it("is kept on a rename once it was written", () => {
    const step = { ...createSeqProcess("step1"), code: "step1()\n{\n    echo hi\n}" };
    expect(withSeqProcessChanges(step, { name: "addone" }).code).toBe(step.code);
  });

  it("starts empty in another language", () => {
    expect(withSeqProcessChanges(createSeqProcess("step1"), { language: "python" }).code).toBe("");
  });

  it("is refused in Bash when it defines no function of the name", () => {
    const step = { ...createSeqProcess("addone"), code: "step1()\n{\n    :\n}" };
    expect(seqProcessesProblem([step], [])).toMatch(/does not define a function "addone"/);
  });

  it("is not checked for an alias", () => {
    const alias = { ...createSeqProcess("a"), code: "", additionalSpecs: { alias: "b" } };
    expect(seqProcessesProblem([alias], [])).toBeNull();
  });

  it("recognizes the forms of a Bash function, a namespaced name included", () => {
    expect(definesBashFunction("ns.step()\n{\n :\n}", "ns.step")).toBe(true);
    expect(definesBashFunction("function step {\n :\n}", "step")).toBe(true);
    expect(definesBashFunction("function step()\n{\n :\n}", "step")).toBe(true);
    expect(definesBashFunction("nsXstep()\n{\n :\n}", "ns.step")).toBe(false);
    expect(definesBashFunction("stepper()\n{\n :\n}", "step")).toBe(false);
  });

});
