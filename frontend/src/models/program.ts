import type { ProgramEdge } from "./edge";
import type { ProgramProcess } from "./process";

export interface ExecutionOptions {

  scheduler: string;

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

  processes: ProgramProcess[];

  edges: ProgramEdge[];

}
