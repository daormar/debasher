import { RevisionConflict } from "../../src/api/revisionConflict";
import type { Program } from "../../src/models/program";
import { NoProgramMetadata } from "../../src/storage/programStorage";
import type { Backend } from "./backend";

// A backend for the tests of the MCP tools, which needs no server: the
// program metadata of each home directory in memory, saved with the
// revision check of the backend (see persistence.save), and every other
// request answered by `overrides`, or refused as not faked.

export interface FakeBackend extends Backend {
  saved: Map<string, Program>;
  saves: number;
}

function sameContent(a: Program, b: Program): boolean {
  const content = ({ revision: _revision, homeDir: _homeDir, ...rest }: Program) => rest;
  return JSON.stringify(content(a)) === JSON.stringify(content(b));
}

export function fakeBackend(programs: Program[] = [], overrides: Partial<Backend> = {}): FakeBackend {

  const saved = new Map(programs.map(program => [program.homeDir, structuredClone(program)]));

  const fake = {
    saved,
    saves: 0,

    async loadProgram(homeDir: string) {
      const program = saved.get(homeDir);
      if (!program) {
        throw new NoProgramMetadata(`Failed to load program: no program in ${homeDir}`);
      }
      return structuredClone(program);
    },

    async saveProgram(program: Program, homeDir: string) {
      const current = saved.get(homeDir);
      const ownHome = program.homeDir === homeDir;
      if (current && ownHome && (current.revision ?? 0) !== (program.revision ?? 0) && !sameContent(current, program)) {
        throw new RevisionConflict(
          `The program in ${homeDir} was saved elsewhere since it was loaded (revision ${current.revision}).`,
          current.revision ?? 0
        );
      }
      const unchanged = current !== undefined && ownHome && sameContent(current, program);
      const revision = unchanged ? current.revision ?? 0 : (ownHome ? current?.revision ?? 0 : 0) + 1;
      saved.set(homeDir, structuredClone({ ...program, homeDir, revision }));
      fake.saves += 1;
      return { revision };
    },

    async validateProcessName(name: string) {
      return /^[A-Za-z_][A-Za-z0-9_.]*$/.test(name);
    },

    async suggestProcessNames() {
      return [];
    },

    async suggestNodes() {
      return [];
    },

    ...overrides,
  };

  return new Proxy(fake, {
    get(target, property, receiver) {
      if (property in target || typeof property === "symbol") {
        return Reflect.get(target, property, receiver);
      }
      return async () => {
        throw new Error(`The fake backend does not answer ${String(property)}.`);
      };
    },
  }) as unknown as FakeBackend;

}
