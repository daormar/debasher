import { describe, expect, it } from "vitest";

import { hasUnsavedChanges, onDiskDigest, savedContent } from "./externalChanges";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "./program";

const saved = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", digest: "3" });

describe("hasUnsavedChanges", () => {

  it("sees no change in the digest or the home directory, which loading replaces", () => {
    expect(hasUnsavedChanges({ ...saved(), digest: "9", homeDir: "/elsewhere" }, saved())).toBe(false);
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

describe("onDiskDigest", () => {

  const state = { tabDigest: "3", diskDigest: "3", unsavedChanges: false };

  it("does nothing when there is no program metadata on disk", () => {
    expect(onDiskDigest({ ...state, diskDigest: null })).toBe("none");
    expect(onDiskDigest({ ...state, diskDigest: null, unsavedChanges: true })).toBe("none");
  });

  it("clears any question once the tab holds the digest on disk", () => {
    expect(onDiskDigest(state)).toBe("clear");
    expect(onDiskDigest({ ...state, unsavedChanges: true })).toBe("clear");
  });

  it("loads another digest when the tab holds nothing unsaved", () => {
    expect(onDiskDigest({ ...state, diskDigest: "4" })).toBe("reload");
  });

  it("asks when the tab holds unsaved changes", () => {
    expect(onDiskDigest({ ...state, diskDigest: "4", unsavedChanges: true })).toBe("ask");
  });

});
