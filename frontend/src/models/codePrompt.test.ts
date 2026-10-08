import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { ProcessLanguage, ProgramProcess } from "./process";
import type { Program } from "./program";
import { buildCodePrompt } from "./codePrompt";
import { TEMPLATE_MARKER, generateCodeTemplate } from "./codeTemplates";

function process(name: string, options: ProgramOption[], fields: Partial<ProgramProcess> = {}): ProgramProcess {
  return {
    id: name,
    name,
    description: "",
    language: "bash",
    code: "",
    options,
    optionsHandler: { mode: "standard" },
    ...fields,
  } as ProgramProcess;
}

// A producer that streams lines through a FIFO to a counter, which hands
// the count to a reporter through a value descriptor.
const produce = process("produce", [
  createOption("n", "-n", { dataType: "int", commandLine: true, mandatory: true, description: "how many lines" }),
  createOption("outf", "-outf", { direction: "output", channel: "fifo", description: "the lines" }),
], { description: "Writes numbered lines." });

const count = process("count", [
  createOption("inf", "-inf", { description: "lines to count" }),
  createOption("sep", "-sep", { value: "tab" }),
  createOption("v", "-v", { dataType: "None", description: "say more" }),
  createOption("outv", "-outv", { direction: "output", channel: "value_desc", description: "the count" }),
], { description: "Counts lines.\nOne line per record." });

const report = process("report", [
  createOption("total", "-total", { description: "lines counted" }),
], { description: "Reports the count." });

const program = {
  name: "lines",
  description: "Counts the lines that a producer writes.",
  processes: [produce, count, report],
  edges: [
    { id: "e1", sourceProcessId: "produce", sourceOptionId: "outf", targetProcessId: "count", targetOptionId: "inf" },
    { id: "e2", sourceProcessId: "count", sourceOptionId: "outv", targetProcessId: "report", targetOptionId: "total" },
  ],
} as unknown as Program;

function withLanguage(p: ProgramProcess, language: ProcessLanguage): ProgramProcess {
  return { ...p, language };
}

describe("buildCodePrompt", () => {
  it("gives the same text for the same arguments", () => {
    expect(buildCodePrompt(program, count, "", "")).toBe(buildCodePrompt(program, count, "", ""));
  });

  it("has every part, in order", () => {
    const prompt = buildCodePrompt(program, count, "", "");
    const headings = [...prompt.matchAll(/^## (.*)$/gm)].map(m => m[1]);
    expect(headings).toEqual([
      "How the engine runs the code",
      "The program",
      "The process",
      "The options",
      "The code to complete",
      "What the code has to do",
      "What to return",
    ]);
  });

  it("describes the program and the process", () => {
    const prompt = buildCodePrompt(program, count, "", "");
    expect(prompt).toContain("- Name: `lines`\n- Description: Counts the lines that a producer writes.");
    expect(prompt).toContain("- Name: `count`\n- Language: Bash\n- Description: Counts lines.\n  One line per record.");
  });

  it("says that a process with several tasks runs once for each", () => {
    const array = { ...count, optionsHandler: { mode: "array" } } as ProgramProcess;
    expect(buildCodePrompt(program, array, "", "")).toContain("runs the code once for each of its tasks (options handler mode `array`)");
    expect(buildCodePrompt(program, count, "", "")).not.toContain("once for each of its tasks");
  });

  it("describes each option with its connections", () => {
    const prompt = buildCodePrompt(program, count, "", "");
    expect(prompt).toContain("- `-inf` (input, string)\n  lines to count\n  Reads the option `-outf` of the process `produce`: the lines\n  (`produce`: Writes numbered lines.)");
    expect(prompt).toContain("That output is a FIFO: both processes run at the same time");
    expect(prompt).toContain("- `-sep` (input, string)\n  Its value: `tab`.");
    expect(prompt).toContain("- `-v` (flag)\n  say more");
    expect(prompt).toContain("- `-outv` (output, string)\n  the count\n  A value descriptor: write the value with `write_value_to_desc <value> <path>`");
    expect(prompt).toContain("Read by the option `-total` of the process `report`: lines counted");
  });

  it("says how a value descriptor is written and read in each language", () => {
    const python = buildCodePrompt(program, withLanguage(count, "python"), "", "");
    expect(python).toContain("A value descriptor: write the value, alone, into the file that the option names.");
    expect(buildCodePrompt(program, report, "", "")).toContain("`read_opt_value_from_func_args` gives the value, not the path.");
    expect(buildCodePrompt(program, withLanguage(report, "perl"), "", "")).toContain("the option gives the path of a file that holds the value.");
  });

  it("says that a process runs after the one whose file it reads", () => {
    const reads = process("reads", [createOption("inf", "-inf")]);
    const writes = process("writes", [createOption("outf", "-outf", { direction: "output", dataType: "file" })]);
    const p = { ...program, processes: [writes, reads], edges: [
      { id: "e", sourceProcessId: "writes", sourceOptionId: "outf", targetProcessId: "reads", targetOptionId: "inf" },
    ] } as Program;
    expect(buildCodePrompt(p, reads, "", "")).toContain("This process runs once `writes` has finished.");
  });

  it("says that someone outside the program is at the other end of an unconnected FIFO", () => {
    const talk = process("talk", [
      createOption("inf", "-inf", { channel: "fifo" }),
      createOption("outf", "-outf", { direction: "output", channel: "fifo" }),
    ]);
    const prompt = buildCodePrompt({ ...program, processes: [talk], edges: [] } as Program, talk, "", "");
    expect(prompt).toContain("A FIFO that this process reads until its end.\n  Nothing in the program writes it: someone outside the program writes it.");
    expect(prompt).toContain("A FIFO that this process writes: close it once everything is written.\n  Nothing in the program reads it: someone outside the program reads it.");
  });

  it("says that the code does not receive a task shaping option", () => {
    const worker = process("worker", [
      createOption("w", "-w", { dataType: "int", commandLine: true, mandatory: true, taskShaping: true }),
      createOption("inf", "-inf"),
    ], { optionsHandler: { mode: "array", arrayCode: "array=(0 1)" } });
    const prompt = buildCodePrompt({ ...program, processes: [worker], edges: [] } as Program, worker, "", "");
    expect(prompt).toContain("- `-w` (input, int, mandatory, command line option, task shaping option)");
    expect(prompt).toContain("no task receives it, so the code of the process cannot read it");
    expect(prompt).not.toMatch(/`-inf` \([^)]*task shaping/);
  });

  it("names the count of a fanout family", () => {
    const dispatch = process("dispatch", [
      createOption("w", "-w", { dataType: "int", commandLine: true }),
      createOption("outf", "-outfith", { direction: "output", channel: "fifo", countSourceOptionId: "w" }),
    ]);
    const prompt = buildCodePrompt({ ...program, processes: [dispatch], edges: [] } as Program, dispatch, "", "");
    expect(prompt).toContain("A fanout family: the options `-outf0`, `-outf1`, ..., as many as the value of `-w`.");
    expect(prompt).not.toContain("someone outside the program");
  });

  it("gives the language rules of the language of the process", () => {
    const bash = buildCodePrompt(program, count, "", "");
    expect(bash).toContain("- The process is a Bash function named `count`");
    expect(bash).toContain("`read_flag_from_func_args \"<label>\" \"$@\"`");
    expect(bash).not.toContain("here-document");
    for (const [language, interpreter] of [["python", "python3 -c"], ["perl", "perl -e"], ["r", "Rscript -e"], ["groovy", "groovy -e"]] as const) {
      const prompt = buildCodePrompt(program, withLanguage(count, language), "", "");
      expect(prompt).toContain(`which the engine runs with \`${interpreter}\``);
      expect(prompt).toContain("so no line of the code may be `EOF` alone");
    }
  });

  it("carries the template of the process when the draft is blank, and asks to fill it in", () => {
    for (const language of ["bash", "python", "perl", "r", "groovy"] as const) {
      const p = withLanguage(count, language);
      const prompt = buildCodePrompt(program, p, "  \n", "");
      expect(prompt).toContain(`\`\`\`${language}\n${generateCodeTemplate(p)}\n\`\`\``);
      expect(prompt).toContain(`write the code of the process where the comment \`${TEMPLATE_MARKER}\` is`);
    }
  });

  it("carries a draft that is not a template, and asks to change it", () => {
    const prompt = buildCodePrompt(program, count, "count()\n{\n    wc -l\n}\n", "Count words too.");
    expect(prompt).toContain("```bash\ncount()\n{\n    wc -l\n}\n```");
    expect(prompt).toContain("Change this code as the next section says, and keep the rest of it.");
    expect(prompt).toContain("## What the code has to do\n\nCount words too.");
  });

  it("asks for what the description says when the code request is blank", () => {
    expect(buildCodePrompt(program, count, "", "  ")).toContain("Write the code that the description of the process asks for.");
  });

  it("fences a draft that holds backquotes with a longer fence", () => {
    const prompt = buildCodePrompt(program, count, "count()\n{\n    echo '```'\n}", "");
    expect(prompt).toContain("````bash\ncount()");
  });

  it("asks to ask rather than guess, before the form of the answer", () => {
    const prompt = buildCodePrompt(program, count, "", "");
    expect(prompt).toContain("## What to return\n\nIf something that the code depends on is missing or ambiguous");
    expect(prompt).toContain("ask about it before writing any code, all your questions at once, instead of guessing. Otherwise, return the code as follows.\n\nReturn the whole code");
  });

  it("asks for the whole code in a single block, with the function line in Bash", () => {
    expect(buildCodePrompt(program, count, "", "")).toContain("the line `count()` that names the function included, in a single fenced code block tagged `bash`");
    expect(buildCodePrompt(program, withLanguage(count, "r"), "", "")).toContain("in a single fenced code block tagged `r`, with nothing else inside the block.");
  });
});
