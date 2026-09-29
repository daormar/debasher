import { describe, expect, it } from "vitest";
import { backEdgeRoute, taperedBand } from "./edgeRoutes";

describe("backEdgeRoute", () => {
  it("goes down, out to the lane, up, and in to the target from above", () => {
    expect(backEdgeRoute(10, 200, 50, 0, { detourX: 300 })).toEqual([
      [10, 200],
      [10, 224],
      [300, 224],
      [300, -24],
      [50, -24],
      [50, 0],
    ]);
  });

  it("sets apart the edges of ports further left", () => {
    const [, down, out] = backEdgeRoute(10, 200, 50, 0, { detourX: 300, sourceLeftRank: 1, targetLeftRank: 1 });
    expect(down).toEqual([10, 238]);
    expect(out[0]).toBe(340);
  });
});

describe("taperedBand", () => {
  it("is the wedge between both ends on a straight route", () => {
    expect(taperedBand([[0, 0], [0, 100]], 1.5, 6)).toEqual([
      [-1.5, 0],
      [-6, 100],
      [6, 100],
      [1.5, 0],
    ]);
  });

  it("widens with the length run, and meets at the miter point of a corner", () => {
    // Down 10, then right 10: half-width 2 at the corner, halfway.
    const band = taperedBand([[0, 0], [0, 10], [10, 10]], 1, 3);
    expect(band).toEqual([
      [-1, 0],
      [-2, 12],
      [10, 13],
      [10, 7],
      [2, 8],
      [1, 0],
    ]);
  });

  it("drops a point that repeats the one before it", () => {
    expect(taperedBand([[0, 0], [0, 0], [0, 100]], 1.5, 6)).toEqual(taperedBand([[0, 0], [0, 100]], 1.5, 6));
  });
});
