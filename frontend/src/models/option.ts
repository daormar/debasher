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

export function getOptionDirection(label: string): OptionDirection {
  return label.startsWith("-out") || label.startsWith("--out")
    ? "output"
    : "input";
}

export function isValidOptionLabel(label: string): boolean {
  return label.trim().startsWith("-");
}
