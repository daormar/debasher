export type OptionDirection = "input" | "output";

export type OptionDataType = "int" | "float" | "string";

export interface WorkflowOption {
  id: string;
  label: string;
  direction: OptionDirection;
  dataType: OptionDataType;
  description: string;
  value: string;
  fifo: boolean;
}
