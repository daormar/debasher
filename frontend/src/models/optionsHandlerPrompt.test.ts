import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { generateCodeTemplate } from "./codeTemplates";
import { buildOptionsHandlerPrompt } from "./optionsHandlerPrompt";
import { GENERATOR_SIZE_TEMPLATE } from "./codeTemplates";
import { emptyNodeCode } from "./node";

// An array process with one task per file of a directory given on the
// command line, as data/programs/debasher_array_example.sh.
const count = {
  id: "count",
  name: "count",
  description: "Counts the lines of each file.",
  language: "bash",
  code: "count()\n{\n    local inf=$(read_opt_value_from_func_args \"-inf\" \"$@\")\n    wc -l < \"${inf}\"\n}",
  options: [
    createOption("dir", "-dir", { commandLine: true, description: "directory with the files" }),
    createOption("inf", "-inf", { value: "${array[$task_idx]}", description: "the file of the task" }),
    createOption("outf", "-outf", { direction: "output", dataType: "file", value: "${process_outdir}/${task_idx}.txt" }),
  ],
  optionsHandler: { mode: "array" },
  additionalSpecs: {},
} as unknown as ProgramProcess;

const program = {
  name: "counts",
  description: "Counts lines.",
  processes: [count],
  edges: [],
} as unknown as Program;

describe("buildOptionsHandlerPrompt", () => {
  it("has every part, in order", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    const headings = [...prompt.matchAll(/^## (.*)$/gm)].map(m => m[1]);
    expect(headings).toEqual([
      "How the engine runs the code",
      "The program",
      "The process",
      "The options",
      "The code of the process",
      "The code to complete",
      "What the code has to do",
      "What to return",
    ]);
  });

  it("gives the rules of an array", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    expect(prompt).toContain("# Write the code that builds the array of tasks of the DeBasher process `count`");
    expect(prompt).toContain("written into the function `count_define_opts`");
    expect(prompt).toContain("It has to build a Bash array named `array`, with one element for each task.");
    expect(prompt).toContain("whose values can use `${array[$task_idx]}`, the element of the task, `${task_idx}`, its index, and any variable that the code sets.");
    expect(prompt).toContain("  ```bash\n  local cmdline=$1\n  local process_spec=$2\n  local process_name=$3\n  local process_outdir=$4\n  ```");
    expect(prompt).toContain("`get_cmdline_opt \"$cmdline\" \"<label>\"`");
    expect(prompt).toContain("It must never open a FIFO: nothing writes it yet, so the read would block `debasher_exec`, and what it read would be taken from the reader of the FIFO.");
    expect(prompt).toContain("It cannot read what a process of the program produces either: a file left by an earlier run would hold old data.");
  });

  it("gives the rules of an option generator", () => {
    const generator = { ...count, optionsHandler: { mode: "generator" } } as ProgramProcess;
    const prompt = buildOptionsHandlerPrompt(program, generator, "generator", "", "");
    expect(prompt).toContain("# Write the code that prints the number of tasks of the DeBasher process `count`");
    expect(prompt).toContain("written into the function `count_generate_opts_size`. It has to print the number of tasks of the process on its standard output, and nothing else.");
    expect(prompt).toContain("`debasher_exec` runs the code once each time it prepares a run, in a subshell");
    expect(prompt).not.toContain("several times");
    expect(prompt).toContain("Print the number of tasks that the description of the process and the values of its options call for.");
  });

  it("asks an option generator to take its number of tasks from another process instead of computing it again", () => {
    const generator = { ...count, optionsHandler: { mode: "generator" } } as ProgramProcess;
    const prompt = buildOptionsHandlerPrompt(program, generator, "generator", "", "");
    expect(prompt).toContain("print that number with `get_process_num_tasks \"<process>\"` instead of computing it again");
    expect(prompt).toContain("Any process of the program can be asked.");
    expect(prompt).toContain("`n=$(get_process_num_tasks \"<process>\") || return 1`, so that a failure stops the preparation of the run.");
    expect(prompt).not.toContain("reads, task by task");
  });

  it("lets an array take its number of elements only from an option generator", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    expect(prompt).toContain("read that number with `n=$(get_process_num_tasks \"<process>\") || return 1` instead of computing it again");
    expect(prompt).toContain("Only a process in `generator` mode can be asked");
  });

  it("names the processes that the process reads task by task", () => {
    const producer = { ...count, id: "producer", name: "producer", optionsHandler: { mode: "generator" } } as ProgramProcess;
    const single = { ...count, id: "single", name: "single", optionsHandler: { mode: "standard" } } as ProgramProcess;
    const consumer = { ...count, id: "consumer", name: "consumer", optionsHandler: { mode: "generator" } } as ProgramProcess;
    const edge = (id: string, source: string) =>
      ({ id, sourceProcessId: source, sourceOptionId: `${source}-outf`, targetProcessId: "consumer", targetOptionId: "inf" });
    const connected = {
      ...program,
      processes: [producer, single, consumer],
      edges: [edge("e1", "producer"), edge("e2", "single")],
    } as unknown as Program;
    const prompt = buildOptionsHandlerPrompt(connected, consumer, "generator", "", "");
    expect(prompt).toContain("- This process reads, task by task, the tasks of: `producer` (`generator` mode).");
  });

  it("names for an array only the processes in generator mode that it reads task by task", () => {
    const generated = { ...count, id: "generated", name: "generated", optionsHandler: { mode: "generator" } } as ProgramProcess;
    const arrayed = { ...count, id: "arrayed", name: "arrayed", optionsHandler: { mode: "array" } } as ProgramProcess;
    const reader = { ...count, id: "reader", name: "reader", optionsHandler: { mode: "array" } } as ProgramProcess;
    const edge = (id: string, source: string) =>
      ({ id, sourceProcessId: source, sourceOptionId: `${source}-outf`, targetProcessId: "reader", targetOptionId: "inf" });
    const connected = {
      ...program,
      processes: [generated, arrayed, reader],
      edges: [edge("e1", "generated"), edge("e2", "arrayed")],
    } as unknown as Program;
    const prompt = buildOptionsHandlerPrompt(connected, reader, "array", "", "");
    expect(prompt).toContain("- This process reads, task by task, the tasks of: `generated` (`generator` mode).");
    expect(prompt).not.toContain("`arrayed`");
  });

  it("does not take a connection between shared directories for one that pairs tasks", () => {
    const writer = { ...count, id: "writer", name: "writer", optionsHandler: { mode: "array" } } as ProgramProcess;
    const reader = {
      ...count,
      id: "reader",
      name: "reader",
      optionsHandler: { mode: "generator" },
      options: [...count.options, createOption("data", "-data", { channel: "shared_dir", value: "data" })],
    } as ProgramProcess;
    const connected = {
      ...program,
      processes: [writer, reader],
      edges: [{ id: "e1", sourceProcessId: "writer", sourceOptionId: "writer-data", targetProcessId: "reader", targetOptionId: "data" }],
    } as unknown as Program;
    expect(buildOptionsHandlerPrompt(connected, reader, "generator", "", "")).not.toContain("reads, task by task");
  });

  it("shows the values of the options, which say what a task is", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    expect(prompt).toContain("- `-inf` (input, string)\n  the file of the task\n  Its value: `${array[$task_idx]}`.");
    expect(prompt).toContain("- `-dir` (input, string, command line option)\n  directory with the files");
  });

  it("carries the code of the process, or says that there is none yet", () => {
    expect(buildOptionsHandlerPrompt(program, count, "array", "", ""))
      .toContain("For context only, how each task uses its options (Bash):\n\n```bash\ncount()\n{");
    const unwritten = { ...count, code: generateCodeTemplate(count) } as ProgramProcess;
    expect(buildOptionsHandlerPrompt(program, unwritten, "array", "", ""))
      .toContain("The code of the process is not written yet: the descriptions above are all there is about what a task does.");
    const aliased = { ...count, additionalSpecs: { alias: "other" } } as unknown as ProgramProcess;
    expect(buildOptionsHandlerPrompt(program, aliased, "array", "", ""))
      .toContain("The process takes its code from the alias `other`, which is not shown here.");
  });

  it("carries the code to complete, or says that it is empty", () => {
    expect(buildOptionsHandlerPrompt(program, count, "array", " \n", "")).toContain("## The code to complete\n\nEmpty: write it from scratch.");
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "array=(a b)\n", "Use the files of -dir.");
    expect(prompt).toContain("```bash\narray=(a b)\n```\n\nChange this code as the next section says, and keep the rest of it.");
    expect(prompt).toContain("## What the code has to do\n\nUse the files of -dir.");
  });

  it("takes the first code of the generator editor as no code", () => {
    const generator = { ...count, optionsHandler: { mode: "generator" } } as ProgramProcess;
    expect(buildOptionsHandlerPrompt(program, generator, "generator", GENERATOR_SIZE_TEMPLATE, ""))
      .toContain("## The code to complete\n\nEmpty: write it from scratch.");
  });

  it("shows the parts of a node of a resident program as its code", () => {
    const node = {
      ...count,
      name: "Worker",
      language: "python",
      nodeKind: "FBPProcess",
      nodeCode: { ...emptyNodeCode(), processData: "self.send_data(\"out\", packet)" },
    } as unknown as ProgramProcess;
    const resident = { ...program, programType: "resident", processes: [node] } as unknown as Program;
    const prompt = buildOptionsHandlerPrompt(resident, node, "array", "", "");
    expect(prompt).toContain("# Write the code that builds the array of tasks of the DeBasher node `Worker`");
    expect(prompt).toContain("## The code of the node\n\nFor context only, the parts of the class `Worker` (Python), each task of which is a node of its own:\n\n### process_data\n\n```python\nself.send_data(\"out\", packet)\n```");
    const unwritten = { ...node, nodeCode: emptyNodeCode() } as ProgramProcess;
    expect(buildOptionsHandlerPrompt(resident, unwritten, "array", "", "")).toContain("The code of the node is not written yet");
  });

  it("asks to ask rather than guess, and for the code without its header", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    expect(prompt).toContain("## What to return\n\nIf something that the code depends on is missing or ambiguous");
    expect(prompt).toContain("without the lines `local cmdline=$1` to `local process_outdir=$4` that come before it.");
  });
});
