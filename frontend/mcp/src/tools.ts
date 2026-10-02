import { z } from "zod";

import { LaunchRecordConflict, TEST_OUTCOME_MESSAGES } from "../../src/api/executionApi";
import type { FileEntry } from "../../src/api/programFilesApi";
import { RevisionConflict } from "../../src/api/revisionConflict";
import { hasSupervisor } from "../../src/models/node";
import type { InspectNodeCommand, NodeSummary } from "../../src/models/nodeState";
import { summaryRows } from "../../src/models/nodeState";
import type { ProgramProcess } from "../../src/models/process";
import type { Program } from "../../src/models/program";
import { normalizeProgram } from "../../src/models/programEdits";
import { layoutProcesses } from "../../src/models/programLayout";
import type { NamedEdit } from "../../src/models/programRefs";
import {
  HARD_KILL_CONSEQUENCES,
  offersRelaunchNode,
  offersRestartNode,
  orderlyStopOutcome,
  relaunchOutcome,
  residentRunPhase,
  restartNodeWarning,
  restartsWithBothEnds,
  snapshotOutcome,
} from "../../src/models/residentRun";
import type { TalkCandidate } from "../../src/models/residentTalk";
import { entryText, talkCandidates } from "../../src/models/residentTalk";
import { offersAddTest, testFilePath, testSkeleton } from "../../src/models/testSkeleton";
import { createEmptyProgram, NoProgramMetadata } from "../../src/storage/programStorage";
import type { Backend } from "./backend";
import { describeProcess, describeProgram, describeSeqProcess, lastLines, optionLine } from "./describe";
import type { Answer, EditCall } from "./editing";
import { editProgram, loadProgram, Refusal } from "./editing";
import * as schemas from "./schemas";

// The MCP tools: each a name, a description for the agent, the schema of
// its parameters and what it does with the backend (see "The MCP tools" in
// doc/design_doc_webui.md).

export interface ToolAnnotations {
  readOnlyHint?: boolean;
  destructiveHint?: boolean;
}

export interface Tool {
  name: string;
  description: string;
  input: z.ZodRawShape;
  annotations: ToolAnnotations;
  run: (backend: Backend, args: Record<string, unknown>) => Promise<Answer>;
}

function tool<Shape extends z.ZodRawShape>(
  name: string,
  description: string,
  input: Shape,
  annotations: ToolAnnotations,
  run: (backend: Backend, args: z.infer<z.ZodObject<Shape>>) => Promise<Answer | string>
): Tool {
  return {
    name,
    description,
    input,
    annotations,
    run: async (backend, args) => {
      const answer = await run(backend, args as z.infer<z.ZodObject<Shape>>);
      return typeof answer === "string" ? { text: answer } : answer;
    },
  };
}

const READS = { readOnlyHint: true };
const EDITS = { readOnlyHint: false, destructiveHint: false };
const DELETES = { readOnlyHint: false, destructiveHint: true };

function editCall(args: { dry_run?: boolean; detach_groups?: boolean }): EditCall {
  return { dryRun: args.dry_run, detachGroups: args.detach_groups };
}

// A tool that applies the named edits that its parameters stand for.
function editTool<Shape extends z.ZodRawShape>(
  name: string,
  description: string,
  input: Shape,
  edits: (args: z.infer<z.ZodObject<Shape>> & { home_dir: string }, backend: Backend) => NamedEdit[] | Promise<NamedEdit[]>
): Tool {
  return tool(
    name,
    `${description} Applied whole or not at all; dry_run answers with a proposal instead.`,
    { home_dir: schemas.homeDir, ...input, ...schemas.editFlags },
    EDITS,
    async (backend, args) => {
      const call = args as z.infer<z.ZodObject<Shape>> & { home_dir: string; dry_run?: boolean; detach_groups?: boolean };
      return editProgram(backend, call.home_dir, await edits(call, backend), editCall(call));
    }
  );
}

function processOf(program: Program, name: string): ProgramProcess {
  const process = program.processes.find(candidate => candidate.name === name);
  if (!process) {
    throw new Refusal(`There is no process named "${name}".`);
  }
  return process;
}

// Refuses a directory that already holds program metadata, which a save of
// a program not loaded from it would replace.
async function refuseProgramIn(backend: Backend, homeDir: string): Promise<void> {
  try {
    await backend.loadProgram(homeDir);
  } catch (err) {
    if (err instanceof NoProgramMetadata) {
      return;
    }
    throw err;
  }
  throw new Refusal(`${homeDir} already holds a program: load it with get_program, or choose another directory.`);
}

// Saves a program that was not loaded from `homeDir` into it.
async function saveNewProgram(backend: Backend, program: Program, homeDir: string): Promise<string> {
  const { revision } = await backend.saveProgram(program, homeDir);
  return describeProgram({ ...program, homeDir, revision });
}

// The program, which a request of the run needs to have an output directory.
async function programWithOutputDir(backend: Backend, homeDir: string): Promise<Program> {
  const program = await loadProgram(backend, homeDir);
  if (!program.outputDir.trim()) {
    throw new Refusal("The program has no output directory: set one with set_program_settings (outputDir).");
  }
  return program;
}

// Sends a request of the run that saves the program first.
async function savingFirst<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (err) {
    if (err instanceof RevisionConflict) {
      throw new Refusal(`${err.message} Read the program again with get_program.`);
    }
    throw err;
  }
}

function requireResident(program: Program, what: string): void {
  if (program.programType !== "resident") {
    throw new Refusal(`${what} is only for a resident program.`);
  }
}

function withOutput(text: string, output: string | null | undefined, lines: number): string {
  return output?.trim() ? `${text}\nWhat the tool printed:\n${lastLines(output, lines)}` : text;
}

const OUTPUT_LINES = 40;

const lines = z.number().int().min(0).optional()
  .describe(`How many of the last lines to show; 0 for all. By default ${OUTPUT_LINES}.`);

const task = z.number().int().min(0).optional()
  .describe("The task of a process that runs as several tasks (see get_process_tasks).");

const confirm = z.boolean().optional().describe("Confirms an action that cannot be undone.");

// ---------------------------------------------------------------
// Reading
// ---------------------------------------------------------------

const readingTools = [

  tool(
    "get_program",
    "The program saved in a home directory: its settings, its processes with their options, its sequential processes and its connections, without the code of the processes.",
    { home_dir: schemas.homeDir },
    READS,
    async (backend, { home_dir }) => describeProgram(await loadProgram(backend, home_dir))
  ),

  tool(
    "get_process",
    "One process, or sequential process, of the program in full, its code included.",
    { home_dir: schemas.homeDir, process: schemas.processName },
    READS,
    async (backend, { home_dir, process }) => {
      const program = await loadProgram(backend, home_dir);
      const seqProcess = program.seqProcesses.find(candidate => candidate.name === process);
      return seqProcess ? describeSeqProcess(seqProcess) : describeProcess(program, processOf(program, process));
    }
  ),

  tool(
    "import_module",
    "Imports a DeBasher module (a .sh file) as a program, places its processes in layers by their connections, and saves it into a new home directory.",
    {
      script_path: z.string().min(1).describe("The path of the module."),
      home_dir: schemas.homeDir.describe("A directory that holds no program yet."),
      debasher_mod_dir: z.string().optional().describe("Directories where the engine looks for the modules that the module loads."),
    },
    EDITS,
    async (backend, { script_path, home_dir, debasher_mod_dir }) => {
      await refuseProgramIn(backend, home_dir);
      const program = normalizeProgram(await backend.importProgram(script_path, debasher_mod_dir ?? ""));
      return `Imported and saved.\n${await saveNewProgram(backend, program, home_dir)}`;
    }
  ),

];

// ---------------------------------------------------------------
// The library
// ---------------------------------------------------------------

const libraryTools = [

  tool(
    "search_library",
    "The processes (in a general program) or nodes (in a resident program) that the modules loaded by the preamble of the program define, which add_process brings with their options and code.",
    {
      home_dir: schemas.homeDir,
      query: z.string().optional().describe("Only the names that hold this text, in any case."),
    },
    READS,
    async (backend, { home_dir, query }) => {
      const { programType, preamble, envVars } = await loadProgram(backend, home_dir);
      const names = programType === "resident"
        ? (await backend.suggestNodes(preamble, envVars)).map(node => `${node.name} (${node.nodeKind})`)
        : await backend.suggestProcessNames(preamble, envVars);
      const found = names.filter(name => !query || name.toLowerCase().includes(query.toLowerCase()));
      return found.length > 0 ? found.join("\n") : "Nothing found.";
    }
  ),

  tool(
    "get_library_process",
    "What a process or node of the library brings: its description, options and code.",
    { home_dir: schemas.homeDir, name: z.string().min(1) },
    READS,
    async (backend, { home_dir, name }) => {
      const { programType, preamble, envVars } = await loadProgram(backend, home_dir);
      if (programType === "resident") {
        const info = await backend.getNodeInfo(preamble, envVars, name);
        const process = { name, options: info.options } as ProgramProcess;
        return [
          `${name} (${info.nodeKind})`,
          ...(info.description ? [info.description] : []),
          ...info.options.map(option => `  ${optionLine(process, option)}`),
          ...Object.entries(info.nodeCode).flatMap(([part, code]) => code ? [`Node code ${part}:`, code] : []),
        ].join("\n");
      }
      const info = await backend.getProcessInfo(preamble, envVars, name);
      if (!info) {
        throw new Refusal(`No module of the preamble defines a process named "${name}".`);
      }
      return [
        `${name} (${info.language})`,
        ...(info.description ? [info.description] : []),
        ...info.options.map(option =>
          `  ${option.label} (${[option.dataType, option.commandLine ? "command line" : null, option.mandatory ? "mandatory" : null]
            .filter(Boolean).join(", ")})${option.description ? `: ${option.description}` : ""}`
        ),
        ...(info.code ? ["Code:", info.code] : []),
      ].join("\n");
    }
  ),

];

// ---------------------------------------------------------------
// Editing
// ---------------------------------------------------------------

const seqProcessEntry = schemas.seqProcessChanges.extend({
  name: z.string().min(1).describe("The name of the sequential process."),
  newName: z.string().optional().describe("A new name for an existing one."),
  remove: z.boolean().optional().describe("Removes it."),
}).strict();

const editingTools = [

  tool(
    "create_program",
    "Creates an empty program and saves it into a new home directory.",
    {
      home_dir: schemas.homeDir.describe("A directory that holds no program yet."),
      name: z.string().min(1),
      program_type: z.enum(["general", "resident"]).optional()
        .describe("general (by default) or resident; it cannot be changed afterwards."),
      description: z.string().optional(),
      preamble: z.string().optional(),
      output_dir: z.string().optional(),
    },
    EDITS,
    async (backend, { home_dir, name, program_type, description, preamble, output_dir }) => {
      await refuseProgramIn(backend, home_dir);
      const program = {
        ...createEmptyProgram(name, program_type ?? "general"),
        description: description ?? "",
        preamble: preamble ?? "",
        outputDir: output_dir ?? "",
      };
      return `Created.\n${await saveNewProgram(backend, program, home_dir)}`;
    }
  ),

  editTool(
    "add_process",
    "Adds a process. A process (or node) that a module of the preamble defines comes with its description, options and code (see search_library); in a resident program, any other node needs nodeKind.",
    schemas.addProcessFields,
    ({ name, nodeKind, changes, options, position }) => [{ op: "addProcess", name, nodeKind, changes, options, position }]
  ),

  editTool(
    "update_process",
    "Changes a process: its name, description, code, options handler, specifications, methods or, for a node, its code parts.",
    { process: schemas.processName, changes: schemas.processChanges },
    ({ process, changes }) => [{ op: "updateProcess", process, changes }]
  ),

  editTool(
    "remove_process",
    "Removes a process with its connections.",
    { process: schemas.processName },
    ({ process }) => [{ op: "removeProcess", process }]
  ),

  editTool(
    "move_process",
    "Moves a process on the canvas, or, with layout, lays out every process again in layers by their connections.",
    {
      process: schemas.processName.optional(),
      position: schemas.position.optional(),
      layout: z.boolean().optional(),
    },
    async ({ home_dir, process, position, layout }, backend) => {
      if (layout) {
        const laidOut = layoutProcesses(await loadProgram(backend, home_dir));
        return laidOut.processes.map(({ name, position: place }) => ({ op: "moveProcess", process: name, position: place }));
      }
      if (!process || !position) {
        throw new Refusal("Give a process and its position, or layout.");
      }
      return [{ op: "moveProcess", process, position }];
    }
  ),

  editTool(
    "add_option",
    "Adds an option to a process. Its direction follows from its label: output when it starts with -out.",
    { process: schemas.processName, label: schemas.optionLabel, fields: schemas.optionFields.optional() },
    ({ process, label, fields }) => [{ op: "addOption", process, label, fields }]
  ),

  editTool(
    "update_option",
    "Changes an option of a process.",
    { process: schemas.processName, option: schemas.optionLabel, changes: schemas.optionChanges },
    ({ process, option, changes }) => [{ op: "updateOption", process, option, changes }]
  ),

  editTool(
    "remove_option",
    "Removes an option of a process.",
    { process: schemas.processName, option: schemas.optionLabel },
    ({ process, option }) => [{ op: "removeOption", process, option }]
  ),

  editTool(
    "connect",
    "Connects an output of a process to an input of another, or of the same one; the input then takes its value from the output.",
    { from: schemas.optionRef, to: schemas.optionRef },
    ({ from, to }) => [{ op: "connect", from, to }]
  ),

  editTool(
    "disconnect",
    "Removes the connection between an output and an input.",
    { from: schemas.optionRef, to: schemas.optionRef },
    ({ from, to }) => [{ op: "disconnect", from, to }]
  ),

  editTool(
    "set_program_settings",
    "Changes the settings of the program: name, description, preamble, environment variables, output directory, execution options, program options and shared directories.",
    {
      changes: schemas.programFields.optional(),
      env_vars: z.record(z.string(), z.string()).optional().describe("Environment variables to set, by name."),
    },
    ({ changes, env_vars }) => [
      ...(changes ? [{ op: "setProgramFields" as const, changes }] : []),
      ...Object.entries(env_vars ?? {}).map(([name, value]) => ({ op: "setEnvVar" as const, name, value })),
    ]
  ),

  editTool(
    "set_seq_processes",
    "Adds, changes or removes sequential processes (general programs only): code that a process runs as a step. Each entry adds the one it names, or changes or removes it if it exists.",
    { seq_processes: z.array(seqProcessEntry).min(1) },
    async ({ home_dir, seq_processes }, backend) => {
      const existing = new Set((await loadProgram(backend, home_dir)).seqProcesses.map(seqProcess => seqProcess.name));
      return seq_processes.map(({ name, newName, remove, ...changes }): NamedEdit => {
        if (remove) {
          return { op: "removeSeqProcess", name };
        }
        if (!existing.has(name)) {
          return { op: "addSeqProcess", name, changes };
        }
        return { op: "updateSeqProcess", name, changes: newName ? { ...changes, name: newName } : changes };
      });
    }
  ),

  editTool(
    "apply_edits",
    "Applies a list of named edits in order, each one able to name what an earlier one added: processes and sequential processes by name, options by process and label, connections by their two ends.",
    { edits: z.array(schemas.namedEdit).min(1) },
    ({ edits }) => edits as NamedEdit[]
  ),

];

// ---------------------------------------------------------------
// Running
// ---------------------------------------------------------------

const outputKinds = {
  stdout: "getProcessStdout",
  scheduler: "getProcessSchedOut",
  options: "getProcessOpts",
} as const;

// The process statuses, none while the output directory holds no run.
async function processStatuses(backend: Backend, program: Program): Promise<Record<string, string>> {
  try {
    return (await backend.getProcessStatuses(program)).statuses;
  } catch {
    return {};
  }
}

function statusLines(statuses: Record<string, string>): string[] {
  return Object.entries(statuses).map(([name, status]) => `  ${name}: ${status}`);
}

// How long run_program waits for the statuses of a general program to show
// the run it launched, and how often it reads them meanwhile.
export const RUN_START_WAIT = { totalMs: 10000, everyMs: 500 };

/**
 * The process statuses once they show the run just launched in the
 * background: a process in progress, or statuses other than those `before`
 * it. The first readings after a launch may still show the run before; past
 * the wait, the last reading.
 */
async function statusesOfLaunchedRun(
  backend: Backend,
  program: Program,
  before: Record<string, string>
): Promise<Record<string, string>> {
  const deadline = Date.now() + RUN_START_WAIT.totalMs;
  for (;;) {
    const statuses = await processStatuses(backend, program);
    const shown = Object.values(statuses).includes("IN-PROGRESS") || JSON.stringify(statuses) !== JSON.stringify(before);
    if (shown || Date.now() >= deadline) {
      return statuses;
    }
    await new Promise(resolve => setTimeout(resolve, RUN_START_WAIT.everyMs));
  }
}

const runningTools = [

  tool(
    "validate_program",
    "Validates the program as the Run menu does: everything but launching the processes (debasher_exec --validate), then checks the options of the program. Both save the program first.",
    { home_dir: schemas.homeDir, lines },
    READS,
    async (backend, { home_dir, lines: count }) => {
      const program = await programWithOutputDir(backend, home_dir);
      const validation = await savingFirst(() => backend.validateProgram(program));
      const check = await savingFirst(() => backend.checkProgramOptions({ ...program, revision: validation.revision }));
      return [
        "Validation:", lastLines(validation.output, count ?? OUTPUT_LINES),
        "Program options:", lastLines(check.output, count ?? OUTPUT_LINES),
      ].join("\n");
    }
  ),

  tool(
    "run_program",
    "Saves and launches the program in its output directory. A general program runs in the background: follow it with get_status. The launch of a resident program is waited for.",
    {
      home_dir: schemas.homeDir,
      resume_changed_program: z.boolean().optional()
        .describe("For a resident program whose output directory holds program state that another program produced: resume it with this program."),
    },
    EDITS,
    async (backend, { home_dir, resume_changed_program }) => {
      const program = await programWithOutputDir(backend, home_dir);
      if ((await backend.fetchProgramStatus(program)).state === "in-progress") {
        throw new Refusal("A run is already in progress for this output directory.");
      }
      const before = await processStatuses(backend, program);
      let result;
      try {
        result = await savingFirst(() => backend.runProgram(program, resume_changed_program ?? false));
      } catch (err) {
        if (err instanceof LaunchRecordConflict) {
          throw new Refusal(
            "The output directory holds program state that " +
            (err.hasLaunchRecord ? "another program produced" : "no launch record describes") +
            ": call again with resume_changed_program to resume it with this program, or reset it with " +
            "reset_program_state to start afresh."
          );
        }
        throw err;
      }
      if (result.exitCode !== null && result.exitCode !== 0) {
        throw new Refusal(withOutput(`The launch failed: debasher_exec ended with exit code ${result.exitCode}.`, result.output, OUTPUT_LINES));
      }
      if (!result.started) {
        return "The program was not launched.";
      }
      if (program.programType === "resident") {
        return "Launched. Follow the program with get_status.";
      }
      const statuses = await statusesOfLaunchedRun(backend, program, before);
      return ["Launched. Follow the run with get_status.", "Processes:", ...statusLines(statuses)].join("\n");
    }
  ),

  tool(
    "stop_program",
    "Stops the run of the program. A resident program stops in order, every node halting in the same round; kill ends it at once instead, which needs confirm.",
    { home_dir: schemas.homeDir, kill: z.boolean().optional(), confirm },
    DELETES,
    async (backend, { home_dir, kill, confirm: confirmed }) => {
      const program = await programWithOutputDir(backend, home_dir);
      if (program.programType !== "resident") {
        const { output } = await backend.stopProgram(program);
        return withOutput("Stopped.", output, OUTPUT_LINES);
      }
      if (kill) {
        if (!confirmed) {
          throw new Refusal(`Killing the program needs confirm. ${HARD_KILL_CONSEQUENCES}`);
        }
        const { output } = await backend.killProgram(program);
        return withOutput("Killed.", output, OUTPUT_LINES);
      }
      const { output, exitCode } = await backend.stopProgram(program);
      return withOutput(orderlyStopOutcome(exitCode), output, OUTPUT_LINES);
    }
  ),

  tool(
    "get_status",
    "The run of the program in its output directory: its phase and the status of each process, and, for a resident program, the notices of its nodes.",
    { home_dir: schemas.homeDir, lines },
    READS,
    async (backend, { home_dir, lines: count }) => {
      const program = await programWithOutputDir(backend, home_dir);
      const { statuses, hasProgramState, notices, output } = await backend.getProcessStatuses(program);
      const lines = statusLines(statuses);
      if (program.programType === "resident") {
        return [
          `Run phase: ${residentRunPhase(statuses, hasProgramState, null)}`,
          ...(lines.length > 0 ? ["Processes:", ...lines] : []),
          ...notices.map(notice =>
            `Notice of ${notice.process}${notice.task === null ? "" : `:${notice.task}`}: ${notice.level}: ${notice.text}`
          ),
        ].join("\n");
      }
      const { state } = await backend.fetchProgramStatus(program);
      return [
        `Run state: ${state}`,
        ...(lines.length > 0 ? ["Processes:", ...lines] : []),
        ...(state === "unfinished" && output.trim() ? ["What debasher_status printed:", lastLines(output, count ?? OUTPUT_LINES)] : []),
      ].join("\n");
    }
  ),

  tool(
    "get_process_output",
    "What a process of the run left: its standard output, its scheduler output, its options as given, or its resolved options.",
    {
      home_dir: schemas.homeDir,
      process: schemas.processName,
      kind: z.enum(["stdout", "scheduler", "options", "resolved_options"]).optional().describe("stdout by default."),
      task,
      lines,
    },
    READS,
    async (backend, { home_dir, process, kind, task: taskIndex, lines: count }) => {
      const program = await programWithOutputDir(backend, home_dir);
      processOf(program, process);
      if (kind === "resolved_options") {
        const values = await backend.getProcessResolvedOptions(program, process, taskIndex);
        const entries = Object.entries(values);
        return entries.length > 0 ? entries.map(([label, value]) => `${label} ${value}`).join("\n") : "Nothing yet: the process has not run.";
      }
      const output = await backend[outputKinds[kind ?? "stdout"]](program, process, taskIndex);
      return output ? lastLines(output, count ?? OUTPUT_LINES) : "(empty)";
    }
  ),

  tool(
    "get_process_tasks",
    "The tasks of a process that ran as several (an array or a generator), whose output get_process_output reads one by one; none for a process that runs as one.",
    { home_dir: schemas.homeDir, process: schemas.processName },
    READS,
    async (backend, { home_dir, process }) => {
      const program = await programWithOutputDir(backend, home_dir);
      processOf(program, process);
      const tasks = await backend.getProcessTasks(program, process);
      return tasks.length > 0 ? `Tasks: ${tasks.join(", ")}` : "The process runs as one task.";
    }
  ),

  tool(
    "reset_output_dir",
    "Deletes everything in the output directory of the program. Needs confirm.",
    { home_dir: schemas.homeDir, confirm },
    DELETES,
    async (backend, { home_dir, confirm: confirmed }) => {
      const program = await programWithOutputDir(backend, home_dir);
      if (!confirmed) {
        throw new Refusal(`This deletes everything in ${program.outputDir}: call again with confirm.`);
      }
      return (await backend.resetOutputDir(program)) ? "The output directory was emptied." : "There was nothing to reset.";
    }
  ),

  tool(
    "reset_program_state",
    "Sets the program state of a resident program aside, or deletes it, so that the next launch starts afresh. Needs confirm.",
    { home_dir: schemas.homeDir, delete: z.boolean().optional().describe("Delete it rather than set it aside."), confirm },
    DELETES,
    async (backend, { home_dir, delete: deleteState, confirm: confirmed }) => {
      const program = await programWithOutputDir(backend, home_dir);
      requireResident(program, "Resetting the program state");
      if (!confirmed) {
        throw new Refusal("The next launch would start afresh, without the program state: call again with confirm.");
      }
      const { output, exitCode } = await backend.resetProgramState(program, deleteState ?? false);
      return withOutput(exitCode === 0 ? "The program state was reset." : `The reset ended with exit code ${exitCode}.`, output, OUTPUT_LINES);
    }
  ),

];

// ---------------------------------------------------------------
// Resident programs
// ---------------------------------------------------------------

// The FIFO of "Talk to FIFOs" that the call names, or a refusal.
function talkCandidate(candidates: TalkCandidate[], process: string, option: string, what: string): TalkCandidate {
  const found = candidates.find(candidate => candidate.processName === process && candidate.option.label === option);
  if (!found) {
    throw new Refusal(`${process} ${option} is not ${what}: see list_fifos.`);
  }
  return found;
}

const residentTools = [

  tool(
    "inspect_node",
    "What a node of a running or stopped resident program keeps: a summary, a checkpoint, its input log, or the batch runs of a launcher node.",
    {
      home_dir: schemas.homeDir,
      process: schemas.processName,
      task,
      what: z.enum(["summary", "checkpoint", "log", "runs"]).optional().describe("summary by default."),
      epoch: z.number().int().optional().describe("The epoch of the checkpoint."),
      port: z.string().optional().describe("Only the records of the input log of this port."),
    },
    READS,
    async (backend, { home_dir, process, task: taskIndex, what, epoch, port }) => {
      const program = await programWithOutputDir(backend, home_dir);
      requireResident(program, "Inspecting a node");
      processOf(program, process);
      let command: InspectNodeCommand;
      switch (what ?? "summary") {
        case "checkpoint":
          if (epoch === undefined) {
            throw new Refusal("Give the epoch of the checkpoint.");
          }
          command = { command: "checkpoint", epoch };
          break;
        case "log":
          command = { command: "log", port };
          break;
        case "runs":
          command = { command: "runs" };
          break;
        default:
          command = { command: "summary" };
      }
      const { result, error } = await backend.inspectNode<unknown>(program, process, taskIndex, command);
      if (error) {
        throw new Refusal(error);
      }
      if (command.command === "summary") {
        return summaryRows(result as NodeSummary)
          .map(row => `${row.label}: ${row.value}${row.warning ? " (warning)" : ""}`)
          .join("\n");
      }
      return JSON.stringify(result, null, 2);
    }
  ),

  tool(
    "snapshot",
    "Takes a snapshot of a live resident program: starts a round, which every node checkpoints, and waits for it to close.",
    { home_dir: schemas.homeDir },
    EDITS,
    async (backend, { home_dir }) => {
      const program = await programWithOutputDir(backend, home_dir);
      requireResident(program, "A snapshot");
      const { exitCode, epoch, pendingNodes, output } = await backend.takeSnapshot(program);
      return withOutput(snapshotOutcome(exitCode, epoch, pendingNodes), exitCode === 0 ? "" : output, OUTPUT_LINES);
    }
  ),

  tool(
    "restart_node",
    "Kills a node of a live resident program, as in a crash, and has it relaunched from its last checkpoint. Needs confirm.",
    { home_dir: schemas.homeDir, process: schemas.processName, confirm },
    DELETES,
    async (backend, { home_dir, process, confirm: confirmed }) => {
      const program = await programWithOutputDir(backend, home_dir);
      const node = processOf(program, process);
      if (!offersRestartNode(program, node)) {
        throw new Refusal("Only a node of a resident program, other than the Supervisor, can be restarted.");
      }
      if (!confirmed) {
        const supervised = hasSupervisor(program.processes);
        const bothEnds = restartsWithBothEnds(program.edges, node.id);
        const losesHeldChannel = bothEnds && (!supervised || await backend.launchedWithNoHoldFifos(program));
        throw new Refusal(`${restartNodeWarning(node, supervised, losesHeldChannel).join(" ")} Call again with confirm.`);
      }
      const { output, exitCode, relaunched } = await backend.restartNode(program, process);
      const outcome = hasSupervisor(program.processes)
        ? (exitCode === 0 ? "Restarted: the Supervisor relaunches it." : `It ended with exit code ${exitCode}.`)
        : relaunchOutcome(relaunched, exitCode);
      return withOutput(outcome, output, OUTPUT_LINES);
    }
  ),

  tool(
    "relaunch_node",
    "Relaunches the tasks of a node that are down, in a resident program without a Supervisor.",
    { home_dir: schemas.homeDir, process: schemas.processName },
    EDITS,
    async (backend, { home_dir, process }) => {
      const program = await programWithOutputDir(backend, home_dir);
      processOf(program, process);
      if (!offersRelaunchNode(program)) {
        throw new Refusal("Only a node of a resident program without a Supervisor is relaunched this way.");
      }
      const { output, exitCode, relaunched } = await backend.relaunchNode(program, process);
      return withOutput(relaunchOutcome(relaunched, exitCode), exitCode === 0 ? "" : output, OUTPUT_LINES);
    }
  ),

  tool(
    "list_fifos",
    "The FIFOs of a resident program that write_fifo and read_fifo talk to: its external inputs, and its business outputs with no connection.",
    { home_dir: schemas.homeDir },
    READS,
    async (backend, { home_dir }) => {
      const program = await loadProgram(backend, home_dir);
      requireResident(program, "Talking to FIFOs");
      const { inputs, outputs } = talkCandidates(program);
      const line = (candidate: TalkCandidate) => `  ${candidate.processName} ${candidate.option.label}`;
      return [
        inputs.length > 0 ? "Inputs (write_fifo):" : "Inputs: none",
        ...inputs.map(line),
        outputs.length > 0 ? "Outputs (read_fifo):" : "Outputs: none",
        ...outputs.map(line),
      ].join("\n");
    }
  ),

  tool(
    "write_fifo",
    "Writes one message into an external input of a live resident program, which the backend wraps in a DATA envelope.",
    {
      home_dir: schemas.homeDir,
      process: schemas.processName,
      option: schemas.optionLabel,
      message: z.string().describe("In json mode, any JSON value; in text mode, the text sent as a string."),
      mode: z.enum(["json", "text"]).optional().describe("json by default."),
    },
    EDITS,
    async (backend, { home_dir, process, option, message, mode }) => {
      const program = await programWithOutputDir(backend, home_dir);
      requireResident(program, "Talking to FIFOs");
      const input = talkCandidate(talkCandidates(program).inputs, process, option, "an external input");
      const result = await backend.writeResidentFifo(program, process, input.option.value, message, mode ?? "json");
      if (!result.ok) {
        throw new Refusal(result.error ?? "The message was not written.");
      }
      return `Written to ${process} ${option}.`;
    }
  ),

  tool(
    "read_fifo",
    "Reads the next message from a business output with no connection of a live resident program, which takes it from the channel.",
    { home_dir: schemas.homeDir, process: schemas.processName, option: schemas.optionLabel },
    EDITS,
    async (backend, { home_dir, process, option }) => {
      const program = await programWithOutputDir(backend, home_dir);
      requireResident(program, "Talking to FIFOs");
      const output = talkCandidate(talkCandidates(program).outputs, process, option, "a business output with no connection");
      const read = await backend.readResidentFifo(program, process, output.option.value);
      if (read.error) {
        throw new Refusal(read.error);
      }
      if (read.timedOut) {
        return "Nothing arrived yet: read again.";
      }
      return entryText({ kind: "read", port: `${process} ${option}`, read });
    }
  ),

];

const filePath = z.string().min(1)
  .describe('A path relative to the home directory of the program, such as "test/greet.bats".');

// The entry of the tree of user files at `path`, if any.
function findFileEntry(entries: FileEntry[], path: string): FileEntry | undefined {
  for (const entry of entries) {
    if (entry.path === path) {
      return entry;
    }
    const found = findFileEntry(entry.children ?? [], path);
    if (found) {
      return found;
    }
  }
  return undefined;
}

// The number of files under some entries of the tree, at any depth.
function countFiles(entries: FileEntry[]): number {
  return entries.reduce((count, entry) => count + (entry.type === "dir" ? countFiles(entry.children ?? []) : 1), 0);
}

// The user files of a home directory, one per line, indented by depth, a
// directory with a final slash.
function fileTreeLines(entries: FileEntry[], depth = 0): string[] {
  return entries.flatMap(entry => [
    `${"  ".repeat(depth)}${entry.name}${entry.type === "dir" ? "/" : ""}${entry.readonly ? " (generated script, read-only)" : ""}`,
    ...fileTreeLines(entry.children ?? [], depth + 1),
  ]);
}

const testTools = [

  tool(
    "run_tests",
    "Runs the business tests of the program, the files test/*.bats and test/test_*.py of its home directory, as \"Run tests\" in the Run menu does (debasher_test), after saving the program. Refused while a run is in progress.",
    { home_dir: schemas.homeDir, lines },
    READS,
    async (backend, { home_dir, lines: count }) => {
      const program = await loadProgram(backend, home_dir);
      const { outcome, output } = await savingFirst(() => backend.runTests(program));
      // The message of the editor names its own menu, where an agent has add_test
      const message = outcome === "noTests" ? "The program has no tests: add_test writes a first one." : TEST_OUTCOME_MESSAGES[outcome];
      return withOutput(message, output, count ?? OUTPUT_LINES);
    }
  ),

  tool(
    "add_test",
    "Writes the test skeleton of a process, as \"Add test\" does: test/<process>.bats for a process of a general program, test/test_<process>.py for a node. Fill in its placeholders and its checks, then remove the line that makes it fail. Refused when the file exists.",
    { home_dir: schemas.homeDir, process: schemas.processName },
    EDITS,
    async (backend, { home_dir, process: name }) => {
      const program = await loadProgram(backend, home_dir);
      const process = processOf(program, name);
      if (!offersAddTest(program, process)) {
        throw new Refusal(`${name} is a ${process.nodeKind}: the node harness builds only an FBPProcess.`);
      }
      const path = testFilePath(program, process);
      if ((await backend.getFileContent(home_dir, path)).kind !== "missing") {
        throw new Refusal(`${path} exists: read it with read_program_file.`);
      }
      const content = testSkeleton(program, process);
      await backend.writeFileContent(home_dir, program.name, path, content, true);
      return `Wrote ${path}:\n${content}`;
    }
  ),

];

// The user files of the home directory, as the program files panel manages
// them (see "Reserved names and user files" in doc/design_doc_webui.md).
const userFileTools = [

  tool(
    "list_program_files",
    "Lists the user files of the home directory of the program, such as its tests and the data they read, with the generated script; files that DeBasher manages are not shown.",
    { home_dir: schemas.homeDir },
    READS,
    async (backend, { home_dir }) => {
      const program = await loadProgram(backend, home_dir);
      const entries = await backend.getFileTree(home_dir, program.name);
      return entries.length > 0 ? fileTreeLines(entries).join("\n") : "The home directory has no user files.";
    }
  ),

  tool(
    "read_program_file",
    "Reads a user file of the home directory of the program.",
    { home_dir: schemas.homeDir, path: filePath },
    READS,
    async (backend, { home_dir, path }) => {
      const file = await backend.getFileContent(home_dir, path);
      if (file.kind === "missing") {
        throw new Refusal(`${path} does not exist.`);
      }
      return file.kind === "binary" ? `${path} is a binary file.` : file.content;
    }
  ),

  tool(
    "write_program_file",
    "Creates or replaces a user file of the home directory of the program, with the directories above it, such as a test or the data it reads. The generated script and the files that DeBasher manages are refused.",
    { home_dir: schemas.homeDir, path: filePath, content: z.string().describe("The whole content of the file.") },
    EDITS,
    async (backend, { home_dir, path, content }) => {
      const program = await loadProgram(backend, home_dir);
      await backend.writeFileContent(home_dir, program.name, path, content, true);
      return `Wrote ${path}.`;
    }
  ),

  tool(
    "delete_program_file",
    "Deletes a user file of the home directory of the program, or a directory with everything in it. It cannot be undone, so it needs confirm. The generated script and the files that DeBasher manages are refused.",
    { home_dir: schemas.homeDir, path: filePath, confirm },
    DELETES,
    async (backend, { home_dir, path, confirm: confirmed }) => {
      const program = await loadProgram(backend, home_dir);
      if (!confirmed) {
        const entry = findFileEntry(await backend.getFileTree(home_dir, program.name), path);
        if (!entry) {
          throw new Refusal(`${path} does not exist.`);
        }
        const what = entry.type === "dir"
          ? `the directory ${path} and the ${countFiles(entry.children ?? [])} files in it`
          : path;
        throw new Refusal(`This deletes ${what}, which cannot be undone: call again with confirm.`);
      }
      await backend.deleteEntry(home_dir, program.name, path);
      return `Deleted ${path}.`;
    }
  ),

  tool(
    "move_program_file",
    "Renames or moves a user file or directory of the home directory of the program, creating the directories above the new path. Refused when the new path exists, so nothing is overwritten.",
    { home_dir: schemas.homeDir, path: filePath, new_path: filePath.describe("The new path, relative to the home directory.") },
    EDITS,
    async (backend, { home_dir, path, new_path }) => {
      const program = await loadProgram(backend, home_dir);
      await backend.moveEntry(home_dir, program.name, path, new_path);
      return `Moved ${path} to ${new_path}.`;
    }
  ),

];

export const TOOLS: Tool[] = [
  ...readingTools,
  ...libraryTools,
  ...editingTools,
  ...runningTools,
  ...residentTools,
  ...testTools,
  ...userFileTools,
];
