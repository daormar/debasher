import type { Position } from "./position";
import type { OptionDataType, ProgramOption } from "./option";
import { createOption } from "./option";
import type { NodeCode, NodeInfo, NodeKind } from "./node";
import { emptyNodeCode } from "./node";

export type ProcessLanguage =
  | "bash"
  | "python"
  | "perl"
  | "r"
  | "groovy";

export interface ComputationalSpecs {

  cpus?: number;

  mem?: number;

  time?: string;

  // Only for the node kinds of a resident program that read them (see
  // RESIDENT_SPEC_FIELDS in models/node.ts), each named as the engine's
  // computational specification it becomes; unset leaves the default of
  // the class.

  input_log_max_mb?: number;

  out_backlog_max_mb?: number;

  out_backlog_fail_mb?: number;

  gil_switch_interval_ms?: number;

  startup_timeout_s?: number;

  max_concurrent_runs?: number;

  batch_sched?: string;

  heartbeat_timeout_s?: number;

}

export const DEFAULT_COMPUTATIONAL_SPECS: Required<Pick<ComputationalSpecs, "cpus" | "mem" | "time">> = {
  cpus: 1,
  mem: 256,
  time: "01:00:00",
};

export interface AliasOptMapping {

  fromLabel: string;

  toLabel: string;

}

export interface AdditionalSpecs {

  force: boolean;

  processdeps?: string;

  alias?: string;

  // Only meaningful alongside `alias` — renames this process's own
  // option labels (fromLabel) into the ones the aliased process's
  // implementation expects (toLabel) before delegating, via the
  // engine's "alias_opt_map" process spec attribute. Lets an alias
  // process keep its own option names even when they differ from the
  // aliased implementation's.
  aliasOptMap?: AliasOptMapping[];

  externalAlias?: string;

}

export type OptionsHandlerMode =
  | "standard"
  | "array"
  | "generator"
  | "manual";

export interface OptionsHandler {

  mode: OptionsHandlerMode;

  generatorSizeCode?: string;

  arrayCode?: string;

  manualCode?: string;

}

/**
 * Bodies (not full function definitions, unlike ProgramProcess.code) for
 * the DEBASHER_PROCESS_METHODS (engine/debasher_lib.sh) not covered
 * elsewhere in the Inspector — "document" has its own Description field,
 * "exec" is ProgramProcess.code, and the option explanation/definition
 * methods are driven by ProgramProcess.options / optionsHandler.
 */
export interface AdditionalMethods {

  resetOutfilesCode?: string;

  postCode?: string;

  outdirBasenameCode?: string;

  skipCode?: string;

  condaEnvsCode?: string;

  dockerImgsCode?: string;

}

/**
 * Marks a process as having been brought in as part of a batch via
 * "Add program" (see ProgramContext's mergeProgram), rather than
 * authored directly in this canvas. `groupId` ties together every
 * process merged in the same operation; `groupSize` is how many there
 * were, so script_generation.py can tell an intact group (still all
 * present, none detached) from a partial one. Cleared from every
 * process sharing the same groupId the moment any one of them has its
 * own content edited or is deleted (see ProgramContext's
 * confirmDetachIfGrouped) — add_debasher_program can't express "this
 * module except one process" or "with this process's code overridden",
 * so once that happens the whole group falls back to being generated
 * as ordinary add_debasher_process calls.
 */
export interface GroupSource {

  programName: string;

  groupId: string;

  groupSize: number;

  sourceDir: string;

}

export interface ProgramProcess {

  id: string;

  name: string;

  description: string;

  position: Position;

  options: ProgramOption[];

  optionsHandler: OptionsHandler;

  language: ProcessLanguage;

  code: string;

  computationalSpecs: ComputationalSpecs;

  additionalSpecs: AdditionalSpecs;

  additionalMethods: AdditionalMethods;

  groupSource?: GroupSource;

  // Only in a resident program: the node kind of the process, chosen when
  // it is added; whether it is an initiator, where a round starts; and the
  // parts of its code, which a Supervisor does not have (script generation
  // writes its whole class). See models/node.ts.
  nodeKind?: NodeKind;

  initiator?: boolean;

  nodeCode?: NodeCode;

}

/**
 * A previously-defined process's description, options, and code, as
 * fetched from the program's preamble (via debasher_get_proc_info) when
 * a suggested (already-existing) process name is selected.
 */
export interface ProcessInfoOption {

  label: string;

  dataType: OptionDataType;

  description: string;

  commandLine: boolean;

  mandatory: boolean;

}

export interface ProcessInfo {

  description: string;

  options: ProcessInfoOption[];

  language: ProcessLanguage;

  code: string;

}

// A new option from what the library brings for it.
export function optionFromInfo(info: ProcessInfoOption, id: string): ProgramOption {
  return createOption(id, info.label, {
    dataType: info.dataType,
    description: info.description,
    commandLine: info.commandLine,
    mandatory: info.mandatory,
  });
}

// Where a new process comes from: what the library brings for its name, or,
// in a resident program, the node kind chosen for it and, for a node that a
// module of the preamble defines, what that module brings.
export interface NewProcessSource {

  info?: ProcessInfo | null;

  nodeKind?: NodeKind;

  nodeInfo?: NodeInfo;

}

/**
 * A new process, with the ids of its options from `newId`. A node is written
 * in Python, in the parts of NodeCode, and a Supervisor has no code of its
 * own.
 */
export function createProcess(
  id: string,
  name: string,
  { info, nodeKind, nodeInfo }: NewProcessSource,
  newId: () => string
): ProgramProcess {

  const nodeFields: Partial<ProgramProcess> = nodeInfo
    ? {
        nodeKind: nodeInfo.nodeKind,
        initiator: false,
        nodeCode: nodeInfo.nodeCode,
        language: "python",
        description: nodeInfo.description,
        options: nodeInfo.options,
        optionsHandler: nodeInfo.optionsHandler,
      }
    : nodeKind
      ? {
          nodeKind,
          initiator: false,
          nodeCode: nodeKind === "Supervisor" ? undefined : emptyNodeCode(),
          language: "python",
        }
      : {};

  return {
    id,
    name,
    description: info?.description ?? "",
    position: { x: 100, y: 100 },
    options: info ? info.options.map(option => optionFromInfo(option, newId())) : [],
    optionsHandler: { mode: "standard" },
    language: info?.language ?? "bash",
    code: info?.code ?? "",
    computationalSpecs: { ...DEFAULT_COMPUTATIONAL_SPECS },
    additionalSpecs: { force: false },
    additionalMethods: {},
    ...nodeFields,
  };

}
