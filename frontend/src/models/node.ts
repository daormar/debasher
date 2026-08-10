import type { Position } from "./position";
import type { WorkflowHandle } from "./handle";

export interface WorkflowNode {

  id: string;

  name: string;

  position: Position;

  handles: WorkflowHandle[];

}
