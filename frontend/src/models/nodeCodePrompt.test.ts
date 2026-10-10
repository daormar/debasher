import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import type { NodeCode } from "./node";
import { emptyNodeCode } from "./node";
import { buildNodeCodePrompt, offersNodeCodePrompt } from "./nodeCodePrompt";
import type { NodeLibrary } from "./nodeCodePrompt";

function node(name: string, nodeKind: ProgramProcess["nodeKind"], options: ProgramOption[], fields: Partial<ProgramProcess> = {}): ProgramProcess {
  return {
    id: name,
    name,
    description: "",
    language: "python",
    code: "",
    options,
    optionsHandler: { mode: "standard" },
    nodeKind,
    nodeCode: emptyNodeCode(),
    ...fields,
  } as ProgramProcess;
}

// webui_running_sum: a source feeds numbers to Accumulate, which sends the
// running sum; Accumulate also takes a scale, a flag and an external input.
const source = node("Source", "FBPProcess", [
  createOption("outnums", "-outnums", { direction: "output", channel: "fifo", description: "one number per message" }),
], { description: "Emits numbers." });

const accumulate = node("Accumulate", "FBPProcess", [
  createOption("in", "-in", { description: "numbers to add" }),
  createOption("scale", "-scale", { dataType: "int", commandLine: true, description: "factor of each number" }),
  createOption("label", "-label", { value: "sum" }),
  createOption("verbose", "-verbose", { dataType: "None" }),
  createOption("ext", "-ext", { channel: "fifo", fifoTag: "external", description: "resets from outside" }),
  createOption("outsum", "-outsum", { direction: "output", channel: "fifo", description: "the running sum" }),
], { description: "Adds the numbers it receives." });

const launch = node("Launch", "ProgramLauncher", [
  createOption("inreq", "-inreq"),
]);

const program = {
  name: "running_sum",
  programType: "resident",
  description: "Sums numbers as they arrive.",
  processes: [source, accumulate, launch],
  edges: [
    { id: "e1", sourceProcessId: "Source", sourceOptionId: "outnums", targetProcessId: "Accumulate", targetOptionId: "in" },
  ],
} as unknown as Program;

const library: NodeLibrary = {
  reference: "### FBPProcess\n\nThe base class of every node.\n\n#### Hooks of FBPProcess\n\n`def process_data(self, port_name, packet)`\n\nIt must be deterministic.",
  referenceError: null,
  inherited: {},
};

function code(fields: Partial<NodeCode>): NodeCode {
  return { ...emptyNodeCode(), ...fields };
}

describe("buildNodeCodePrompt", () => {
  it("is offered on every node kind but the Supervisor", () => {
    expect(offersNodeCodePrompt("FBPProcess")).toBe(true);
    expect(offersNodeCodePrompt("ProgramLauncher")).toBe(true);
    expect(offersNodeCodePrompt("DirectoryWatcher")).toBe(true);
    expect(offersNodeCodePrompt("Supervisor")).toBe(false);
  });

  it("has every part, in order", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    const headings = [...prompt.matchAll(/^## (.*)$/gm)].map(m => m[1]);
    expect(headings).toEqual([
      "How the code is put together",
      "The runtime library",
      "The program",
      "The node",
      "The ports and options",
      "The code to complete",
      "What the code has to do",
      "What to return",
    ]);
  });

  it("says how the parts are assembled into the class of the node", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    expect(prompt).toContain("`from debasher_runtime_lib import FBPProcess`, the node preamble, `class Accumulate(FBPProcess):`, the class body");
    expect(prompt).toContain("`Accumulate().run()`");
    expect(prompt).toContain("`def restore_node_state(self, node_state):`");
    expect(prompt).toContain("This node has to give a body to `process_data`, `capture_node_state`, `restore_node_state` and `initialize_runtime`");
  });

  it("carries the reference of the runtime library, or why it is missing", () => {
    expect(buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library))
      .toContain("from their own documentation:\n\n### FBPProcess\n\nThe base class of every node.");
    const missing = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", { reference: "", referenceError: "not found", inherited: {} });
    expect(missing).toContain("The reference of the runtime library could not be read (not found). Follow the rules above.");
  });

  it("describes each port and option by its role", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    expect(prompt).toContain("- `-in` (business input, port `in`)\n  numbers to add\n  What arrives on it reaches `process_data` with `port_name` `\"in\"`.\n  Sent by the option `-outnums` of the node `Source`: one number per message\n  (`Source`: Emits numbers.)");
    expect(prompt).toContain("- `-scale` (configuration option, int, command line option)\n  factor of each number\n  Its value, a string, is `self.opts[\"scale\"]`.");
    expect(prompt).toContain("- `-label` (configuration option, string)\n  Its value, a string, is `self.opts[\"label\"]`.\n  Its value: `sum`.");
    expect(prompt).toContain("- `-verbose` (flag)\n  `self.opts[\"verbose\"]` is True when the flag is given; list `\"verbose\"` in the class attribute `FLAGS`.");
    expect(prompt).toContain("- `-ext` (external input, port `ext`)\n  resets from outside\n  Written by someone outside the program");
    expect(prompt).toContain("- `-outsum` (business output, port `outsum`)\n  the running sum\n  Send on it with `self.send_data(\"outsum\", payload)`, from `process_data` only.\n  Nothing in the program reads it: someone outside the program reads it.");
  });

  it("takes an input that no connection reaches as a configuration option", () => {
    const prompt = buildNodeCodePrompt(program, launch, emptyNodeCode(), "", library);
    expect(prompt).toContain("- `-inreq` (configuration option, string)");
  });

  it("names the ports of a fanout family", () => {
    const dispatch = node("Dispatch", "FBPProcess", [
      createOption("w", "-w", { dataType: "int", commandLine: true }),
      createOption("outw", "-outw-ith", { direction: "output", channel: "fifo", countSourceOptionId: "w" }),
    ]);
    const prompt = buildNodeCodePrompt({ ...program, processes: [dispatch], edges: [] } as Program, dispatch, emptyNodeCode(), "", library);
    expect(prompt).toContain("A fanout family: the ports `outw0`, `outw1`, ..., as many as the value of `-w` says; send on one with `self.send_data(f\"outw{i}\", payload)`.");
  });

  it("carries every part, its code or that it is empty", () => {
    const draft = code({ classBody: "def __init__(self):\n    super().__init__()\n    self.total = 0\n", processData: "self.total += packet" });
    const prompt = buildNodeCodePrompt(program, accumulate, draft, "", library);
    expect(prompt).toContain("### Node preamble\n\nEmpty.");
    expect(prompt).toContain("### Class body\n\n```python\ndef __init__(self):\n    super().__init__()\n    self.total = 0\n```");
    expect(prompt).toContain("### process_data\n\n```python\nself.total += packet\n```");
    expect(prompt).toContain("### capture_node_state\n\nEmpty, and required.");
    expect(prompt).toContain("### observe\n\nEmpty.");
  });

  it("shows the hooks that a node inherits, and which ones a body replaces", () => {
    const inherited = { processData: "def process_data(self, port_name, packet):\n    self._register(packet)", observe: "def observe(self):\n    pass" };
    const draft = code({ classBody: "PFILE = \"greet.sh\"", observe: "super().observe()" });
    const prompt = buildNodeCodePrompt(program, launch, draft, "", { ...library, inherited });
    expect(prompt).toContain("`ProgramLauncher` already implements every hook");
    expect(prompt).toContain("such as `super().process_data(port_name, packet)`");
    expect(prompt).toContain("### process_data\n\nEmpty: the node runs `process_data` of `ProgramLauncher`, which is:\n\n```python\ndef process_data(self, port_name, packet):\n    self._register(packet)\n```");
    expect(prompt).toContain("### observe\n\n```python\nsuper().observe()\n```\n\nIt replaces `observe` of `ProgramLauncher`, which is:\n\n```python\ndef observe(self):\n    pass\n```");
    expect(prompt).toContain("### capture_node_state\n\nEmpty: the node runs `capture_node_state` of `ProgramLauncher`.");
  });

  it("says when the inherited code could not be read", () => {
    const prompt = buildNodeCodePrompt(program, launch, emptyNodeCode(), "", { ...library, inheritedError: "not found" });
    expect(prompt).toContain("The code of the hooks that the node inherits from `ProgramLauncher` could not be read (not found).");
    expect(buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", { ...library, inheritedError: "not found" })).not.toContain("could not be read");
  });

  it("asks to ask rather than guess, before the form of the answer", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    expect(prompt).toContain("## What to return\n\nIf something that the code depends on is missing or ambiguous");
    expect(prompt).toContain("Otherwise, return the code as follows.\n\nReturn each part that you change");
  });

  it("asks for the parts that change, each whole under its name", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "Reset on ext.", library);
    expect(prompt).toContain("## What the code has to do\n\nReset on ext.");
    expect(prompt).toContain("under a heading `### <part>` with the name of the part: one of `Node preamble`, `Class body`, `process_data`, `capture_node_state`, `restore_node_state`, `initialize_runtime`, `observe`.");
    expect(prompt).toContain("A part that you do not return stays as it is");
    expect(buildNodeCodePrompt(program, accumulate, emptyNodeCode(), " ", library)).toContain("Write the code that the description of the node asks for.");
  });

  it("gives the same text for the same arguments", () => {
    expect(buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library))
      .toBe(buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library));
  });
});
