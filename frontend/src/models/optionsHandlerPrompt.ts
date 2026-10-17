import type { FuncLanguage, ProgramProcess } from "./process";
import type { Program } from "./program";
import { LANGUAGE_NAMES, isCodeStillTemplate, isFuncTemplate } from "./codeTemplates";
import { NODE_CODE_PARTS, nodeClassName } from "./node";
import { ASK_BEFORE_GUESSING, commentSection, describedAs, fenceFor, optionsSection } from "./codePrompt";

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
// the process uses the options of a task says what a task is. In Python
// the code is a tasks file, which defines tasks(run).
export function buildOptionsHandlerPrompt(
  program: Program,
  process: ProgramProcess,
  mode: PromptedHandlerMode,
  draft: string,
  request: string,
  language: FuncLanguage = "bash",
): string {
  const python = language === "python";
  const what = python
    ? `the Python tasks file of ${mode === "array" ? "an array" : "an option generator"}`
    : mode === "array"
      ? "the code that builds the array of tasks"
      : "the code that prints the number of tasks";
  const noun = program.programType === "resident" ? "node" : "process";

  const sections = [
    [
      `# Write ${what} of the DeBasher ${noun} \`${process.name}\``,
      "",
      `DeBasher runs programs made of processes, each of which receives its options from the engine; a process can run as several tasks, each with options of its own. Write ${what} of the ${noun} described below.`,
    ],
    python ? pythonRulesSection(program, process, mode) : rulesSection(program, process, mode),
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
    codeSection(isFuncTemplate(draft) ? "" : draft, language),
    [
      "## What the code has to do",
      "",
      request.trim() !== ""
        ? request.trim()
        : mode === "array"
          ? `${python ? "Return the elements of the array" : "Build the array"} that the description of the process and the values of its options call for.`
          : `${python ? "Return" : "Print"} the number of tasks that the description of the process and the values of its options call for.`,
    ],
    commentSection(language, [
      python
        ? `- A docstring for \`tasks\`: what a task of the ${noun} is, and where the number of tasks comes from.`
        : `- A comment at the start of the code: what a task of the ${noun} is, and where the number of tasks comes from.`,
    ]),
    [
      "## What to return",
      "",
      ASK_BEFORE_GUESSING,
      "",
      python
        ? "Return the whole file in a single fenced code block tagged `python`, with nothing else inside the block: the function `tasks(run)` and what it needs."
        : "Return the whole code in a single fenced code block tagged `bash`, with nothing else inside the block, and without the lines `local cmdline=$1` to `local process_outdir=$4` that come before it.",
    ],
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}

function rulesSection(program: Program, process: ProgramProcess, mode: PromptedHandlerMode): string[] {
  const own = mode === "array"
    ? [
        `- The code is Bash, written into the function \`${process.name}_define_opts\`, which defines the options of every task of the process. It has to build a Bash array named \`array\`, with one element for each task. After it, a loop \`for task_idx in "\${!array[@]}"\` defines the options of each task, whose values can use \`\${array[$task_idx]}\`, the element of the task, \`\${task_idx}\`, its index, and any variable that the code sets.`,
        "- `debasher_exec` runs the code each time it prepares a run, so a later run builds the array again, from what it reads then. Within a run it may run it more than once: when another process asks for the number of tasks of this one with `get_process_num_tasks` before this code has run in its turn, the engine runs it again, in a subshell, and keeps nothing of that run. The code has to build an array of the same size every time: a file or a directory that it reads, such as one given on the command line, has to stay unchanged while the run lasts.",
      ]
    : [
        `- The code is Bash, written into the function \`${process.name}_generate_opts_size\`. It has to print the number of tasks of the process on its standard output, and nothing else. Another function defines the options of the task of index \`task_idx\`, from 0, whose values can use \`\${task_idx}\`; it does not see the variables of this code.`,
        "- `debasher_exec` runs the code each time it prepares a run, in a subshell, so a later run counts the tasks again, from what it reads then; within a run it may run it more than once (when another process asks for the number of tasks with `get_process_num_tasks`), and it calls the function that defines the options of a task again inside that task. The code has to print the same number every time: a file or a directory that it reads, such as one given on the command line, has to stay unchanged while the run lasts.",
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
    ...numTasksRules(program, process, mode),
  ];
}

// The rules of a tasks file in Python, as the engine runs it (see "Python
// function files" in doc/design_doc_engine.md): the same moment and the
// same inputs as the Bash it replaces, read through `run`.
function pythonRulesSection(program: Program, process: ProgramProcess, mode: PromptedHandlerMode): string[] {
  const own = mode === "array"
    ? `- The code is a Python file that defines a function \`tasks(run)\`, which the engine calls to build the array of the tasks of the process. It returns the elements of the array, one per task: a list, or any other iterable, of strings, numbers or paths. The function \`${process.name}_define_opts\` of the module then defines the options of each task in Bash, whose values can use \`\${array[$task_idx]}\`, the text of the element of the task, and \`\${task_idx}\`, its index; nothing else of the Python code reaches them.`
    : `- The code is a Python file that defines a function \`tasks(run)\`, which the engine calls to count the tasks of the process. It returns the number of tasks, an integer, 0 or more. The options of the task of index \`task_idx\`, from 0, are defined in Bash, and their values can use \`\${task_idx}\`; nothing of the Python code reaches them.`;
  return [
    "## How the engine runs the code",
    "",
    own,
    "- `run` holds what the code may read: `run.value(\"<label>\")` is the value of a command line option of the program (`None` when it is not given or has no value; a second argument gives another default), `run.given(\"<label>\")` says whether an option or a flag is given, and `run.args` is the whole command line; `run.process` is the name of the process and `run.outdir` its output directory.",
    `- \`debasher_exec\` calls the function each time it prepares a run, so a later run ${mode === "array" ? "builds the array" : "counts the tasks"} again, from what it reads then; within a run it may call it more than once, when another process asks for the number of tasks of this one with \`get_process_num_tasks\` before this one is defined. It has to return the same ${mode === "array" ? "elements" : "number"} every time: a file or a directory that it reads, such as one given on the command line, has to stay unchanged while the run lasts.`,
    "- The function runs while `debasher_exec` prepares the run, before any process of the program does. It must never open a FIFO: nothing writes it yet, so the read would block `debasher_exec`, and what it read would be taken from the reader of the FIFO. It cannot read what a process of the program produces either: a file left by an earlier run would hold old data. It may read what exists before the run, such as a file or a directory given on the command line; the number of tasks usually comes from a command line option.",
    "- The file runs with the Python that DeBasher was configured with, not in the Conda environment or the Docker image of the process, so it imports only what that Python has; its own directory is first on `sys.path`, so it can import files beside it. A relative path is taken from the directory where `debasher_exec` runs. What it prints goes to the standard error. An exception, or a value of the wrong kind (a string or a dictionary for the elements, a negative number or a boolean for the number of tasks), stops the preparation of the run with the traceback.",
    "- Python cannot ask another process for its number of tasks (`get_process_num_tasks` is a Bash function of the engine): when the tasks of this process follow those of another one, the code of the options handler is better written in Bash.",
    ...taskByTaskSourcesLine(program, process),
  ];
}

// How the code takes its number of tasks from another process of the
// program, with get_process_num_tasks, instead of computing it again with
// the rule of that process, which two copies could apply differently. The
// processes that this one reads task by task are the usual candidates. Any
// process can be asked, once per code; a process in generator mode is
// cheap to ask, and one in array mode costs its whole option definition
// when it is not defined yet.
const COST_OF_ASKING =
  "Any process of the program can be asked, but ask once, keeping the number in a variable: a process in `generator` mode answers at the cost of its size code, while a process in `array` or `manual` mode that is not defined yet answers by running its whole option definition again, which is costly, so prefer asking a process in `generator` mode. A chain of such questions that comes back to this process stops the preparation of the run.";

function numTasksRules(program: Program, process: ProgramProcess, mode: PromptedHandlerMode): string[] {
  const rule = mode === "array"
    ? `- If the array has as many elements as another process of the program has tasks, read that number with \`n=$(get_process_num_tasks "<process>") || return 1\` instead of computing it again, which would repeat the rule by which the other process counts its tasks, and could apply it differently. ${COST_OF_ASKING}`
    : `- If the process has as many tasks as another process of the program, as when each task reads the task with the same index of that process, print that number with \`get_process_num_tasks "<process>"\` instead of computing it again, which would repeat the rule by which the other process counts its tasks, and could apply it differently. ${COST_OF_ASKING} Make it the last command of the code, or read it with \`n=$(get_process_num_tasks "<process>") || return 1\`, so that a failure stops the preparation of the run.`;
  return [rule, ...taskByTaskSourcesLine(program, process)];
}

// The rule that names the processes whose tasks this one reads task by
// task, when there are any.
function taskByTaskSourcesLine(program: Program, process: ProgramProcess): string[] {
  const sources = taskByTaskSources(program, process);
  if (sources.length === 0) {
    return [];
  }
  const listed = sources.map(source => `\`${source.name}\` (\`${source.optionsHandler.mode}\` mode)`).join(", ");
  return [`- This process reads, task by task, the tasks of: ${listed}.`];
}

// The processes in array or generator mode that an input of this process is
// connected to: in array or generator mode too, each task of this process
// reads the task of the same index of theirs. A connection between shared_dir
// options only documents that the processes share a directory, and pairs no
// tasks.
function taskByTaskSources(program: Program, process: ProgramProcess): ProgramProcess[] {
  const sharedDirInputs = new Set(
    process.options.filter(option => option.channel === "shared_dir").map(option => option.id),
  );
  const sourceIds = new Set(
    program.edges
      .filter(edge => edge.targetProcessId === process.id && edge.sourceProcessId !== process.id)
      .filter(edge => !sharedDirInputs.has(edge.targetOptionId))
      .map(edge => edge.sourceProcessId),
  );
  return program.processes.filter(
    other => sourceIds.has(other.id) && (other.optionsHandler.mode === "array" || other.optionsHandler.mode === "generator"),
  );
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

export function codeSection(draft: string, language: FuncLanguage = "bash"): string[] {
  const header = ["## The code to complete", ""];
  if (draft.trim() === "") {
    return [...header, "Empty: write it from scratch."];
  }
  const fence = fenceFor(draft);
  return [
    ...header,
    `${fence}${language}`,
    draft.replace(/\n+$/, ""),
    fence,
    "",
    "Change this code as the next section says, and keep the rest of it.",
  ];
}
