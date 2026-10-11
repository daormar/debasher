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
      "How to comment the code",
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
    expect(prompt).not.toContain("as a request for a batch run");
  });

  it("asks for comments as the runtime library documents its classes", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    expect(prompt).toContain("## How to comment the code\n\nComment the code for someone who did not write it, as the runtime library documents its own classes:");
    expect(prompt).toContain("A docstring for each helper function and method, and for each hook or method that the node redefines (for a hook, the first line of its body)");
    expect(prompt).toContain("a choice made for the recovery of the node or the idempotence of an effect outside the program, why something is dropped.");
    expect(prompt).toContain("A comment in the constructor on what the node state holds, which the constructor, `process_data`, `capture_node_state` and `restore_node_state` have to agree on.");
    expect(prompt).toContain("No comment that only repeats what the code says.");
  });

  it("asks for the methods of the runtime library rather than code of its own", () => {
    const prompt = buildNodeCodePrompt(program, accumulate, emptyNodeCode(), "", library);
    expect(prompt).toContain("`self.sleep()`, not `time.sleep()`");
    expect(prompt).toContain("`observe` with `self.inject()`");
    expect(prompt).toContain("set again in `restore_node_state` when it follows from the node state");
  });

  describe("a watcher, a launcher and the node that reads the ends of the batch runs", () => {
    const watch = node("Watch", "DirectoryWatcher", [
      createOption("watchdir", "-watchdir", { commandLine: true, mandatory: true }),
      createOption("outrequests", "-outrequests", { direction: "output", channel: "fifo", value: "requests" }),
    ]);
    const batch = node("Batch", "ProgramLauncher", [
      createOption("requests", "-requests"),
      createOption("pfile", "-pfile", { commandLine: true }),
      createOption("process", "-process", { value: "align" }),
      createOption("runsdir", "-runsdir", { commandLine: true }),
      createOption("outdone", "-outdone", { direction: "output", channel: "fifo", value: "done" }),
    ]);
    const report = node("Report", "FBPProcess", [
      createOption("done", "-done"),
      createOption("files", "-files"),
    ]);
    const pipeline = {
      name: "pipeline",
      programType: "resident",
      description: "",
      processes: [watch, batch, report],
      edges: [
        { id: "e1", sourceProcessId: "Watch", sourceOptionId: "outrequests", targetProcessId: "Batch", targetOptionId: "requests" },
        { id: "e2", sourceProcessId: "Batch", sourceOptionId: "outdone", targetProcessId: "Report", targetOptionId: "done" },
        { id: "e3", sourceProcessId: "Watch", sourceOptionId: "outrequests", targetProcessId: "Report", targetOptionId: "files" },
      ],
    } as unknown as Program;

    it("says which options the class of a watcher uses, and what it sends", () => {
      const prompt = buildNodeCodePrompt(pipeline, watch, emptyNodeCode(), "", library);
      expect(prompt).toContain("The class `DirectoryWatcher` reads it (`WATCH_DIR_OPTION`)");
      expect(prompt).toContain("The class `DirectoryWatcher` sends on it (`REQUESTS_PORT`), once for each complete file, what `request_for()` makes of its path, by default `{\"opts\": {\"-infile\": \"<path of the file>\"}");
      expect(prompt).not.toContain("Send on it with");
    });

    it("says which options the class of a launcher uses, and what it takes and sends", () => {
      const prompt = buildNodeCodePrompt(pipeline, batch, emptyNodeCode(), "", library);
      expect(prompt).toContain("The class `ProgramLauncher` takes every message on it as a request for a batch run: `{\"opts\": {\"-<option>\": \"<value>\", ...}, \"run\": \"<run directory>\"}`");
      expect(prompt).toContain("The class `ProgramLauncher` reads it (`PFILE_OPTION`): the general program to launch, in place of `PFILE`.");
      expect(prompt).toContain("The class `ProgramLauncher` reads it (`PROCESS_OPTION`)");
      expect(prompt).toContain("The class `ProgramLauncher` reads it (`RUNS_ROOT_OPTION`)");
      expect(prompt).toContain("The class `ProgramLauncher` sends on it (`DONE_PORT`), for each batch run that ends, `{\"run\": ..., \"run_dir\": ..., \"status\": ..., \"exit_code\": ...}`");
      expect(prompt).not.toContain("Send on it with");
    });

    it("tells the node downstream what each message of the class holds", () => {
      const prompt = buildNodeCodePrompt(pipeline, report, emptyNodeCode(), "", library);
      expect(prompt).toContain("Each message is `{\"run\": ..., \"run_dir\": ..., \"status\": ..., \"exit_code\": ...}`, with `run_dir` the absolute path of the run directory, where the results of the batch run are");
      expect(prompt).toContain("Each message is `{\"opts\": {\"-infile\": \"<path of the file>\"}, \"run\": \"<name of the file without its extension>\"}`, for one complete file.");
    });

    it("leaves the request to a request_for that the class body of the watcher redefines", () => {
      const redefined = { ...watch, nodeCode: code({ classBody: "def request_for(self, path):\n    return {\"opts\": {\"-bam\": path}}" }) };
      const withRedefined = { ...pipeline, processes: [redefined, batch, report] } as Program;
      const prompt = buildNodeCodePrompt(withRedefined, report, emptyNodeCode(), "", library);
      expect(prompt).toContain("Each message is what `request_for()` of `Watch`, redefined in its class body, makes of the path of a complete file.");
    });
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
