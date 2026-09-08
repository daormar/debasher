export type OptionDirection = "input" | "output";

export type OptionDataType = "int" | "float" | "string" | "file" | "None";

// How the value is delivered, independent of its type — see
// api/models.py's ProgramOption.channel for the full rationale
// (value_desc is output-only; fifo and shared_dir aren't
// direction-restricted). A "shared_dir" option's value names one of
// Program.sharedDirs rather than holding a literal value.
export type OptionChannel = "none" | "value_desc" | "fifo" | "shared_dir";

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
  // On a "standard"-mode process only, whether this option's value comes
  // from an attribute of the process's own process spec (via
  // debasher::define_procspec_opt) rather than a literal/connection/
  // channel-delivered value — see api/models.py's
  // ProgramOption.fromProcessSpec for why this is deliberately its own
  // flag rather than folded into `channel`. Mutually exclusive with
  // commandLine. When true, `value` holds the spec attribute's name
  // (e.g. "cpus", one of PROCESS_SPEC_ATTRIBUTE_NAMES) rather than a
  // literal value — the same convention a "shared_dir"-channel option
  // already uses for its own `value` (a directory name, not a path).
  fromProcessSpec: boolean;
  // On a "standard"-mode process only (see isFanoutOption), the id of
  // another option on the SAME process (with commandLine=true) whose
  // value supplies the runtime count for this fanout family — e.g.
  // "-outfith"'s countSourceOptionId points at that process's own "-w".
  countSourceOptionId?: string;
}

// Process-spec attribute names a "from process spec" option can name in
// `value` — restricted to the ones ComputationalSpecs/AdditionalSpecs
// (see models/process.ts) actually model and let a user set elsewhere in
// this editor, out of the full set debasher::define_procspec_opt itself
// accepts (which also includes the engine's nodes/account/partition/
// throttle computational-spec attributes — process.ts has no fields for
// those, so offering them here would let a user reference a value they
// can't set anywhere in the app).
export const PROCESS_SPEC_ATTRIBUTE_NAMES = [
  "cpus",
  "mem",
  "time",
  "processdeps",
  "force",
  "alias",
  "ext_alias",
] as const;

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
