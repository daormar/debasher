import { describe, expect, it } from "vitest";

import { modDirFromLines, modDirToLines, splitModDir } from "./modDir";

describe("splitModDir", () => {

  it("splits on colons, on line breaks and on both", () => {
    expect(splitModDir("/a:/b")).toEqual(["/a", "/b"]);
    expect(splitModDir("/a\n/b")).toEqual(["/a", "/b"]);
    expect(splitModDir("/a:/b\n/c")).toEqual(["/a", "/b", "/c"]);
  });

  it("drops blanks and empty entries", () => {
    expect(splitModDir("  /a  \n\n:/b:\n")).toEqual(["/a", "/b"]);
    expect(splitModDir("")).toEqual([]);
  });

});

describe("modDirFromLines and modDirToLines", () => {

  it("keep one directory per line in the editor and colons in the program", () => {
    expect(modDirFromLines("/a\n/b\n")).toBe("/a:/b");
    expect(modDirToLines("/a:/b")).toBe("/a\n/b");
  });

  it("go back and forth without changes", () => {
    expect(modDirFromLines(modDirToLines("/a:/b:/c"))).toBe("/a:/b:/c");
  });

});
