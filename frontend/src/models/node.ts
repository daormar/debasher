import type { Position } from "./position";
import type { WorkflowOption } from "./option";

export type NodeLanguage =
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

export interface WorkflowNode {

  id: string;

  name: string;

  position: Position;

  options: WorkflowOption[];

  language: NodeLanguage;

  code: string;

  computationalSpecs: ComputationalSpecs;

  additionalSpecs: AdditionalSpecs;

}
