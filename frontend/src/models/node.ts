import type { Position } from "./position";
import type { WorkflowHandle } from "./handle";

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

}

export interface WorkflowNode {

  id: string;

  name: string;

  position: Position;

  handles: WorkflowHandle[];

  language: NodeLanguage;

  code: string;

  computationalSpecs: ComputationalSpecs;

  additionalSpecs: AdditionalSpecs;

}
