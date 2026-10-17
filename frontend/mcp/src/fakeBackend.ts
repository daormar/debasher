import { DigestConflict } from "../../src/api/digestConflict";
import type { Program } from "../../src/models/program";
import { NoProgramMetadata } from "../../src/storage/programStorage";
import type { Backend } from "./backend";

// A backend for the tests of the MCP tools, which needs no server: the
// program metadata of each home directory in memory, saved with the
// digest check of the backend (see persistence.save), and every other
// request answered by `overrides`, or refused as not faked.

export interface FakeBackend extends Backend {
  saved: Map<string, Program>;
  saves: number;
}

function sameContent(a: Program, b: Program): boolean {
  const content = ({ digest: _digest, homeDir: _homeDir, ...rest }: Program) => rest;
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
      if (current && ownHome && (current.digest ?? "") !== (program.digest ?? "") && !sameContent(current, program)) {
        throw new DigestConflict(
          `The program in ${homeDir} was saved elsewhere since it was loaded (digest ${current.digest}).`,
          current.digest ?? ""
        );
      }
      const unchanged = current !== undefined && ownHome && sameContent(current, program);
      // A counter stands for the digest of the real backend
      const digest = unchanged ? current.digest ?? "" : String(Number(ownHome ? current?.digest ?? "0" : "0") + 1);
      saved.set(homeDir, structuredClone({ ...program, homeDir, digest }));
      fake.saves += 1;
      return { digest };
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
