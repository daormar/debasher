import type { Position } from "./position";
import type { WorkflowHandle } from "./handle";

export type NodeLanguage =
  | "bash"
  | "python"
  | "perl"
  | "r"
  | "groovy";

export interface WorkflowNode {

  id: string;

  name: string;

  position: Position;

  handles: WorkflowHandle[];

  language: NodeLanguage;

  code: string;

}
