import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { buildMethodPrompt } from "./methodPrompt";
import { PROCESS_METHODS } from "./processMethods";

// A process that writes a file and runs a tool of a conda environment.
const align = {
  id: "align",
  name: "align",
  description: "Aligns the reads.",
  language: "bash",
  code: "align()\n{\n    conda_activate bwa\n    local outf=$(read_opt_value_from_func_args \"-outf\" \"$@\")\n    bwa mem ref.fa reads.fq > \"${outf}\"\n}",
  options: [
    createOption("outf", "-outf", { direction: "output", dataType: "file", value: "${process_outdir}/aln.sam", description: "the alignments" }),
  ],
  optionsHandler: { mode: "standard" },
  additionalSpecs: {},
  additionalMethods: {},
} as unknown as ProgramProcess;

const program = {
  name: "mapping",
  description: "Maps reads.",
  processes: [align],
  edges: [],
} as unknown as Program;

describe("buildMethodPrompt", () => {
  it("has every part, in order", () => {
    const prompt = buildMethodPrompt(program, align, "skipCode", "", "");
    const headings = [...prompt.matchAll(/^## (.*)$/gm)].map(m => m[1]);
    expect(headings).toEqual([
      "How the engine runs the method",
      "The program",
      "The process",
      "The options",
      "The code of the process",
      "The code to complete",
      "What the code has to do",
      "What to return",
    ]);
  });

  it("gives the rules of the method, from the list of the methods", () => {
    for (const method of PROCESS_METHODS) {
      const prompt = buildMethodPrompt(program, align, method.key, "", "");
      expect(prompt).toContain(`# Write the \`${method.name}\` method of the DeBasher process \`align\``);
      expect(prompt).toContain(`- The method is a Bash function, \`align_${method.name}()\`, whatever the language of the process. You write only its body`);
      for (const rule of method.rules) {
        expect(prompt).toContain(`- ${rule}`);
      }
    }
  });

  it("says that skip skips on success, and that no end of a FIFO may be skipped", () => {
    const prompt = buildMethodPrompt(program, align, "skipCode", "", "");
    expect(prompt).toContain("Returning 0 skips the task; any other status lets it run.");
    expect(prompt).toContain("A process at either end of a FIFO must not be skipped");
  });

  it("says that post runs whether the process function succeeded or failed", () => {
    expect(buildMethodPrompt(program, align, "postCode", "", ""))
      .toContain("right after the process function returns, whether the function succeeded or failed.");
  });

  it("describes the options as arguments, or as what the code of the process reads", () => {
    expect(buildMethodPrompt(program, align, "resetOutfilesCode", "", ""))
      .toContain("## The options\n\n- `-outf` (output, file)");
    expect(buildMethodPrompt(program, align, "condaEnvsCode", "", ""))
      .toContain("## The options\n\nThe method receives no options; the options of the process, which its code reads, show what it works on:\n\n- `-outf` (output, file)");
  });

  it("carries the code of the process, which shows what the method acts on", () => {
    expect(buildMethodPrompt(program, align, "condaEnvsCode", "", "")).toContain("    conda_activate bwa");
  });

  it("carries the code to complete, and the code request", () => {
    expect(buildMethodPrompt(program, align, "postCode", "", "")).toContain("## The code to complete\n\nEmpty: write it from scratch.");
    const prompt = buildMethodPrompt(program, align, "postCode", "rm -f tmp\n", "Also gzip the output.");
    expect(prompt).toContain("```bash\nrm -f tmp\n```\n\nChange this code as the next section says");
    expect(prompt).toContain("## What the code has to do\n\nAlso gzip the output.");
    expect(buildMethodPrompt(program, align, "postCode", "", ""))
      .toContain("Write the `post` method that the description and the code of the process call for.");
  });

  it("asks to ask rather than guess, and for the body alone", () => {
    const prompt = buildMethodPrompt(program, align, "dockerImgsCode", "", "");
    expect(prompt).toContain("## What to return\n\nIf something that the code depends on is missing or ambiguous");
    expect(prompt).toContain("without the line `align_docker_imgs()` and the braces around the body.");
  });
});
