export type HandleDirection = "input" | "output";

export interface WorkflowHandle {
  id: string;
  label: string;
  direction: HandleDirection;
}
