import { describe, expect, it } from "vitest";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import {
  configurationSource,
  emptyNodeCode,
  isBusinessInputCandidate,
  isBusinessOutput,
  isRequiredHook,
  isReservedNodeOptionLabel,
  nodeClassName,
  nodeNameProblem,
  noHoldFifosOption,
  nodeOptionRole,
  observesOutside,
  programCommandLineOptions,
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

describe("nodeOptionRole", () => {
  it("tells the sort of each option of a node", () => {
    expect(nodeOptionRole(option("-outf", { channel: "fifo" }))).toBe("businessOutput");
    expect(nodeOptionRole(option("-inf"))).toBe("businessInput");
    expect(nodeOptionRole(option("-id", { value: "${idx}" }))).toBe("businessInput");
    expect(nodeOptionRole(option("-ext", { channel: "fifo", fifoTag: "external" }))).toBe("externalInput");
  });

  it("makes a configuration option of whatever no connection can feed", () => {
    expect(nodeOptionRole(option("-n", { commandLine: true }))).toBe("configuration");
    expect(nodeOptionRole(option("-c", { fromProcessSpec: true, value: "cpus" }))).toBe("configuration");
    expect(nodeOptionRole(option("-verbose", { dataType: "None" }))).toBe("configuration");
    expect(nodeOptionRole(option("-outv", { value: "/tmp/v" }))).toBe("configuration");
  });
});

describe("configurationSource", () => {
  it("says where the value of an option that takes no connection comes from", () => {
    expect(configurationSource(option("-n", { commandLine: true }))).toBe("cmdline");
    expect(configurationSource(option("-v", { commandLine: true, dataType: "None" }))).toBe("cmdline");
    expect(configurationSource(option("-c", { fromProcessSpec: true, value: "cpus" }))).toBe("spec");
    expect(configurationSource(option("-verbose", { dataType: "None" }))).toBe("flag");
    expect(configurationSource(option("-outv", { value: "/tmp/v" }))).toBe("fixed");
  });

  it("gives the flag of the Supervisor a place of its own among its options", () => {
    const flag = noHoldFifosOption();
    expect(flag.label).toBe("-no-hold-fifos");
    expect(nodeOptionRole(flag)).toBe("configuration");
    expect(configurationSource(flag)).toBe("cmdline");
  });
});

describe("observesOutside", () => {
  function node(fields: Partial<ProgramProcess>): ProgramProcess {
    return {
      id: "n",
      name: "n",
      description: "",
      position: { x: 0, y: 0 },
      options: [],
      optionsHandler: { mode: "standard" },
      language: "python",
      code: "",
      computationalSpecs: {},
      additionalSpecs: { force: false },
      additionalMethods: {},
      ...fields,
    };
  }

  it("holds for an FBPProcess only with a body for observe", () => {
    expect(observesOutside(node({ nodeKind: "FBPProcess", nodeCode: emptyNodeCode() }))).toBe(false);
    expect(observesOutside(node({ nodeKind: "FBPProcess", nodeCode: { ...emptyNodeCode(), observe: "  \n" } }))).toBe(false);
    expect(observesOutside(node({ nodeKind: "FBPProcess", nodeCode: { ...emptyNodeCode(), observe: "self.poll()" } }))).toBe(true);
  });

  it("holds for every ProgramLauncher and DirectoryWatcher, and never for the Supervisor", () => {
    expect(observesOutside(node({ nodeKind: "ProgramLauncher", nodeCode: emptyNodeCode() }))).toBe(true);
    expect(observesOutside(node({ nodeKind: "DirectoryWatcher", nodeCode: emptyNodeCode() }))).toBe(true);
    expect(observesOutside(node({ nodeKind: "Supervisor" }))).toBe(false);
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

describe("programCommandLineOptions", () => {
  function processWith(nodeKind: ProgramProcess["nodeKind"], options: ProgramOption[]): ProgramProcess {
    return {
      id: nodeKind ?? "p",
      name: nodeKind ?? "p",
      description: "",
      position: { x: 0, y: 0 },
      options,
      optionsHandler: { mode: "standard" },
      language: "python",
      code: "",
      computationalSpecs: {},
      additionalSpecs: { force: false },
      additionalMethods: {},
      nodeKind,
    } as ProgramProcess;
  }

  const count = option("-w", { commandLine: true, dataType: "int" });

  it("adds the flag of the Supervisor in a resident program that has one", () => {
    const processes = [processWith("FBPProcess", [count]), processWith("Supervisor", [])];
    expect(programCommandLineOptions({ programType: "resident", processes }).map(o => o.label))
      .toEqual(["-w", "-no-hold-fifos"]);
  });

  it("offers only the options of the processes without a Supervisor", () => {
    const processes = [processWith("FBPProcess", [count])];
    expect(programCommandLineOptions({ programType: "resident", processes }).map(o => o.label))
      .toEqual(["-w"]);
    expect(programCommandLineOptions({ programType: "general", processes: [processWith(undefined, [count])] })
      .map(o => o.label)).toEqual(["-w"]);
  });
});
