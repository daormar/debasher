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
      "How to comment the code",
      "What to return",
    ]);
  });

  it("lists the sequential processes that a Bash process can run as steps, before the code", () => {
    const withSeq = {
      ...program,
      seqProcesses: [
        { id: "s1", name: "double", description: "Doubles $1 into the file $2.", language: "python", code: "", computationalSpecs: {}, additionalSpecs: { sched: "SLURM" } },
        { id: "s2", name: "add_one", description: "Adds one to -n.", language: "bash", code: "", computationalSpecs: {}, additionalSpecs: { alias: "increment", aliasOptMap: [{ fromLabel: "-n", toLabel: "-value" }] } },
        { id: "s3", name: "tidy", description: "", language: "bash", code: "", computationalSpecs: {}, additionalSpecs: { externalAlias: "tidy.sh" } },
        { id: "s4", name: "plain", description: "Prints $1.", language: "bash", code: "", computationalSpecs: {}, additionalSpecs: {} },
      ],
    } as unknown as Program;
    const prompt = buildCodePrompt(withSeq, count, "", "");
    const headings = [...prompt.matchAll(/^## (.*)$/gm)].map(m => m[1]);
    expect(headings.indexOf("The sequential processes")).toBe(headings.indexOf("The options") + 1);
    expect(prompt).toContain("`seq_execute <name> <args>`");
    expect(prompt).toContain("- `double` (Python, steps on Slurm): Doubles $1 into the file $2.");
    expect(prompt).toContain("- `add_one` (alias of `increment`, `-n` passed on as `-value`): Adds one to -n.");
    expect(prompt).toContain("- `tidy` (external alias `tidy.sh`, arguments not described)\n");
    expect(prompt).toContain("- `plain` (Bash): Prints $1.");
    expect(prompt).toContain("not `seq_execute_slurm`");
    expect(prompt).toContain("`< /dev/null`");
    expect(prompt).toContain("never a FIFO");
  });

  it("gives the rule of the steps on Slurm only when a sequential process sends its steps there", () => {
    const withSeq = {
      ...program,
      seqProcesses: [{ id: "s1", name: "plain", description: "Prints $1.", language: "bash", code: "", computationalSpecs: {}, additionalSpecs: {} }],
    } as unknown as Program;
    expect(buildCodePrompt(withSeq, count, "", "")).not.toContain("never a FIFO");
  });

  it("says nothing of sequential processes when the program has none, or to a process in another language", () => {
    const withSeq = {
      ...program,
      seqProcesses: [{ id: "s1", name: "double", description: "", language: "python", code: "", computationalSpecs: {}, additionalSpecs: {} }],
    } as unknown as Program;
    expect(buildCodePrompt(program, count, "", "")).not.toContain("seq_execute");
    expect(buildCodePrompt(withSeq, withLanguage(count, "python"), "", "")).not.toContain("seq_execute");
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
    expect(prompt).toContain("- `-inf` (input, the path of a FIFO, each line a string)\n  lines to count\n  Reads the option `-outf` of the process `produce`: the lines\n  (`produce`: Writes numbered lines.)");
    expect(prompt).toContain("That output is a FIFO: both processes run at the same time");
    expect(prompt).toContain("- `-sep` (input, string)\n  Its value: `tab`.");
    expect(prompt).toContain("- `-v` (flag)\n  say more");
    expect(prompt).toContain("- `-outv` (output, the path of a value descriptor that holds a string)\n  the count\n  A value descriptor: write the value with `write_value_to_desc <value> <path>`");
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

  it("says that each task of an array waits only for the task of the same index of the array whose file it reads", () => {
    const array = { optionsHandler: { mode: "array" } } as Partial<ProgramProcess>;
    const generator = { optionsHandler: { mode: "generator" } } as Partial<ProgramProcess>;
    const prompt = (writesFields: Partial<ProgramProcess>, readsFields: Partial<ProgramProcess>) => {
      const writes = process("writes", [createOption("outf", "-outf", { direction: "output", dataType: "file" })], writesFields);
      const reads = process("reads", [createOption("inf", "-inf")], readsFields);
      const p = { ...program, processes: [writes, reads], edges: [
        { id: "e", sourceProcessId: "writes", sourceOptionId: "outf", targetProcessId: "reads", targetOptionId: "inf" },
      ] } as Program;
      return buildCodePrompt(p, reads, "", "");
    };
    const counterpart = "Each task of this process runs once the task of `writes` with the same index has finished, while other tasks of `writes` may still be running";

    expect(prompt(array, array)).toContain(counterpart);
    expect(prompt(generator, array)).toContain(counterpart);
    // A standard process on either side gives afterok
    expect(prompt({}, array)).toContain("This process runs once `writes` has finished.");
    expect(prompt(array, {})).toContain("This process runs once `writes` has finished.");
    expect(prompt(array, generator)).toContain(counterpart);
    // A manual options handler may pair the tasks by index or not
    const manual = { optionsHandler: { mode: "manual" } } as Partial<ProgramProcess>;
    expect(prompt(array, manual)).toContain("This process runs once `writes` has finished, unless its options handler connects each task to the task of `writes` with the same index");
    // The generated code of an array reads the first task of a manual one
    expect(prompt(manual, array)).toContain("This process runs once `writes` has finished.");
  });

  it("says when a process with processdeps starts with respect to the one whose file it reads", () => {
    const reads = (processdeps: string) => process("reads", [createOption("inf", "-inf")], { additionalSpecs: { processdeps } } as Partial<ProgramProcess>);
    const writes = process("writes", [createOption("outf", "-outf", { direction: "output", dataType: "file" })]);
    const prompt = (processdeps: string) => {
      const p = { ...program, processes: [writes, reads(processdeps)], edges: [
        { id: "e", sourceProcessId: "writes", sourceOptionId: "outf", targetProcessId: "reads", targetOptionId: "inf" },
      ] } as Program;
      return buildCodePrompt(p, p.processes[1], "", "");
    };
    const finished = "This process runs once `writes` has finished.";
    const notWaiting = "The `processdeps` of this process do not wait for `writes` to finish, so the file may not be complete when it starts.";

    expect(prompt("after:other,afterok:writes")).toContain(finished);
    // afterany and aftercorr together ask for every task successful
    expect(prompt("afterany:writes,aftercorr:writes")).toContain(finished);
    expect(prompt("afterany:writes")).toContain("This process runs once `writes` has ended, whether it finished or failed, so the file may be incomplete or missing.");
    expect(prompt("aftercorr:writes")).toContain("Each task of this process runs once the task of `writes` with the same index has finished, while other tasks of `writes` may still be running (a task with no such counterpart waits for every task of `writes`).");
    expect(prompt("afternotok:writes")).toContain("This process runs once `writes` has failed, so the file may be incomplete or missing.");
    // In a list joined by "," every element holds
    expect(prompt("afterany:writes,afternotok:writes")).toContain("has failed");
    expect(prompt("afterok:writes?afterok:other")).toContain("The `processdeps` of this process may let it start before `writes` finishes");
    expect(prompt("after:writes")).toContain(notWaiting);
    expect(prompt("none")).toContain(notWaiting);
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

  it("says what a directory of the task's own gives the code", () => {
    const worker = process("worker", [
      createOption("outd", "-outd", { direction: "output", channel: "process_outdir", subpath: "${task_idx}" }),
      createOption("outs", "-outs", { direction: "output", channel: "shared_dir", value: "data", subpath: "${task_idx}" }),
      createOption("outp", "-outp", { direction: "output", channel: "process_outdir" }),
    ], { optionsHandler: { mode: "array", arrayCode: "array=(0 1)" } });
    const prompt = buildCodePrompt({ ...program, processes: [worker], edges: [] } as Program, worker, "", "");
    expect(prompt).toContain("The absolute path of the directory `${task_idx}` below the output directory of the process, a directory of the task's own: it exists and is empty when the code starts");
    expect(prompt).toContain("The absolute path of the directory `${task_idx}` below the shared directory `data`");
    expect(prompt).toContain("which every task of the process shares and which is not emptied before each of them");

    const resetting = { ...worker, additionalMethods: { resetOutfilesCode: "worker_reset_outfiles()\n{\n    :\n}" } } as ProgramProcess;
    const resetPrompt = buildCodePrompt({ ...program, processes: [resetting], edges: [] } as Program, resetting, "", "");
    expect(resetPrompt).toContain("its `reset_outfiles` method, not the engine, decides what is left in it");
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
      createOption("outf", "-outf-ith", { direction: "output", channel: "fifo", countSourceOptionId: "w" }),
    ]);
    const prompt = buildCodePrompt({ ...program, processes: [dispatch], edges: [] } as Program, dispatch, "", "");
    expect(prompt).toContain("A fanout family: the options `-outf0`, `-outf1`, ..., as many as the value of `-w`.");
    expect(prompt).not.toContain("someone outside the program");
    expect(prompt).not.toContain("The task does not receive that number");
  });

  it("names the generator whose tasks count a fanout family without a count source", () => {
    const worker = process("worker", [createOption("outd", "-outd", { direction: "output", dataType: "dir" })], {
      optionsHandler: { mode: "generator", generatorSizeCode: "echo 2" },
    });
    const collect = process("collect", [createOption("ind", "-ind-ith", { dataType: "dir" })]);
    const edges = [{ id: "e", sourceProcessId: "worker", sourceOptionId: "outd", targetProcessId: "collect", targetOptionId: "ind" }];
    const prompt = buildCodePrompt({ ...program, processes: [worker, collect], edges } as Program, collect, "", "");
    expect(prompt).toContain("A fanout family: the options `-ind0`, `-ind1`, ..., as many as the tasks of `worker`.");
    expect(prompt).toContain("The task does not receive that number: count the options of the family among the arguments.");
  });

  it("names an array or a generator as what counts a fanout family without a count source nor connection", () => {
    const collect = process("collect", [createOption("ind", "-ind-ith", { dataType: "dir" })]);
    const prompt = buildCodePrompt({ ...program, processes: [collect], edges: [] } as Program, collect, "", "");
    expect(prompt).toContain("as many as the tasks of the process at the other end of its connections, an array or a generator.");
  });

  it("gives the language rules of the language of the process", () => {
    const bash = buildCodePrompt(program, count, "", "");
    expect(bash).toContain("- The process is a Bash function named `count`");
    expect(bash).toContain("`read_flag_from_func_args \"<label>\" \"$@\"`");
    expect(bash).not.toContain("here-document");
    for (const [language, command] of [["python", "python3 count.py"], ["perl", "perl count.pl"], ["r", "Rscript count.R"], ["groovy", "groovy count.groovy"]] as const) {
      const prompt = buildCodePrompt(program, withLanguage(count, language), "", "");
      expect(prompt).toContain(`which the engine runs as \`${command}\``);
      expect(prompt).toContain("may import a module beside it");
      expect(prompt).not.toContain("here-document");
    }
    const loaded = { ...withLanguage(count, "python"), files: { code: "src/counter.py", tasks: "", methods: {} } };
    expect(buildCodePrompt(program, loaded, "", "")).toContain("runs as `python3 src/counter.py`");
  });

  it("carries the template of the process when the draft is blank, and asks to fill it in", () => {
    for (const language of ["bash", "python", "perl", "r", "groovy"] as const) {
      const p = withLanguage(count, language);
      const prompt = buildCodePrompt(program, p, "  \n", "");
      expect(prompt).toContain(`\`\`\`${language}\n${generateCodeTemplate(program, p)}\n\`\`\``);
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

  it("asks for comments that say what the code does not, in the style of the language", () => {
    const bash = buildCodePrompt(program, count, "", "");
    expect(bash).toContain("## How to comment the code\n\nComment the code for someone who did not write it:");
    expect(bash).toContain("Before each helper function, a block of `#` comments, as the modules of DeBasher have");
    expect(bash).toContain("its arguments (`# $1 - ...`) and what it prints or returns.");
    expect(bash).toContain("A comment for each step whose reason does not follow from the code: the format of an input");
    expect(bash).toContain("No comment that only repeats what the code says.");
    const python = buildCodePrompt(program, withLanguage(count, "python"), "", "");
    expect(python).toContain("A docstring for each helper function and class");
    expect(python).not.toContain("`# $1 - ...`");
    expect(buildCodePrompt(program, withLanguage(count, "r"), "", "")).toContain("Before each helper function, a comment: what it does");
  });

  it("asks for the whole code in a single block, with the function line in Bash", () => {
    expect(buildCodePrompt(program, count, "", "")).toContain("the line `count()` that names the function included, in a single fenced code block tagged `bash`");
    expect(buildCodePrompt(program, withLanguage(count, "r"), "", "")).toContain("in a single fenced code block tagged `r`, with nothing else inside the block.");
  });
});
