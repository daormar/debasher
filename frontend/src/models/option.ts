export type OptionDirection = "input" | "output";

export type OptionDataType = "int" | "float" | "string" | "file" | "None";

// How the value is delivered, independent of its type — see
// api/models.py's ProgramOption.channel for the full rationale
// (value_desc is output-only, fifo isn't direction-restricted).
export type OptionChannel = "none" | "value_desc" | "fifo";

export interface ProgramOption {
  id: string;
  label: string;
  direction: OptionDirection;
  dataType: OptionDataType;
  channel: OptionChannel;
  description: string;
  value: string;
  commandLine: boolean;
  mandatory: boolean;
}

export function getOptionDirection(label: string): OptionDirection {
  return label.startsWith("-out") || label.startsWith("--out")
    ? "output"
    : "input";
}

export function isValidOptionLabel(label: string): boolean {
  return label.trim().startsWith("-");
}

/**
 * Command line options declared across all of a program's processes,
 * deduplicated by label (the same option can be declared on more than
 * one process).
 */
export function getCommandLineOptions(
  processes: { options: ProgramOption[] }[]
): ProgramOption[] {

  const byLabel = new Map<string, ProgramOption>();

  for (const process of processes) {
    for (const option of process.options) {
      if (option.commandLine && !byLabel.has(option.label)) {
        byLabel.set(option.label, option);
      }
    }
  }

  return [...byLabel.values()];

}
