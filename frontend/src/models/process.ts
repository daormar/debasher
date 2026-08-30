import type { Position } from "./position";
import type { OptionDataType, WorkflowOption } from "./option";

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

}

export interface AdditionalSpecs {

  forced: boolean;

  processdeps?: string;

  alias?: string;

  externalAlias?: string;

}

export type OptionsHandlerMode =
  | "standard"
  | "array"
  | "generator"
  | "manual";

export interface OptionsHandler {

  mode: OptionsHandlerMode;

  generatorSize?: string;

  arrayCode?: string;

  manualCode?: string;

}

export interface WorkflowProcess {

  id: string;

  name: string;

  description: string;

  position: Position;

  options: WorkflowOption[];

  optionsHandler: OptionsHandler;

  language: ProcessLanguage;

  code: string;

  computationalSpecs: ComputationalSpecs;

  additionalSpecs: AdditionalSpecs;

}

/**
 * A previously-defined process's description, options, and code, as
 * fetched from the workflow's preamble (via debasher_get_proc_info) when
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
