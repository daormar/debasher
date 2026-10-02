import type { AdditionalMethods, ProgramProcess } from "./process";
import type { Program } from "./program";
import { ASK_BEFORE_GUESSING, describedAs, optionsSection } from "./codePrompt";
import { codeSection, processCodeSection } from "./optionsHandlerPrompt";
import { processMethod } from "./processMethods";

// The code prompt of an additional method of a process: as that of the
// code of a process (see buildCodePrompt), with the rules of the method,
// from PROCESS_METHODS, and the code of the process for context, since a
// method acts on what the process does (the files it writes, the
// environments it activates).
export function buildMethodPrompt(
  program: Program,
  process: ProgramProcess,
  key: keyof AdditionalMethods,
  draft: string,
  request: string,
): string {
  const method = processMethod(key);
  const funcName = `${process.name}_${method.name}`;

  const sections = [
    [
      `# Write the \`${method.name}\` method of the DeBasher process \`${process.name}\``,
      "",
      `DeBasher runs programs made of processes, each of which receives its options from the engine and may define methods that the engine calls around its work. Write the \`${method.name}\` method of the process described below.`,
    ],
    [
      "## How the engine runs the method",
      "",
      `- The method is a Bash function, \`${funcName}()\`, whatever the language of the process. You write only its body: the line \`${funcName}()\` and the braces around the body are already written.`,
      ...method.rules.map(rule => `- ${rule}`),
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
      ? optionsSection(program, process)
      : ["## The options", "", "The method receives no options; the options of the process, which its code reads, show what it works on:", "", ...optionsSection(program, process).slice(2)],
    processCodeSection(process, "what the process does"),
    codeSection(draft),
    [
      "## What the code has to do",
      "",
      request.trim() !== ""
        ? request.trim()
        : `Write the \`${method.name}\` method that the description and the code of the process call for.`,
    ],
    [
      "## What to return",
      "",
      ASK_BEFORE_GUESSING,
      "",
      `Return the whole body of the method in a single fenced code block tagged \`bash\`, with nothing else inside the block, and without the line \`${funcName}()\` and the braces around the body.`,
    ],
  ];

  return sections.map(lines => lines.join("\n")).join("\n\n") + "\n";
}
