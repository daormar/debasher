import type { ProgramOption } from "../../src/models/option";
import type { ProgramProcess } from "../../src/models/process";
import type { Program } from "../../src/models/program";
import type { SeqProcess } from "../../src/models/seqProcess";

// The program as the answers of the MCP tools show it: short text for a
// model to read, one line per process, option and connection, naming each
// by its name or label and never by an id.

function quoted(text: string): string {
  return JSON.stringify(text);
}

// The fields of an object that are set, as "key=value".
function setFields(fields: object): string {
  return Object.entries(fields)
    .filter(([, value]) => value !== undefined && value !== null && value !== "" && value !== false)
    .filter(([, value]) => !(Array.isArray(value) && value.length === 0))
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
}

// The name of the option of `process` with the given id.
function labelOf(process: ProgramProcess, optionId: string | undefined): string | undefined {
  return process.options.find(option => option.id === optionId)?.label;
}

export function optionLine(process: ProgramProcess, option: ProgramOption): string {
  const traits = [
    option.direction,
    option.dataType,
    option.channel !== "none" ? `channel ${option.channel}` : null,
    option.mirror ? "mirrored" : null,
    option.fifoTag === "external" ? "external input" : null,
    option.commandLine ? "command line" : null,
    option.taskShaping ? "task shaping" : null,
    option.fromProcessSpec ? "from process spec" : null,
    option.mandatory ? "mandatory" : null,
    option.countSourceOptionId ? `count from ${labelOf(process, option.countSourceOptionId)}` : null,
    option.value ? `value ${quoted(option.value)}` : null,
  ].filter(Boolean);
  const description = option.description ? `: ${option.description}` : "";
  return `${option.label} (${traits.join(", ")})${description}`;
}

function processHeader(process: ProgramProcess): string {
  const traits = [
    process.nodeKind ?? null,
    process.initiator ? "initiator" : null,
    process.nodeKind ? null : process.language,
    process.optionsHandler.mode !== "standard" ? `options handler ${process.optionsHandler.mode}` : null,
    process.groupSource ? `added with program ${quoted(process.groupSource.programName)}` : null,
  ].filter(Boolean);
  return `${process.name} (${traits.join(", ")})`;
}

function processLines(process: ProgramProcess): string[] {
  return [
    processHeader(process),
    ...(process.description ? [`  ${process.description}`] : []),
    ...process.options.map(option => `  ${optionLine(process, option)}`),
  ];
}

function seqProcessLine(seqProcess: SeqProcess): string {
  const traits = [
    seqProcess.language,
    seqProcess.groupSource ? `added with program ${quoted(seqProcess.groupSource.programName)}` : null,
  ].filter(Boolean);
  const description = seqProcess.description ? `: ${seqProcess.description}` : "";
  return `${seqProcess.name} (${traits.join(", ")})${description}`;
}

export function connectionLines(program: Program): string[] {
  const byId = new Map(program.processes.map(process => [process.id, process]));
  return program.edges.map(edge => {
    const source = byId.get(edge.sourceProcessId);
    const target = byId.get(edge.targetProcessId);
    return (
      `${source?.name} ${source && labelOf(source, edge.sourceOptionId)} -> ` +
      `${target?.name} ${target && labelOf(target, edge.targetOptionId)}`
    );
  });
}

function section(title: string, lines: string[]): string[] {
  return lines.length === 0 ? [`${title}: none`] : [`${title}:`, ...lines.map(line => `  ${line}`)];
}

// The settings of the program: everything but its processes and connections.
export function settingsLines(program: Program): string[] {
  return [
    `Program ${quoted(program.name)} (${program.programType})`,
    `Home directory: ${program.homeDir || "(not saved)"}`,
    `Output directory: ${program.outputDir || "(not set)"}`,
    ...(program.description ? [`Description: ${program.description}`] : []),
    ...section("Preamble", program.preamble ? program.preamble.split("\n") : []),
    ...section("Environment variables", Object.entries(program.envVars).map(([name, value]) => `${name}=${value}`)),
    `Execution options: ${setFields(program.executionOptions)}`,
    ...section("Program options", Object.entries(program.programOptions).map(([label, value]) => `${label} ${value}`)),
    ...(program.sharedDirs.length > 0 ? [`Shared directories: ${program.sharedDirs.join(", ")}`] : []),
  ];
}

// The whole program, without the code of its processes.
export function describeProgram(program: Program): string {
  return [
    ...settingsLines(program),
    ...section("Processes", program.processes.flatMap(processLines)),
    ...(program.programType === "general"
      ? section("Sequential processes", program.seqProcesses.map(seqProcessLine))
      : []),
    ...section("Connections", connectionLines(program)),
  ].join("\n");
}

function codeBlock(title: string, code: string | undefined): string[] {
  return code ? [`${title}:`, code] : [];
}

// One process in full, its code included.
export function describeProcess(program: Program, process: ProgramProcess): string {
  const { computationalSpecs, additionalSpecs, additionalMethods, optionsHandler, nodeCode } = process;
  const connections = connectionLines(program).filter(line =>
    line.startsWith(`${process.name} `) || line.includes(`-> ${process.name} `)
  );
  return [
    ...processLines(process),
    `Computational specs: ${setFields(computationalSpecs) || "none"}`,
    `Additional specs: ${setFields(additionalSpecs) || "none"}`,
    ...section("Connections", connections),
    ...codeBlock("Options handler code", optionsHandler.arrayCode ?? optionsHandler.generatorSizeCode ?? optionsHandler.manualCode),
    ...Object.entries(additionalMethods).flatMap(([name, code]) => codeBlock(`Method ${name}`, code)),
    ...(nodeCode
      ? Object.entries(nodeCode).flatMap(([part, code]) => codeBlock(`Node code ${part}`, code))
      : codeBlock("Code", process.code)),
  ].join("\n");
}

export function describeSeqProcess(seqProcess: SeqProcess): string {
  return [
    seqProcessLine(seqProcess),
    `Computational specs: ${setFields(seqProcess.computationalSpecs) || "none"}`,
    `Additional specs: ${setFields(seqProcess.additionalSpecs) || "none"}`,
    ...codeBlock("Code", seqProcess.code),
  ].join("\n");
}

function prefixed(prefix: string, lines: string[]): string[] {
  return lines.map(line => `${prefix}${line}`);
}

function codeLines(prefix: string, code: string | undefined): string[] {
  return code ? prefixed(prefix, code.split("\n")) : [];
}

// Every line of the program, code included, each saying on its own what it
// belongs to, so that a line that changes is understood without the lines
// around it.
function selfContainedLines(program: Program): string[] {
  return [
    // The lines of the settings that hold a list are given apart below.
    ...settingsLines(program).filter(line => !line.startsWith("  ") && !line.endsWith(":")),
    ...codeLines("Preamble | ", program.preamble),
    ...Object.entries(program.envVars).map(([name, value]) => `Environment variable ${name}=${value}`),
    ...Object.entries(program.programOptions).map(([label, value]) => `Program option ${label} ${value}`),
    ...program.processes.flatMap(process => {
      const { computationalSpecs, additionalSpecs, additionalMethods, optionsHandler, nodeCode } = process;
      const at = `Process ${process.name}`;
      return [
        `${at}: ${processHeader(process)}`,
        ...(process.description ? [`${at} description: ${process.description}`] : []),
        ...process.options.map(option => `${at} option ${optionLine(process, option)}`),
        `${at} computational specs: ${setFields(computationalSpecs) || "none"}`,
        `${at} additional specs: ${setFields(additionalSpecs) || "none"}`,
        ...codeLines(`${at} options handler code | `, optionsHandler.arrayCode ?? optionsHandler.generatorSizeCode ?? optionsHandler.manualCode),
        ...Object.entries(additionalMethods).flatMap(([name, code]) => codeLines(`${at} method ${name} | `, code)),
        ...(nodeCode
          ? Object.entries(nodeCode).flatMap(([part, code]) => codeLines(`${at} node code ${part} | `, code))
          : codeLines(`${at} code | `, process.code)),
        `${at} position: ${process.position.x}, ${process.position.y}`,
      ];
    }),
    ...program.seqProcesses.flatMap(seqProcess => [
      `Sequential process ${seqProcessLine(seqProcess)}`,
      `Sequential process ${seqProcess.name} computational specs: ${setFields(seqProcess.computationalSpecs) || "none"}`,
      `Sequential process ${seqProcess.name} additional specs: ${setFields(seqProcess.additionalSpecs) || "none"}`,
      ...codeLines(`Sequential process ${seqProcess.name} code | `, seqProcess.code),
    ]),
    ...connectionLines(program).map(line => `Connection ${line}`),
  ];
}

/**
 * What changed from `before` to `after`, as the lines that one has and the
 * other does not (see selfContainedLines), "-" for a line removed and "+"
 * for a line added, in the order of a longest common subsequence of the two.
 */
export function describeChanges(before: Program, after: Program): string {
  const old = selfContainedLines(before);
  const now = selfContainedLines(after);
  // common[i][j]: the length of a longest common subsequence of old[i..]
  // and now[j..].
  const common = Array.from({ length: old.length + 1 }, () => Array.from({ length: now.length + 1 }, () => 0));
  for (let i = old.length - 1; i >= 0; i--) {
    for (let j = now.length - 1; j >= 0; j--) {
      common[i][j] = old[i] === now[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
    }
  }
  const lines: string[] = [];
  let i = 0;
  let j = 0;
  while (i < old.length || j < now.length) {
    if (i < old.length && j < now.length && old[i] === now[j]) {
      i++;
      j++;
    } else if (i < old.length && (j === now.length || common[i + 1][j] >= common[i][j + 1])) {
      lines.push(`- ${old[i++]}`);
    } else {
      lines.push(`+ ${now[j++]}`);
    }
  }
  return lines.length > 0 ? lines.join("\n") : "(nothing changes)";
}

// The last `count` lines of `text`, all of them when `count` is 0.
export function lastLines(text: string, count: number): string {
  const lines = text.replace(/\n$/, "").split("\n");
  if (count <= 0 || lines.length <= count) {
    return text;
  }
  return [`(the last ${count} of ${lines.length} lines)`, ...lines.slice(-count)].join("\n");
}
