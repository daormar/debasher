import { describe, expect, it } from "vitest";
import type { ProgramOption } from "./option";
import {
  isBusinessInputCandidate,
  isBusinessOutput,
  isRequiredHook,
  isReservedNodeOptionLabel,
  nodeClassName,
  nodeNameProblem,
} from "./node";

function option(label: string, fields: Partial<ProgramOption> = {}): ProgramOption {
  return {
    id: label,
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

describe("nodeClassName", () => {
  it("names the class after the process, in CamelCase, as the engine does", () => {
    expect(nodeClassName("counter")).toBe("Counter");
    expect(nodeClassName("org.ns.count_words")).toBe("OrgNsCountWords");
    expect(nodeClassName("count__words_")).toBe("CountWords");
    expect(nodeClassName("fanIn")).toBe("FanIn");
  });
});

describe("nodeNameProblem", () => {
  it("refuses a name whose class hides a class of the runtime library", () => {
    expect(nodeNameProblem("supervisor")).toMatch(/runtime library/);
    expect(nodeNameProblem("program_launcher")).toMatch(/runtime library/);
  });

  it("refuses a name whose class hides a Python builtin", () => {
    expect(nodeNameProblem("type_error")).toMatch(/Python builtin/);
    expect(nodeNameProblem("exception")).toMatch(/Python builtin/);
  });

  it("accepts any other name", () => {
    expect(nodeNameProblem("counter")).toBeNull();
    expect(nodeNameProblem("sup")).toBeNull();
  });
});

describe("the options of a node", () => {
  it("reserves the labels of the Supervisor wiring", () => {
    expect(isReservedNodeOptionLabel("-outhb")).toBe(true);
    expect(isReservedNodeOptionLabel(" -trigger ")).toBe(true);
    expect(isReservedNodeOptionLabel("-outf")).toBe(false);
  });

  it("tells a business output: an output through a FIFO with no tag", () => {
    expect(isBusinessOutput(option("-outf", { channel: "fifo" }))).toBe(true);
    expect(isBusinessOutput(option("-outf"))).toBe(false);
    expect(isBusinessOutput(option("-inf", { channel: "fifo", fifoTag: "external" }))).toBe(false);
  });

  it("tells an input that a connection can make a business input", () => {
    expect(isBusinessInputCandidate(option("-inf"))).toBe(true);
    expect(isBusinessInputCandidate(option("-inf", { channel: "fifo", fifoTag: "external" }))).toBe(false);
    expect(isBusinessInputCandidate(option("-n", { commandLine: true }))).toBe(false);
    expect(isBusinessInputCandidate(option("-c", { fromProcessSpec: true, value: "cpus" }))).toBe(false);
    expect(isBusinessInputCandidate(option("-verbose", { dataType: "None" }))).toBe(false);
    expect(isBusinessInputCandidate(option("-outf", { channel: "fifo" }))).toBe(false);
  });
});

describe("isRequiredHook", () => {
  it("requires the first four hooks of an FBPProcess, and none of a node whose class implements them", () => {
    expect(isRequiredHook("FBPProcess", "processData")).toBe(true);
    expect(isRequiredHook("FBPProcess", "initializeRuntime")).toBe(true);
    expect(isRequiredHook("FBPProcess", "observe")).toBe(false);
    expect(isRequiredHook("ProgramLauncher", "processData")).toBe(false);
    expect(isRequiredHook("DirectoryWatcher", "captureNodeState")).toBe(false);
  });
});
