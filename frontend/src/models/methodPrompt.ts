import type { FuncLanguage, MethodCodeKey, ProgramProcess } from "./process";
import type { Program } from "./program";
import { ASK_BEFORE_GUESSING, commentSection, describedAs, optionsSection } from "./codePrompt";
import { codeSection, processCodeSection } from "./optionsHandlerPrompt";
import { PYTHON_SKIP_RULES, processMethod } from "./processMethods";
import { isFuncTemplate } from "./codeTemplates";

// The code prompt of an additional method of a process: as that of the
// code of a process (see buildCodePrompt), with the rules of the method,
// from PROCESS_METHODS, and the code of the process for context, since a
// method acts on what the process does (the files it writes, the
// environments it activates). The skip method may be a skip file in
// Python instead, which defines skip(task).
export function buildMethodPrompt(
  program: Program,
  process: ProgramProcess,
  key: MethodCodeKey,
  draft: string,
  request: string,
  language: FuncLanguage = "bash",
): string {
  const method = processMethod(key);
  const funcName = `${process.name}_${method.name}`;
  const python = language === "python" && key === "skipCode";
  // A method that receives the options of the task reads them as a Bash
  // function does (or as task.value does, the same way), whatever the
  // language of the process: the value of a value descriptor, not its path
  const optionsReader: ProgramProcess = { ...process, language: "bash" };

  const sections = [
    [
      `# Write the \`${method.name}\` method of the DeBasher process \`${process.name}\``,
      "",
      `DeBasher runs programs made of processes, each of which receives its options from the engine and may define methods that the engine calls around its work. Write the \`${method.name}\` method of the process described below.`,
    ],
    [
      "## How the engine runs the method",
      "",
      ...(python
        ? [
            `- The method is a Python file that defines a function \`skip(task)\`, which the Bash function \`${funcName}()\` of the module calls through the engine, whatever the language of the process.`,
            ...PYTHON_SKIP_RULES.map(rule => `- ${rule}`),
          ]
        : [
            `- The method is a Bash function, \`${funcName}()\`, whatever the language of the process. You write only its body: the line \`${funcName}()\` and the braces around the body are already written.`,
            ...method.rules.map(rule => `- ${rule}`),
          ]),
    ],
    ["## The program", "", `- Name: \`${program.name}\``, ...describedAs(program.description)],
    [
      "## The process",
      "",
      `- Name: \`${process.name}\``,
      ...describedAs(process.description),
      ...(process.optionsHandler.mode === "standard"
        ? []
        : [`- Tasks: the process runs as several tasks (options handler mode \`${process.optionsHandler.mode}\`).`]),
    ],
    method.receivesOptions || process.options.length === 0
      ? optionsSection(program, optionsReader)
      : ["## The options", "", "The method receives no options; the options of the process, which its code reads, show what it works on:", "", ...optionsSection(program, process).slice(2)],
    processCodeSection(process, "what the process does"),
    codeSection(python && isFuncTemplate(draft) ? "" : draft, python ? "python" : "bash"),
    [
      "## What the code has to do",
      "",
      request.trim() !== ""
        ? request.trim()
        : `Write the \`${method.name}\` method that the description and the code of the process call for.`,
    ],
    commentSection(python ? "python" : "bash", [
      python
        ? "- A docstring for `skip`: when the task is skipped for this process, and why when it is not obvious."
        : "- A comment at the start of the body: what the method does for this process, and why when it is not obvious.",
    ]),
    [
      "## What to return",
      "",
      ASK_BEFORE_GUESSING,
      "",
      python
        ? "Return the whole file in a single fenced code block tagged `python`, with nothing else inside the block: the function `skip(task)` and what it needs."
        : `Return the whole body of the method in a single fenced code block tagged \`bash\`, with nothing else inside the block, and without the line \`${funcName}()\` and the braces around the body.`,
    ],
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}
