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
    createOption("inf", "-inf", { value: "${array[$idx]}", description: "the file of the task" }),
    createOption("outf", "-outf", { direction: "output", dataType: "file", value: "${process_outdir}/${idx}.txt" }),
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
    expect(prompt).toContain("whose values can use `${array[$idx]}`, the element of the task, `${idx}`, its index, and any variable that the code sets.");
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

  it("shows the values of the options, which say what a task is", () => {
    const prompt = buildOptionsHandlerPrompt(program, count, "array", "", "");
    expect(prompt).toContain("- `-inf` (input, string)\n  the file of the task\n  Its value: `${array[$idx]}`.");
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
