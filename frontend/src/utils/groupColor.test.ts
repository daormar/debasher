import { describe, expect, it } from "vitest";
import { groupColor } from "./groupColor";

describe("groupColor", () => {
  it("returns an hsl() color string", () => {
    expect(groupColor("my-group")).toMatch(/^hsl\(\d+, 65%, 45%\)$/);
  });

  it("is deterministic for the same input", () => {
    expect(groupColor("my-group")).toBe(groupColor("my-group"));
  });

  it("gives different groups different hues (in general)", () => {
    expect(groupColor("group-a")).not.toBe(groupColor("group-b"));
  });
});
