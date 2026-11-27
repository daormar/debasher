// @vitest-environment node
import { describe, expect, it } from "vitest";

import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { OptionsHandlerMode, ProgramProcess } from "./process";
import type { Program } from "./program";
import {
  buildOptionChanges,
  canShapeTasks,
  describeFanoutCount,
  describeLockedDataType,
  findScatterCountSource,
  getLockedDataType,
  isScatterConsumer,
  listConnectedSources,
  listOfferedChannels,
  listOfferedDataTypes,
  type OptionDraft,
  type SaveContext,
} from "./optionForm";
import { createEmptyProgram } from "../storage/programStorage";

function process(name: string, mode: OptionsHandlerMode, options: ProgramOption[]): ProgramProcess {
  return {
    id: name,
    name,
    description: "",
    position: { x: 0, y: 0 },
    options,
    optionsHandler: { mode },
    language: "bash",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

function programOf(processes: ProgramProcess[], edges: [string, string, string, string][] = []): Program {
  return {
    ...createEmptyProgram("p"),
    processes,
    edges: edges.map(([source, sourceOption, target, targetOption], index) => ({
      id: `e${index}`,
      sourceProcessId: source,
      sourceOptionId: sourceOption,
      targetProcessId: target,
      targetOptionId: targetOption,
    })),
  };
}

function draft(fields: Partial<OptionDraft> = {}): OptionDraft {
  return {
    label: "-in",
    dataType: "string",
    channel: "none",
    subpath: "",
    mirror: false,
    description: "",
    value: "v",
    commandLine: false,
    fromProcessSpec: false,
    mandatory: false,
    taskShaping: false,
    countSourceOptionId: "",
    ...fields,
  };
}

const general: SaveContext = { isResident: false, isConnected: false, lockedDataType: null, canShapeTasks: false, isFanout: false };

describe("listConnectedSources", () => {

  it("names each output that an option reads, task by task between two processes of several tasks", () => {
    const program = programOf([
      process("gen", "generator", [createOption("o", "-outf")]),
      process("std", "standard", [createOption("o", "-outf")]),
      process("arr", "array", [createOption("i", "-in")]),
    ], [["gen", "o", "arr", "i"], ["std", "o", "arr", "i"]]);
    const reader = program.processes[2];
    expect(listConnectedSources(program, reader, reader.options[0]).map(source => source.sentinel)).toEqual([
      "[gen;-outf;${task_idx}]",
      "[std;-outf]",
    ]);
  });

  it("names the members of a gathering family by the index of its loop", () => {
    const program = programOf([
      process("arr", "array", [createOption("o", "-outf")]),
      process("merge", "standard", [createOption("i", "-in-ith")]),
    ], [["arr", "o", "merge", "i"]]);
    const merge = program.processes[1];
    expect(listConnectedSources(program, merge, merge.options[0]).map(source => source.sentinel)).toEqual([
      "[arr;-outf;${i}]",
    ]);
  });

  it("tells a scatter, and the count source of its family", () => {
    const program = programOf([
      process("split", "standard", [
        createOption("o", "-outf-ith", { countSourceOptionId: "w" }),
        createOption("w", "-w", { commandLine: true }),
      ]),
      process("work", "array", [createOption("i", "-in")]),
    ], [["split", "o", "work", "i"]]);
    const work = program.processes[1];
    const [first] = listConnectedSources(program, work, work.options[0]);
    expect(isScatterConsumer(first)).toBe(true);
    expect(findScatterCountSource(first)?.label).toBe("-w");
    expect(isScatterConsumer(undefined)).toBe(false);
  });

});

describe("the data type of the editor", () => {

  it("is locked by a directory channel or by a connection, but not on the command line", () => {
    const source = { process: process("a", "standard", []), option: createOption("o", "-outf", { dataType: "int" }), sentinel: "" };
    expect(getLockedDataType("shared_dir", false, undefined)).toBe("dir");
    expect(describeLockedDataType("shared_dir", false, undefined)).toBe("(directory channel)");
    expect(getLockedDataType("none", false, source)).toBe("int");
    expect(describeLockedDataType("none", false, source)).toBe("(from connection)");
    expect(getLockedDataType("shared_dir", true, undefined)).toBeNull();
    expect(getLockedDataType("none", false, undefined)).toBeNull();
  });

  it("offers a flag only on an input that is not connected", () => {
    expect(listOfferedDataTypes("input", false)).toContain("None");
    expect(listOfferedDataTypes("input", true)).not.toContain("None");
    expect(listOfferedDataTypes("output", false)).not.toContain("None");
  });

});

describe("listOfferedChannels", () => {

  it("offers a value descriptor and a process output directory only to an output, and no directory in a resident program", () => {
    const channelsOf = (direction: "input" | "output", resident: boolean) =>
      listOfferedChannels(direction, resident).map(entry => entry.channel);
    expect(channelsOf("output", false)).toEqual(["none", "value_desc", "fifo", "process_outdir", "shared_dir"]);
    expect(channelsOf("input", false)).toEqual(["none", "fifo", "shared_dir"]);
    expect(channelsOf("output", true)).toEqual(["none", "fifo"]);
    expect(listOfferedChannels("input", true)[1].text).toBe("External input (FIFO written from outside the program)");
  });

});

describe("canShapeTasks", () => {

  it("takes a command line input with a value that counts no family", () => {
    const owner = process("p", "standard", [
      createOption("w", "-w", { commandLine: true }),
      createOption("f", "-outf-ith", { countSourceOptionId: "w" }),
      createOption("n", "-n", { commandLine: true }),
    ]);
    const [w, , n] = owner.options;
    expect(canShapeTasks(owner, n, { label: "-n", dataType: "int", commandLine: true }, false)).toBe(true);
    expect(canShapeTasks(owner, w, { label: "-w", dataType: "int", commandLine: true }, false)).toBe(false);
    expect(canShapeTasks(owner, n, { label: "-n", dataType: "None", commandLine: true }, false)).toBe(false);
    expect(canShapeTasks(owner, n, { label: "-outn", dataType: "int", commandLine: true }, false)).toBe(false);
    expect(canShapeTasks(owner, n, { label: "-n", dataType: "int", commandLine: false }, false)).toBe(false);
    expect(canShapeTasks(owner, n, { label: "-n-ith", dataType: "int", commandLine: true }, true)).toBe(false);
  });

});

describe("describeFanoutCount", () => {

  it("names the one process that a family counts, and says why an option is needed otherwise", () => {
    expect(describeFanoutCount([process("g", "generator", [])])).toBe("Number of tasks of g");
    expect(describeFanoutCount([process("a", "array", [])])).toBe("Number of tasks of a (an array: a generator is cheaper to count)");
    expect(describeFanoutCount([process("s", "standard", [])])).toBe("Number of tasks of s (not an array nor a generator: choose an option)");
    expect(describeFanoutCount([])).toMatch(/not connected yet/);
    expect(describeFanoutCount([process("a", "array", []), process("b", "array", [])])).toMatch(/connected to several/);
  });

});

describe("buildOptionChanges", () => {

  it("saves the label without the spaces around it, with the direction that it gives", () => {
    const changes = buildOptionChanges(draft({ label: " -outf ", channel: "fifo", mirror: true }), general);
    expect(changes.label).toBe("-outf");
    expect(changes.direction).toBe("output");
    expect(changes.mirror).toBe(true);
  });

  it("saves a flag with no channel, value nor mandatory mark", () => {
    const changes = buildOptionChanges(
      draft({ dataType: "None", channel: "fifo", commandLine: true, mandatory: true, value: "x" }),
      general,
    );
    expect(changes).toMatchObject({ channel: "none", value: "", mandatory: false, mirror: false });
  });

  it("saves a command line option on the channel \"none\", and mandatory when it shapes the tasks", () => {
    expect(buildOptionChanges(draft({ commandLine: true, channel: "fifo" }), general).channel).toBe("none");
    const shaping = buildOptionChanges(
      draft({ commandLine: true, taskShaping: true }),
      { ...general, canShapeTasks: true },
    );
    expect(shaping).toMatchObject({ commandLine: true, taskShaping: true, mandatory: true });
    // Not where the option cannot shape tasks
    expect(buildOptionChanges(draft({ commandLine: true, taskShaping: true }), general).taskShaping).toBe(false);
  });

  it("takes an attribute of the specifications only for an input, which is then no command line option", () => {
    expect(buildOptionChanges(draft({ fromProcessSpec: true, commandLine: true }), general))
      .toMatchObject({ fromProcessSpec: true, commandLine: false, mandatory: false });
    expect(buildOptionChanges(draft({ label: "-outn", fromProcessSpec: true }), general).fromProcessSpec).toBe(false);
  });

  it("saves a connected input on the channel \"none\", or on the shared directory that it reads", () => {
    const connected = { ...general, isConnected: true, lockedDataType: "int" as const };
    expect(buildOptionChanges(draft({ channel: "fifo", mirror: true }), connected))
      .toMatchObject({ channel: "none", dataType: "int", mirror: false });
    expect(buildOptionChanges(draft({ channel: "shared_dir", value: "data", subpath: " 3 " }), connected))
      .toMatchObject({ channel: "shared_dir", value: "data", subpath: "3" });
  });

  it("keeps a subpath only on a directory channel, and no value of a value descriptor or a process output directory", () => {
    expect(buildOptionChanges(draft({ subpath: "3" }), general).subpath).toBe("");
    expect(buildOptionChanges(draft({ label: "-outd", channel: "process_outdir", subpath: "${task_idx}" }), general))
      .toMatchObject({ value: "", subpath: "${task_idx}" });
    expect(buildOptionChanges(draft({ label: "-outv", channel: "value_desc" }), general).value).toBe("");
  });

  it("tags a FIFO input of a resident program as an external input, and mirrors no FIFO there", () => {
    const resident = { ...general, isResident: true };
    expect(buildOptionChanges(draft({ channel: "fifo" }), resident).fifoTag).toBe("external");
    expect(buildOptionChanges(draft({ label: "-outq", channel: "fifo", mirror: true }), resident))
      .toMatchObject({ fifoTag: undefined, mirror: false });
  });

  it("keeps the count source only of a fanout family", () => {
    expect(buildOptionChanges(draft({ countSourceOptionId: "w" }), { ...general, isFanout: true }).countSourceOptionId).toBe("w");
    expect(buildOptionChanges(draft({ countSourceOptionId: "" }), { ...general, isFanout: true }).countSourceOptionId).toBeUndefined();
    expect(buildOptionChanges(draft({ countSourceOptionId: "w" }), general).countSourceOptionId).toBeUndefined();
  });

});
