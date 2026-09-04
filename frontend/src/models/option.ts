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
  // On a "standard"-mode process only (see isFanoutOption), the id of
  // another option on the SAME process (with commandLine=true) whose
  // value supplies the runtime count for this fanout family — e.g.
  // "-outfith"'s countSourceOptionId points at that process's own "-w".
  countSourceOptionId?: string;
}

export function getOptionDirection(label: string): OptionDirection {
  return label.startsWith("-out") || label.startsWith("--out")
    ? "output"
    : "input";
}

export function isValidOptionLabel(label: string): boolean {
  return label.trim().startsWith("-");
}

// debasher's own convention (see data/programs/debasher_dynamic_fanout.sh)
// for a dynamic-count family of options: a label ending in "ith" (e.g.
// "-outfith" standing for "-outf0", "-outf1", ...). Only meaningful on a
// "standard"-mode process — callers must check optionsHandler.mode
// themselves, since the same label on array/generator/manual is just an
// ordinary option.
const FANOUT_SUFFIX = "ith";

export function fanoutBaseLabel(label: string): string {
  return label.slice(0, -FANOUT_SUFFIX.length);
}

export function isFanoutOption(label: string): boolean {
  if (!label.endsWith(FANOUT_SUFFIX)) {
    return false;
  }
  // Excludes the degenerate bare "-ith"/"--ith".
  return fanoutBaseLabel(label).replace(/^-+/, "").length > 0;
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
