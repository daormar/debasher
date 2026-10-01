import { z } from "zod";

// The parameters of the MCP tools. The fields of processes, options and
// settings follow the program model (src/models/), whose names they keep, so
// that an edit given to an MCP tool is a named edit as it is (see
// models/programRefs.ts).

export const homeDir = z.string().min(1)
  .describe("The home directory of the program: the directory where its program metadata is saved.");

export const processName = z.string().min(1).describe("The name of a process of the program.");

export const optionLabel = z.string().min(1).describe('The label of an option of the process, such as "-outf".');

export const optionRef = z.object({ process: processName, option: optionLabel }).strict();

export const position = z.object({ x: z.number(), y: z.number() }).strict()
  .describe("A position on the canvas, in pixels; y grows downwards.");

const language = z.enum(["bash", "python", "perl", "r", "groovy"]);

export const nodeKind = z.enum(["FBPProcess", "ProgramLauncher", "DirectoryWatcher", "Supervisor"]);

export const optionFields = z.object({
  dataType: z.enum(["int", "float", "string", "file", "None"]).optional()
    .describe('"None" for a flag, which takes no value.'),
  channel: z.enum(["none", "value_desc", "fifo", "shared_dir"]).optional()
    .describe("How the value is delivered: a plain value, an output whose value is a description, a FIFO, or a shared directory."),
  mirror: z.boolean().optional().describe("On a FIFO output: keep a copy of what goes through it."),
  fifoTag: z.literal("external").optional()
    .describe("In a resident program, on a FIFO input: an external input, written from outside the program."),
  description: z.string().optional(),
  value: z.string().optional()
    .describe("A Bash word; a connected input takes its value from its connection."),
  commandLine: z.boolean().optional().describe("The value comes from the command line of the program."),
  mandatory: z.boolean().optional(),
  fromProcessSpec: z.boolean().optional()
    .describe("The value comes from an attribute of the process specifications, which `value` names."),
  countSource: z.string().optional()
    .describe('On a fanout family such as "-outfith": the label of the option of the same process whose value gives its count.'),
}).strict();

export const newOption = optionFields.extend({ label: optionLabel }).strict();

export const optionChanges = optionFields.extend({
  label: optionLabel.optional().describe("A new label; its direction follows from it (output when it starts with -out)."),
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
  }).strict().optional(),
  computationalSpecs: computationalSpecs.optional(),
  additionalSpecs: z.object({
    force: z.boolean().optional(),
    processdeps: z.string().optional(),
    alias: z.string().optional(),
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
}).strict().describe("Of a field that holds an object, give only the fields that change.");

export const seqProcessChanges = z.object({
  description: z.string().optional(),
  language: language.optional(),
  code: z.string().optional(),
  computationalSpecs: z.object({
    cpus: z.number().optional(),
    mem: z.number().optional(),
    time: z.string().optional(),
  }).strict().optional(),
  additionalSpecs: z.object({
    alias: z.string().optional(),
    aliasOptMap: aliasOptMap.optional(),
    externalAlias: z.string().optional(),
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
  changes: processChanges.optional(),
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
  z.object({ op: z.literal("connect"), from: optionRef, to: optionRef }).strict(),
  z.object({ op: z.literal("disconnect"), from: optionRef, to: optionRef }).strict(),
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
