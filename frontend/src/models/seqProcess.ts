import type { AliasOptMapping, GroupSource, ProcessLanguage } from "./process";

// The computational specifications that a sequential process may have,
// each optional: under Slurm they become options of srun when a task runs
// it as a step, and the built-in scheduler uses none of them.
export interface SeqComputationalSpecs {

  cpus?: number;

  mem?: number;

  time?: string;

}

// The additional specifications that the engine accepts on a sequential
// process: "processdeps" and "force" belong to a scheduled process only.
export interface SeqAdditionalSpecs {

  alias?: string;

  aliasOptMap?: AliasOptMapping[];

  externalAlias?: string;

}

/**
 * A sequential process of the program (add_debasher_seq_process): code that
 * a process runs as a step with seq_execute, kept beside the processes since
 * any of them may run it. It has no options, options handler, additional
 * methods or position, and it is not drawn on the canvas (see "Sequential
 * processes in the web UI" in doc/design_doc_webui.md). A resident program
 * has none.
 */
export interface SeqProcess {

  id: string;

  name: string;

  description: string;

  language: ProcessLanguage;

  code: string;

  computationalSpecs: SeqComputationalSpecs;

  additionalSpecs: SeqAdditionalSpecs;

  groupSource?: GroupSource;

}

// The code a new sequential process starts with: a Bash function of its
// name that does nothing, or no code in another language.
export function defaultSeqCode(name: string, language: ProcessLanguage): string {
  return language === "bash" ? `${name}()\n{\n    :\n}` : "";
}

export function createSeqProcess(name: string): SeqProcess {
  return {
    id: crypto.randomUUID(),
    name,
    description: "",
    language: "bash",
    code: defaultSeqCode(name, "bash"),
    computationalSpecs: {},
    additionalSpecs: {},
  };
}

/**
 * The changes that renaming a sequential process, or changing its language,
 * makes: code still as it started follows the new name and language, since a
 * Bash function named after the old name would not implement it.
 */
export function withSeqProcessChanges(seqProcess: SeqProcess, changes: Partial<SeqProcess>): SeqProcess {
  const changed = { ...seqProcess, ...changes };
  const untouched = seqProcess.code === defaultSeqCode(seqProcess.name, seqProcess.language);
  if (untouched && changes.code === undefined && (changes.name !== undefined || changes.language !== undefined)) {
    changed.code = defaultSeqCode(changed.name, changed.language);
  }
  return changed;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Whether Bash code defines a function with the given name, as the engine
// needs for a sequential process without an alias.
export function definesBashFunction(code: string, name: string): boolean {
  const escaped = escapeRegExp(name);
  return new RegExp(
    `^\\s*(function\\s+${escaped}(\\s*\\(\\s*\\)|\\s|$)|${escaped}\\s*\\(\\s*\\))`,
    "m"
  ).test(code);
}

/**
 * What makes the sequential processes of a program wrong before the engine
 * sees them, or null: a blank name, a name shared by two of them or by a
 * process (the engine refuses both), an alias together with an external
 * alias, and Bash code that defines no function of the name. Whether a name follows the rules of a process name is checked by
 * the backend, as for a process.
 */
export function seqProcessesProblem(
  seqProcesses: SeqProcess[],
  processNames: string[]
): string | null {

  const taken = new Set(processNames.map(name => name.toLowerCase()));
  const seen = new Set<string>();

  for (const seqProcess of seqProcesses) {
    const name = seqProcess.name.trim();
    if (!name) {
      return "A sequential process has no name.";
    }
    const key = name.toLowerCase();
    if (taken.has(key)) {
      return `"${name}" is the name of a process: a process and a sequential process cannot share a name.`;
    }
    if (seen.has(key)) {
      return `Two sequential processes are named "${name}".`;
    }
    seen.add(key);
    const hasAlias = seqProcess.additionalSpecs.alias || seqProcess.additionalSpecs.externalAlias;
    if (seqProcess.additionalSpecs.alias && seqProcess.additionalSpecs.externalAlias) {
      return `"${name}" has both an alias and an external alias: give only one.`;
    }
    if (!hasAlias && seqProcess.language === "bash" && !definesBashFunction(seqProcess.code, name)) {
      return `The Bash code of "${name}" does not define a function "${name}", which the step runs.`;
    }
  }

  return null;

}

// "OLD:NEW,OLD:NEW" as the engine writes alias_opt_map, from and to the
// list of the model.
export function aliasOptMapToText(mappings: AliasOptMapping[] | undefined): string {
  return (mappings ?? []).map(mapping => `${mapping.fromLabel}:${mapping.toLabel}`).join(",");
}

export function aliasOptMapFromText(text: string): AliasOptMapping[] {
  return text
    .split(",")
    .map(pair => pair.trim())
    .filter(pair => pair !== "")
    .map(pair => {
      const [fromLabel, ...rest] = pair.split(":");
      return { fromLabel: fromLabel.trim(), toLabel: rest.join(":").trim() };
    });
}
