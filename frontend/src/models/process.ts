import type { Position } from "./position";
import type { OptionDataType, ProgramOption } from "./option";

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

export const DEFAULT_COMPUTATIONAL_SPECS: Required<ComputationalSpecs> = {
  cpus: 1,
  mem: 256,
  time: "01:00:00",
};

export interface AdditionalSpecs {

  force: boolean;

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

  generatorSizeCode?: string;

  arrayCode?: string;

  manualCode?: string;

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
