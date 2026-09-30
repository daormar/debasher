import { describe, expect, it } from "vitest";
import type { ProgramOption } from "./option";
import type { Program } from "./program";
import { draftPayload, entryText, talkCandidates } from "./residentTalk";

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

describe("talkCandidates", () => {
  it("offers the external inputs and the business outputs with no connection", () => {
    const program = {
      processes: [
        {
          name: "Launch",
          options: [
            option("-requests", { channel: "fifo", fifoTag: "external" }),
            option("-outdone", { channel: "fifo" }),
            option("-outlog", { channel: "fifo" }),
            option("-limit"),
          ],
        },
        { name: "Report", options: [option("-done", { value: "[Launch;-outdone]" })] },
      ],
      edges: [{ id: "e", sourceProcessId: "L", sourceOptionId: "-outdone", targetProcessId: "R", targetOptionId: "-done" }],
    } as unknown as Program;

    const { inputs, outputs } = talkCandidates(program);

    expect(inputs.map(c => `${c.processName} ${c.option.label}`)).toEqual(["Launch -requests"]);
    expect(outputs.map(c => `${c.processName} ${c.option.label}`)).toEqual(["Launch -outlog"]);
  });
});

describe("draftPayload", () => {
  it("parses JSON mode and keeps text mode as a string", () => {
    expect(draftPayload('{"a":\n 1}', "json")).toEqual({ a: 1 });
    expect(draftPayload("one", "json")).toBeUndefined();
    expect(draftPayload("one", "text")).toBe("one");
  });
});

describe("entryText", () => {
  const read = (envelope: { type: string; seq: number | null; payload: unknown }) =>
    entryText({ kind: "read", port: "sum", read: { envelope } });

  it("shows what was written and the payload of a DATA with its sequence number", () => {
    expect(entryText({ kind: "written", port: "numbers", payload: 3 })).toBe("> numbers: 3");
    expect(read({ type: "DATA", seq: 2, payload: { n: 3 } })).toBe('< sum #2: {"n":3}');
  });

  it("marks a BARRIER as the marker of a round and a CLOSE as the end of the writer", () => {
    expect(read({ type: "BARRIER", seq: null, payload: { epoch: 7, halt: true } }))
      .toBe("< sum: [round 7, halt: the marker of a round (BARRIER)]");
    expect(read({ type: "CLOSE", seq: null, payload: {} })).toMatch(/closed the channel/);
  });

  it("gives a line that is not an envelope as it was read", () => {
    expect(entryText({ kind: "read", port: "sum", read: { unparsable: "oops" } }))
      .toBe("< sum: [not an envelope] oops");
  });
});
