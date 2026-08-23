import type { Position } from "./position";
import type { WorkflowOption } from "./option";

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

export interface WorkflowProcess {

  id: string;

  name: string;

  position: Position;

  options: WorkflowOption[];

  language: ProcessLanguage;

  code: string;

  computationalSpecs: ComputationalSpecs;

  additionalSpecs: AdditionalSpecs;

}
