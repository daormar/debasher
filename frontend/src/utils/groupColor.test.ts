import { describe, expect, it } from "vitest";
import { groupColor } from "./groupColor";

describe("groupColor", () => {
  it("returns an hsl() color string", () => {
    expect(groupColor("my-group")).toMatch(/^hsl\(\d+, 65%, 45%\)$/);
  });

  it("is deterministic for the same input", () => {
    expect(groupColor("my-group")).toBe(groupColor("my-group"));
  });

  it("never takes a hue near the blue of a selected canvas node", () => {
    for (let i = 0; i < 2000; i++) {
      const hue = Number(groupColor(`group-${i}`).match(/^hsl\((\d+),/)![1]);
      expect(Math.abs(hue - 214)).toBeGreaterThanOrEqual(30);
    }
  });

  it("gives different groups different hues (in general)", () => {
    expect(groupColor("group-a")).not.toBe(groupColor("group-b"));
  });
});
