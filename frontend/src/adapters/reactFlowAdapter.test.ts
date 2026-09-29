import { describe, expect, it } from "vitest";
import type { ProgramOption } from "../models/option";
import type { ProgramProcess } from "../models/process";
import type { Program } from "../models/program";
import type { ProgramEdge } from "../models/edge";
import { emptyNodeCode } from "../models/node";
import { createEmptyProgram } from "../storage/programStorage";
import { canvasStructuralKey, computeFlippedOptionIds, isValidProgramConnection } from "./reactFlowAdapter";

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

  it("refuses a connection into a flag", () => {
    const flagged = process("flagged", [option("flagged-v", "-v", { dataType: "None" })], 200);
    expect(
      isValidProgramConnection(program([counter, flagged]), {
        source: "counter",
        sourceHandle: "counter-outsink",
        target: "flagged",
        targetHandle: "flagged-v",
      })
    ).toBe(false);
  });

  it("refuses a connection into an option whose value comes from elsewhere", () => {
    const configured = process("configured", [
      option("configured-n", "-n", { commandLine: true }),
      option("configured-c", "-c", { fromProcessSpec: true, value: "cpus" }),
    ], 200);
    for (const targetHandle of ["configured-n", "configured-c"]) {
      expect(
        isValidProgramConnection(program([counter, configured]), {
          source: "counter",
          sourceHandle: "counter-outsink",
          target: "configured",
          targetHandle,
        })
      ).toBe(false);
    }
  });

  it("refuses a self-loop from an output that is not a fifo", () => {
    const writer = process("writer", [
      option("writer-in", "-in"),
      option("writer-outf", "-outf", { dataType: "file", value: "out.txt" }),
    ]);
    expect(
      isValidProgramConnection(program([writer]), {
        source: "writer",
        sourceHandle: "writer-outf",
        target: "writer",
        targetHandle: "writer-in",
      })
    ).toBe(false);
  });

  // a -> b by file, and b -> a closes the cycle: refused by file, accepted
  // when b writes a fifo.
  function cycle(bOutChannel: "none" | "fifo") {
    const a = process("a", [option("a-in", "-in"), option("a-out", "-out", { value: "a.txt" })]);
    const b = process(
      "b",
      [option("b-in", "-in"), option("b-out", "-out", { channel: bOutChannel, value: "b_out" })],
      200
    );
    const withAToB: Program = {
      ...program([a, b]),
      edges: [
        { id: "ab", sourceProcessId: "a", sourceOptionId: "a-out", targetProcessId: "b", targetOptionId: "b-in" },
      ],
    };
    return isValidProgramConnection(withAToB, {
      source: "b",
      sourceHandle: "b-out",
      target: "a",
      targetHandle: "a-in",
    });
  }

  it("refuses a connection that closes a cycle with no fifo", () => {
    expect(cycle("none")).toBe(false);
  });

  it("accepts a connection that closes a cycle through a fifo", () => {
    expect(cycle("fifo")).toBe(true);
  });
});

describe("canvasStructuralKey", () => {
  const key = canvasStructuralKey(program([counter, sink]));

  it("stays the same when a process is moved", () => {
    const moved = { ...sink, position: { x: 300, y: 400 } };
    expect(canvasStructuralKey(program([counter, moved]))).toBe(key);
  });

  it("changes when a process is renamed or its options handler mode is switched", () => {
    expect(canvasStructuralKey(program([counter, { ...sink, name: "drain" }]))).not.toBe(key);
    const array = { ...sink, optionsHandler: { ...sink.optionsHandler, mode: "array" as const } };
    expect(canvasStructuralKey(program([counter, array]))).not.toBe(key);
  });

  it("changes when an option is added, removed or relabeled", () => {
    const added = { ...sink, options: [...sink.options, option("sink-n", "-n")] };
    expect(canvasStructuralKey(program([counter, added]))).not.toBe(key);
    expect(canvasStructuralKey(program([counter, { ...sink, options: [] }]))).not.toBe(key);
    const relabeled = { ...sink, options: [option("sink-in", "-inf")] };
    expect(canvasStructuralKey(program([counter, relabeled]))).not.toBe(key);
  });

  it("changes when a process is added or removed", () => {
    expect(canvasStructuralKey(program([counter]))).not.toBe(key);
  });
});

describe("canvasStructuralKey in a resident program", () => {
  const relay: ProgramProcess = {
    ...process("relay", [
      option("relay-in", "-inf"),
      option("relay-outf", "-outf", { channel: "fifo", value: "relay_out" }),
    ]),
    language: "python",
    nodeKind: "FBPProcess",
    nodeCode: emptyNodeCode(),
  };

  function resident(processes: ProgramProcess[], edges: ProgramEdge[] = []): Program {
    return { ...program(processes), programType: "resident", edges };
  }

  const key = canvasStructuralKey(resident([relay]));

  it("changes when a node becomes an initiator or starts to observe the outside world", () => {
    expect(canvasStructuralKey(resident([{ ...relay, initiator: true }]))).not.toBe(key);
    const observing = { ...relay, nodeCode: { ...emptyNodeCode(), observe: "self.poll()" } };
    expect(canvasStructuralKey(resident([observing]))).not.toBe(key);
  });

  it("changes when an option changes its sort", () => {
    const configured = { ...relay, options: [option("relay-in", "-inf", { commandLine: true }), relay.options[1]] };
    expect(canvasStructuralKey(resident([configured]))).not.toBe(key);
  });

  it("stays the same when a connection is made", () => {
    const loop: ProgramEdge = {
      id: "loop",
      sourceProcessId: "relay",
      sourceOptionId: "relay-outf",
      targetProcessId: "relay",
      targetOptionId: "relay-in",
    };
    expect(canvasStructuralKey(resident([relay], [loop]))).toBe(key);
  });

  it("stays as in a general program when the program is general", () => {
    expect(canvasStructuralKey(program([relay]))).not.toBe(key);
    expect(canvasStructuralKey(program([{ ...relay, initiator: true }]))).toBe(canvasStructuralKey(program([relay])));
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

describe("isValidProgramConnection in a resident program", () => {

  function node(id: string, options: ProgramOption[], y = 0): ProgramProcess {
    return { ...process(id, options, y), language: "python", nodeKind: "FBPProcess" };
  }

  const relay = node("relay", [
    option("relay-in", "-inf"),
    option("relay-ext", "-ext", { channel: "fifo", fifoTag: "external", value: "relay_ext" }),
    option("relay-n", "-n", { commandLine: true }),
    option("relay-v", "-v", { dataType: "None" }),
    option("relay-outf", "-outf", { channel: "fifo", value: "relay_out" }),
    option("relay-outv", "-outv", { value: "/tmp/v" }),
  ]);

  const collect = node("collect", [option("collect-in", "-inf")], 200);

  function resident(processes: ProgramProcess[]): Program {
    return { ...program(processes), programType: "resident" };
  }

  function connects(sourceHandle: string, target: string, targetHandle: string, source = "relay") {
    return isValidProgramConnection(resident([relay, collect]), {
      source,
      target,
      sourceHandle,
      targetHandle,
    });
  }

  it("joins a business output to an input of another node or of the same one", () => {
    expect(connects("relay-outf", "collect", "collect-in")).toBe(true);
    expect(connects("relay-outf", "relay", "relay-in")).toBe(true);
  });

  it("joins nothing from an output that is not a FIFO", () => {
    expect(connects("relay-outv", "collect", "collect-in")).toBe(false);
  });

  it("joins nothing into an external input or a configuration option", () => {
    expect(connects("relay-outf", "relay", "relay-ext")).toBe(false);
    expect(connects("relay-outf", "relay", "relay-n")).toBe(false);
    expect(connects("relay-outf", "relay", "relay-v")).toBe(false);
  });

  it("keeps a single connection into each business input", () => {
    const withEdge: Program = {
      ...resident([relay, collect]),
      edges: [{
        id: "e1",
        sourceProcessId: "relay",
        sourceOptionId: "relay-outf",
        targetProcessId: "collect",
        targetOptionId: "collect-in",
      }],
    };
    expect(isValidProgramConnection(withEdge, {
      source: "relay",
      target: "collect",
      sourceHandle: "relay-outf",
      targetHandle: "collect-in",
    })).toBe(false);
  });

  it("leaves a general program as it was", () => {
    expect(isValidProgramConnection(program([relay, collect]), {
      source: "relay",
      target: "collect",
      sourceHandle: "relay-outv",
      targetHandle: "collect-in",
    })).toBe(true);
  });

});
