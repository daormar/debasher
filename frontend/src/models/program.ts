import type { ProgramEdge } from "./edge";
import type { ProgramProcess } from "./process";

export interface ExecutionOptions {

  scheduler: string;

  // All fields below are optional debasher_exec flags: an empty/falsy
  // value means "not given", so debasher_exec falls back to its own
  // default (see ExecutionOptionsEditor and execution.py's
  // _prepare_debasher_exec_command).

  // --builtinsched-cpus <int> (BUILTIN scheduler only).
  builtinSchedCpus?: string;

  // --builtinsched-mem <int> (BUILTIN scheduler only). Despite the
  // "<int>" in debasher_exec's own --help, it accepts a plain number
  // (MB) or one with a K/M/G/T suffix (see
  // debasher::_convert_mem_value_to_mb) — free-form text, not an
  // integer input.
  builtinSchedMem?: string;

  // --dflt-nodes <string> (SLURM scheduler only): a node list passed
  // straight through to sbatch's -w, e.g. "node01,node02" or
  // "node[01-04]" — not an index/count despite living next to the
  // (actually numeric) cpus/mem options above.
  dfltNodes?: string;

  // --dflt-throttle <string>: max concurrent tasks for a job array,
  // applied by both schedulers (see
  // debasher::_get_scheduler_throttle). Empty means unthrottled.
  dfltThrottle?: string;

  // --rerun-outdated-procs
  rerunOutdatedProcs?: boolean;

  // --conda-support
  condaSupport?: boolean;

  // --docker-support
  dockerSupport?: boolean;

}

export interface Program {

  id: string;

  name: string;

  description: string;

  preamble: string;

  envVars: Record<string, string>;

  // Directory the program's own definition (program.json) and .sh
  // script are saved to (via the toolbar's "Save" button) — distinct
  // from outputDir, which is where a run's results are written.
  homeDir: string;

  outputDir: string;

  // Absolute directory of the .sh this program was imported from (empty
  // for a program that wasn't imported). A process's AdditionalSpecs.
  // externalAlias, when relative, is resolved against this directory so
  // the backend can copy that file alongside a later save.
  sourceDir: string;

  executionOptions: ExecutionOptions;

  programOptions: Record<string, string>;

  // Names of the module-level shared directories declared for this
  // program, each becoming one debasher::define_shared_dir call in the
  // generated <name>_shared_dirs function (see script_generation.py's
  // _add_shared_dirs_func).
  sharedDirs: string[];

  // Every shared directory name reachable from this program — its own
  // sharedDirs plus every one declared by a module it loads,
  // transitively (see api/doc_mod.py's run_doc_mod_all_shared_dirs).
  // Populated only by import (api/program_import.py); purely additive,
  // never written back by script generation, and never a substitute for
  // sharedDirs, which is what codegen actually emits from.
  availableSharedDirs: string[];

  processes: ProgramProcess[];

  edges: ProgramEdge[];

}
