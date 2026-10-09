import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { GENERATOR_SIZE_TEMPLATE, LANGUAGE_NAMES, isCodeStillTemplate } from "./codeTemplates";
import { NODE_CODE_PARTS, nodeClassName } from "./node";
import { ASK_BEFORE_GUESSING, describedAs, fenceFor, optionsSection } from "./codePrompt";

// The options handler modes whose code has a code prompt: the code that
// builds the array of an array process, and the code that prints the
// number of tasks of an option generator. The option definition function
// of a manual process has none.
export type PromptedHandlerMode = "array" | "generator";

// The lines that script generation writes before the code of the options
// handler, which the code finds already set.
const HEADER = [
  "local cmdline=$1",
  "local process_spec=$2",
  "local process_name=$3",
  "local process_outdir=$4",
];

// The code prompt of the code of the options handler of a process: as that
// of the code of a process (see buildCodePrompt), with the rules of the
// options handler mode, and the code of the process as context, since how
// the process uses the options of a task says what a task is.
export function buildOptionsHandlerPrompt(
  program: Program,
  process: ProgramProcess,
  mode: PromptedHandlerMode,
  draft: string,
  request: string,
): string {
  const what = mode === "array"
    ? "the code that builds the array of tasks"
    : "the code that prints the number of tasks";
  const noun = program.programType === "resident" ? "node" : "process";

  const sections = [
    [
      `# Write ${what} of the DeBasher ${noun} \`${process.name}\``,
      "",
      `DeBasher runs programs made of processes, each of which receives its options from the engine; a process can run as several tasks, each with options of its own. Write ${what} of the ${noun} described below.`,
    ],
    rulesSection(process, mode),
    ["## The program", "", `- Name: \`${program.name}\``, ...describedAs(program.description)],
    [
      "## The process",
      "",
      `- Name: \`${process.name}\``,
      ...describedAs(process.description),
      `- Options handler mode: \`${mode}\``,
    ],
    optionsSection(program, process),
    program.programType === "resident" ? nodeCodeSection(process) : processCodeSection(process),
    codeSection(mode === "generator" && draft.trim() === GENERATOR_SIZE_TEMPLATE.trim() ? "" : draft),
    [
      "## What the code has to do",
      "",
      request.trim() !== ""
        ? request.trim()
        : mode === "array"
          ? "Build the array that the description of the process and the values of its options call for."
          : "Print the number of tasks that the description of the process and the values of its options call for.",
    ],
    [
      "## What to return",
      "",
      ASK_BEFORE_GUESSING,
      "",
      "Return the whole code in a single fenced code block tagged `bash`, with nothing else inside the block, and without the lines `local cmdline=$1` to `local process_outdir=$4` that come before it.",
    ],
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}

function rulesSection(process: ProgramProcess, mode: PromptedHandlerMode): string[] {
  const own = mode === "array"
    ? [
        `- The code is Bash, written into the function \`${process.name}_define_opts\`, which defines the options of every task of the process. It has to build a Bash array named \`array\`, with one element for each task. After it, a loop \`for task_idx in "\${!array[@]}"\` defines the options of each task, whose values can use \`\${array[$task_idx]}\`, the element of the task, \`\${task_idx}\`, its index, and any variable that the code sets.`,
        "- `debasher_exec` runs the code once each time it prepares a run, so a later run builds the array again, from what it reads then.",
      ]
    : [
        `- The code is Bash, written into the function \`${process.name}_generate_opts_size\`. It has to print the number of tasks of the process on its standard output, and nothing else. Another function defines the options of the task of index \`task_idx\`, from 0, whose values can use \`\${task_idx}\`; it does not see the variables of this code.`,
        "- `debasher_exec` runs the code once each time it prepares a run, in a subshell, so a later run counts the tasks again, from what it reads then.",
      ];
  return [
    "## How the engine runs the code",
    "",
    ...own,
    "- The code comes after these lines, which are already written:",
    "",
    "  ```bash",
    ...HEADER.map(line => `  ${line}`),
    "  ```",
    "",
    "- Read the value of a command line option of the program with `get_cmdline_opt \"$cmdline\" \"<label>\"`. `$process_outdir` is the output directory of the process.",
    "- The code runs while `debasher_exec` prepares the run, before any process of the program does. It must never open a FIFO: nothing writes it yet, so the read would block `debasher_exec`, and what it read would be taken from the reader of the FIFO. It cannot read what a process of the program produces either: a file left by an earlier run would hold old data. It may read what exists before the run, such as a file or a directory given on the command line; the number of tasks usually comes from a command line option.",
  ];
}

// The code of the process, which says how a task uses its options; the
// prompt says when there is none to show yet.
export function processCodeSection(process: ProgramProcess, intro = "how each task uses its options"): string[] {
  const header = ["## The code of the process", ""];
  if (process.additionalSpecs.alias || process.additionalSpecs.externalAlias) {
    return [...header, `The process takes its code from the ${process.additionalSpecs.alias ? "alias" : "external alias"} \`${process.additionalSpecs.alias || process.additionalSpecs.externalAlias}\`, which is not shown here.`];
  }
  if (isCodeStillTemplate(process.code)) {
    return [...header, "The code of the process is not written yet: the descriptions above are all there is about what a task does."];
  }
  const fence = fenceFor(process.code);
  return [
    ...header,
    `For context only, ${intro} (${LANGUAGE_NAMES[process.language]}):`,
    "",
    `${fence}${process.language}`,
    process.code.replace(/\n+$/, ""),
    fence,
  ];
}

// The code of a node of a resident program, for context: the parts that
// have code, under their names.
function nodeCodeSection(process: ProgramProcess): string[] {
  const header = ["## The code of the node", ""];
  const code = process.nodeCode;
  const parts = NODE_CODE_PARTS.filter(({ part }) => code && code[part].trim() !== "");
  if (!code || parts.length === 0) {
    return [...header, "The code of the node is not written yet: the descriptions above are all there is about what a task does."];
  }
  const lines = [...header, `For context only, the parts of the class \`${nodeClassName(process.name)}\` (Python), each task of which is a node of its own:`];
  for (const { part, label } of parts) {
    const fence = fenceFor(code[part]);
    lines.push("", `### ${label}`, "", `${fence}python`, code[part].replace(/\n+$/, ""), fence);
  }
  return lines;
}

export function codeSection(draft: string): string[] {
  const header = ["## The code to complete", ""];
  if (draft.trim() === "") {
    return [...header, "Empty: write it from scratch."];
  }
  const fence = fenceFor(draft);
  return [
    ...header,
    `${fence}bash`,
    draft.replace(/\n+$/, ""),
    fence,
    "",
    "Change this code as the next section says, and keep the rest of it.",
  ];
}
