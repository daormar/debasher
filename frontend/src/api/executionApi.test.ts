import { describe, expect, it } from "vitest";
import { pathInspectionText } from "./executionApi";

describe("pathInspectionText", () => {
  it("shows a file's content and a directory's listing", () => {
    expect(pathInspectionText("/d/f", { kind: "file", content: "a\nb\n" })).toBe("a\nb\n");
    expect(pathInspectionText("/d", { kind: "directory", entries: ["f", "sub/"] })).toBe("f\nsub/");
    expect(pathInspectionText("/d", { kind: "directory", entries: [] })).toBe("(empty directory)");
  });

  it("says why neither is shown", () => {
    expect(pathInspectionText("/d/b", { kind: "binary" }))
      .toBe("Warning: /d/b looks like a binary file. Content not shown.");
    expect(pathInspectionText("/nope", { kind: "missing" })).toBe("Path not found: /nope");
  });
});
