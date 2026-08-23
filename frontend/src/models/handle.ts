export type HandleDirection = "input" | "output";

export type HandleDataType = "int" | "float" | "string";

export interface WorkflowHandle {
  id: string;
  label: string;
  direction: HandleDirection;
  dataType: HandleDataType;
  description: string;
  value: string;
  fifo: boolean;
}
