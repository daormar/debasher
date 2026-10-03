import { describe, expect, it } from "vitest";

import { hasUnsavedChanges, onDiskRevision, savedContent } from "./externalChanges";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "./program";

const saved = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", revision: 3 });

describe("hasUnsavedChanges", () => {

  it("sees no change in the revision or the home directory, which loading replaces", () => {
    expect(hasUnsavedChanges({ ...saved(), revision: 9, homeDir: "/elsewhere" }, saved())).toBe(false);
  });

  it("sees no change in the order of the keys of an object", () => {
    const program = saved();
    const reordered = Object.fromEntries(Object.entries(program).reverse()) as unknown as Program;
    expect(savedContent(reordered)).toBe(savedContent(program));
  });

  it("sees no change in a field that holds undefined, which the metadata cannot hold", () => {
    expect(hasUnsavedChanges({ ...saved(), sourceDir: undefined } as unknown as Program, { ...saved(), sourceDir: undefined } as unknown as Program)).toBe(false);
    const withUndefined = { ...saved(), extra: undefined } as unknown as Program;
    expect(hasUnsavedChanges(withUndefined, saved())).toBe(false);
  });

  it("sees any other change, a position included", () => {
    expect(hasUnsavedChanges({ ...saved(), description: "edited" }, saved())).toBe(true);
    expect(hasUnsavedChanges({ ...saved(), envVars: { A: "1" } }, saved())).toBe(true);
  });

});

describe("onDiskRevision", () => {

  const state = { tabRevision: 3, diskRevision: 3, unsavedChanges: false };

  it("does nothing when there is no program metadata on disk", () => {
    expect(onDiskRevision({ ...state, diskRevision: null })).toBe("none");
    expect(onDiskRevision({ ...state, diskRevision: null, unsavedChanges: true })).toBe("none");
  });

  it("clears any question once the tab holds the revision on disk", () => {
    expect(onDiskRevision(state)).toBe("clear");
    expect(onDiskRevision({ ...state, unsavedChanges: true })).toBe("clear");
  });

  it("loads another revision when the tab holds nothing unsaved", () => {
    expect(onDiskRevision({ ...state, diskRevision: 4 })).toBe("reload");
  });

  it("asks when the tab holds unsaved changes", () => {
    expect(onDiskRevision({ ...state, diskRevision: 4, unsavedChanges: true })).toBe("ask");
  });

});
