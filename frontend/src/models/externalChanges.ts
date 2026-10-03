import type { Program } from "./program";

// What the program metadata keeps of a program, as text: every field but the
// revision and the home directory, which loading replaces, with the keys of
// every object in order, so that the order in which an edit built an object
// does not count, and with no field that holds undefined, which the metadata
// cannot hold.
export function savedContent(program: Program): string {
  const kept: Partial<Program> = { ...program };
  delete kept.revision;
  delete kept.homeDir;
  return JSON.stringify(canonical(kept));
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonical);
  }
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(
      Object.keys(record)
        .filter(key => record[key] !== undefined)
        .sort()
        .map(key => [key, canonical(record[key])])
    );
  }
  return value;
}

// Whether `program` holds changes that `saved`, the program as it was last
// loaded or saved, does not: what leaving the editor would lose.
export function hasUnsavedChanges(program: Program, saved: Program): boolean {
  return savedContent(program) !== savedContent(saved);
}

// What the editor does when it learns the revision of the program metadata in
// the home directory: nothing, clear the question asked about a revision that
// the tab has since caught up with, load the program again, or ask the user.
export type DiskRevisionAction = "none" | "clear" | "reload" | "ask";

export interface DiskRevisionState {
  // The revision the tab loaded or last saved.
  tabRevision: number;
  // The revision of the program metadata on disk, null when there is none.
  diskRevision: number | null;
  unsavedChanges: boolean;
}

// Someone else saved the program when the revision on disk is not the one of
// the tab. A tab with nothing unsaved loads the program again, since it loses
// nothing; a tab with unsaved changes asks the user. Once the tab holds the
// revision on disk, whoever brought it there, nothing is left to ask.
export function onDiskRevision(state: DiskRevisionState): DiskRevisionAction {
  const { tabRevision, diskRevision, unsavedChanges } = state;
  if (diskRevision === null) {
    return "none";
  }
  if (diskRevision === tabRevision) {
    return "clear";
  }
  return unsavedChanges ? "ask" : "reload";
}
