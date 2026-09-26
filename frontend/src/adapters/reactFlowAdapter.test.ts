import { describe, expect, it } from "vitest";
import type { ProgramOption } from "../models/option";
import type { ProgramProcess } from "../models/process";
import type { Program } from "../models/program";
import { createEmptyProgram } from "../storage/programStorage";
import { computeFlippedOptionIds, isValidProgramConnection } from "./reactFlowAdapter";

function option(id: string, label: string, fields: Partial<ProgramOption> = {}): ProgramOption {
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
    ...fields,
  };
}

function process(id: string, options: ProgramOption[], y = 0): ProgramProcess {
  return {
    id,
    name: id,
    description: "",
    position: { x: 0, y },
    options,
    optionsHandler: { mode: "standard" },
    language: "bash",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

function program(processes: ProgramProcess[]): Program {
  return { ...createEmptyProgram("p"), processes };
}

const counter = process("counter", [
  option("counter-self", "-self"),
  option("counter-outself", "-outself", { channel: "fifo", value: "counter_self" }),
  option("counter-outsink", "-outsink", { channel: "fifo", value: "counter_sink" }),
]);

const sink = process("sink", [option("sink-in", "-in")], 200);

describe("isValidProgramConnection", () => {
  it("accepts a self-loop from an output to an input of the same process", () => {
    expect(
      isValidProgramConnection(program([counter, sink]), {
        source: "counter",
        sourceHandle: "counter-outself",
        target: "counter",
        targetHandle: "counter-self",
      })
    ).toBe(true);
  });

  it("still refuses a connection from an input to an output of the same process", () => {
    expect(
      isValidProgramConnection(program([counter, sink]), {
        source: "counter",
        sourceHandle: "counter-self",
        target: "counter",
        targetHandle: "counter-outself",
      })
    ).toBe(false);
  });

  it("accepts a connection between two processes", () => {
    expect(
      isValidProgramConnection(program([counter, sink]), {
        source: "counter",
        sourceHandle: "counter-outsink",
        target: "sink",
        targetHandle: "sink-in",
      })
    ).toBe(true);
  });
});

describe("computeFlippedOptionIds", () => {
  it("flips no handle of a self-loop", () => {
    const withLoop: Program = {
      ...program([counter, sink]),
      edges: [
        {
          id: "loop",
          sourceProcessId: "counter",
          sourceOptionId: "counter-outself",
          targetProcessId: "counter",
          targetOptionId: "counter-self",
        },
      ],
    };
    expect(computeFlippedOptionIds(withLoop).size).toBe(0);
  });
});
