import { z } from "zod";

// The parameters of the MCP tools. The fields of processes, options and
// settings follow the program model (src/models/), whose names they keep, so
// that an edit given to an MCP tool is a named edit as it is (see
// models/programRefs.ts).

export const homeDir = z.string().min(1)
  .describe("The home directory of the program: the directory where it is saved (its topology file program.yaml and the files of its processes).");

export const processName = z.string().min(1).describe("The name of a process of the program.");

export const optionLabel = z.string().min(1).describe('The label of an option of the process, such as "-outf".');

export const optionRef = z.object({ process: processName, option: optionLabel }).strict();

export const connectionDisplay = z.enum(["line", "label"])
  .describe(
    "How the canvas draws the connection: a line, or a label edge, a short stub at each end naming the " +
    "other, for a connection whose line would cross others. It changes nothing in the program that runs."
  );

export const position = z.object({ x: z.number(), y: z.number() }).strict()
  .describe("A position on the canvas, in pixels; y grows downwards.");

const language = z.enum(["bash", "python", "perl", "r", "groovy"]);

// The language of a tasks file or of a skip file: a Bash body, or a Python
// function file that the engine runs.
const funcLanguage = z.enum(["bash", "python"]);

export const nodeKind = z.enum(["FBPProcess", "ProgramLauncher", "DirectoryWatcher", "Supervisor"]);

export const optionFields = z.object({
  dataType: z.enum(["int", "float", "string", "file", "dir", "None"]).optional()
    .describe('The type of the data that the option carries, the channel being how it gets there: with channel "none", the value itself ("file" or "dir" for an input path that has to exist, a regular file or a directory); through a FIFO, each line of it; through a value descriptor, the value it holds. A directory channel fixes it to "dir", and a connected input has that of the output it reads, which it follows. "None" for a flag, which takes no value and no channel.'),
  channel: z.enum(["none", "value_desc", "fifo", "shared_dir", "process_outdir"]).optional()
    .describe("How the value is delivered: a plain value, an output whose value is a description, a FIFO, a shared directory, or, for an output, the output directory of the process."),
  subpath: z.string().optional()
    .describe('With channel "shared_dir" or "process_outdir": a directory of the task\'s own below that directory, a Bash word such as "${task_idx}", which the engine creates (and, for the output directory of the process, empties before each task). Empty for the directory itself.'),
  mirror: z.boolean().optional().describe("On a FIFO output: keep a copy of what goes through it."),
  fifoTag: z.literal("external").optional()
    .describe("In a resident program, on a FIFO input: an external input, written from outside the program."),
  description: z.string().optional(),
  value: z.string().optional()
    .describe("A Bash word; a connected input takes its value from its connection."),
  commandLine: z.boolean().optional().describe("The value comes from the command line of the program."),
  mandatory: z.boolean().optional(),
  taskShaping: z.boolean().optional()
    .describe("A task shaping option: only the options handler reads it, to decide the tasks of the process, and no task receives it. It must be a mandatory command line option with a value, and cannot be the count source of a fanout family."),
  fromProcessSpec: z.boolean().optional()
    .describe("The value comes from an attribute of the process specifications, which `value` names."),
  countSource: z.string().optional()
    .describe('On a fanout family such as "-outf-ith": the label of the command line option of the same process whose value gives its count, or "" for none. Without one, the family counts the tasks of the process at the other end of its connections (the one that an input family reads, the only one that reads an output family), which must be in array or generator mode; a generator is cheaper to count, since the engine counts an array not defined yet by running its whole option definition again.'),
}).strict();

export const newOption = optionFields.extend({ label: optionLabel }).strict();

export const optionChanges = optionFields.extend({
  label: optionLabel.optional().describe("A new label; its direction follows from it (output when it starts with -out), and an option whose direction changes loses its connections."),
}).strict();

const computationalSpecs = z.object({
  cpus: z.number().optional(),
  mem: z.number().optional(),
  time: z.string().optional(),
  input_log_max_mb: z.number().optional(),
  out_backlog_max_mb: z.number().optional(),
  out_backlog_fail_mb: z.number().optional(),
  gil_switch_interval_ms: z.number().optional(),
  startup_timeout_s: z.number().optional(),
  max_concurrent_runs: z.number().optional(),
  batch_sched: z.string().optional(),
  heartbeat_timeout_s: z.number().optional(),
}).strict();

const aliasOptMap = z.array(z.object({ fromLabel: z.string(), toLabel: z.string() }).strict());

export const processChanges = z.object({
  name: z.string().optional(),
  description: z.string().optional(),
  language: language.optional(),
  code: z.string().optional().describe("The whole function of the process, for a process that is not a node."),
  optionsHandler: z.object({
    mode: z.enum(["standard", "array", "generator", "manual"]).optional(),
    generatorSizeCode: z.string().optional(),
    arrayCode: z.string().optional(),
    manualCode: z.string().optional(),
    language: funcLanguage.optional().describe("The language of arrayCode and generatorSizeCode: python makes them a tasks file that defines tasks(run). A manual handler is bash. Give the code in the new language (the whole Python file, or a Bash body) in the same change."),
  }).strict().optional(),
  computationalSpecs: computationalSpecs.optional().describe("cpus, mem in MB and time (HH:MM:SS); each one a process leaves unset is 1, 256 and 01:00:00 respectively. The other fields are limits of a node; unset, a limit keeps the default of the class."),
  additionalSpecs: z.object({
    force: z.boolean().optional(),
    processdeps: z.string().optional(),
    alias: z.string().optional().describe("The process whose code this one runs: a Bash process, or one in another language or another alias that comes before this one (every process comes before the sequential processes)."),
    aliasOptMap: aliasOptMap.optional(),
    externalAlias: z.string().optional(),
  }).strict().optional(),
  additionalMethods: z.object({
    resetOutfilesCode: z.string().optional(),
    postCode: z.string().optional(),
    outdirBasenameCode: z.string().optional(),
    skipCode: z.string().optional(),
    condaEnvsCode: z.string().optional(),
    dockerImgsCode: z.string().optional(),
    skipLanguage: funcLanguage.optional().describe("The language of skipCode: python makes it a skip file that defines skip(task). Give the code in the new language (the whole Python file, or a Bash body) in the same change."),
    condaEnvs: z.array(z.object({ name: z.string().min(1), file: z.string().min(1) }).strict()).optional()
      .describe("The Conda environments as data, a name and a YAML file each (looked for in the directories of DEBASHER_YML_DIR, then among those that DeBasher installs), instead of condaEnvsCode, which has to be empty: give it as an empty string in the same change when the process has one. [] removes them, for a body to be given."),
    dockerImgs: z.array(z.string().min(1)).optional()
      .describe("The Docker images as data instead of dockerImgsCode, which has to be empty: give it as an empty string in the same change when the process has one. [] removes them, for a body to be given."),
  }).strict().optional(),
  initiator: z.boolean().optional().describe("In a resident program: the node where a round starts."),
  nodeCode: z.object({
    preamble: z.string().optional(),
    classBody: z.string().optional(),
    processData: z.string().optional(),
    captureNodeState: z.string().optional(),
    restoreNodeState: z.string().optional(),
    initializeRuntime: z.string().optional(),
    observe: z.string().optional(),
  }).strict().optional().describe("In a resident program: the parts of the code of the node, each a body without its def line."),
}).strict().describe(
  "Of a field that holds an object, give only the fields that change. The code of a tasks file or a skip file in Python is the whole file, which defines tasks(run) or skip(task). In a program described in Python, the Conda environments and Docker images given as data and the language of a tasks file or skip file belong to its description (then debasher_build <name>.py)."
);

export const seqProcessChanges = z.object({
  description: z.string().optional(),
  language: language.optional(),
  code: z.string().optional(),
  computationalSpecs: z.object({
    cpus: z.number().optional(),
    mem: z.number().optional(),
    time: z.string().optional(),
  }).strict().optional()
    .describe('Options of srun for its steps, used only when a step goes to Slurm (sched "SLURM", or a call of seq_execute_slurm); ignored in the shell of the task.'),
  additionalSpecs: z.object({
    alias: z.string().optional().describe("The process whose code this one runs: a Bash process, or one in another language or another alias that comes before this one (every process comes before the sequential processes)."),
    aliasOptMap: aliasOptMap.optional(),
    externalAlias: z.string().optional(),
    sched: z.enum(["BUILTIN", "SLURM"]).nullable().optional()
      .describe('Where seq_execute runs its steps: in the shell of the task when not set, whatever the scheduler of the run; "SLURM" sends them through srun with its computationalSpecs, and the run then needs srun. seq_execute_slurm sends a step to Slurm whatever its sched, and refuses one whose sched is "BUILTIN". Leave it unset unless a step has to go to Slurm or must never go there; null unsets it.'),
  }).strict().optional(),
}).strict();

export const executionOptions = z.object({
  scheduler: z.string().optional().describe('"BUILTIN" or "SLURM".'),
  builtinSchedCpus: z.string().optional(),
  builtinSchedMem: z.string().optional(),
  dfltNodes: z.string().optional(),
  dfltThrottle: z.string().optional(),
  rerunOutdatedProcs: z.boolean().optional(),
  condaSupport: z.boolean().optional(),
  dockerSupport: z.boolean().optional(),
  snapshotEverySecs: z.string().optional(),
}).strict();

export const programFields = z.object({
  name: z.string().optional(),
  description: z.string().optional(),
  preamble: z.string().optional().describe("Bash code run before the program, which loads the modules it uses."),
  sharedDirs: z.array(z.string()).optional(),
  outputDir: z.string().optional().describe("The directory where a run writes its results."),
  executionOptions: executionOptions.optional(),
  programOptions: z.record(z.string(), z.string()).optional()
    .describe("The values of the command line options of the program, by label; replaces all of them."),
}).strict();

export const addProcessFields = {
  name: z.string().min(1),
  nodeKind: nodeKind.optional()
    .describe("In a resident program: the node kind of a node that no module of the preamble defines."),
  changes: processChanges.optional()
    .describe("The fields of the process (description, language, code, ...), as update_process takes them."),
  options: z.array(newOption).optional(),
  position: position.optional().describe("Where on the canvas; by default, to the right of every process."),
};

// A named edit, as apply_edits takes it.
export const namedEdit = z.discriminatedUnion("op", [
  z.object({ op: z.literal("setProgramFields"), changes: programFields }).strict(),
  z.object({ op: z.literal("setEnvVar"), name: z.string().min(1), value: z.string() }).strict(),
  z.object({ op: z.literal("addProcess"), ...addProcessFields }).strict(),
  z.object({ op: z.literal("removeProcess"), process: processName }).strict(),
  z.object({ op: z.literal("moveProcess"), process: processName, position }).strict(),
  z.object({ op: z.literal("updateProcess"), process: processName, changes: processChanges }).strict(),
  z.object({ op: z.literal("addOption"), process: processName, label: optionLabel, fields: optionFields.optional() }).strict(),
  z.object({ op: z.literal("updateOption"), process: processName, option: optionLabel, changes: optionChanges }).strict(),
  z.object({ op: z.literal("removeOption"), process: processName, option: optionLabel }).strict(),
  z.object({ op: z.literal("connect"), from: optionRef, to: optionRef, display: connectionDisplay.optional() }).strict(),
  z.object({ op: z.literal("disconnect"), from: optionRef, to: optionRef }).strict(),
  z.object({ op: z.literal("setConnectionDisplay"), from: optionRef, to: optionRef, display: connectionDisplay }).strict(),
  z.object({ op: z.literal("addSeqProcess"), name: z.string().min(1), changes: seqProcessChanges.optional() }).strict(),
  z.object({
    op: z.literal("updateSeqProcess"),
    name: z.string().min(1),
    changes: seqProcessChanges.extend({ name: z.string().optional() }).strict(),
  }).strict(),
  z.object({ op: z.literal("removeSeqProcess"), name: z.string().min(1) }).strict(),
]);

export const editFlags = {
  dry_run: z.boolean().optional()
    .describe("Answer with a proposal of what the edits would change, and save nothing."),
  detach_groups: z.boolean().optional()
    .describe('Dissolve the groups of processes added with "Add program" that the edits change, rather than refuse them.'),
};
