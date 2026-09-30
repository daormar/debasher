// The route of an edge that goes back up (see isBackEdge in
// reactFlowAdapter.ts), shared by BackEdge, which strokes it, and by
// FanoutEdge, which draws its wedge along it.

// Vertical clearance (px) between a handle and where the detour path
// turns sideways, so the elbow doesn't hug the node border.
const STEP = 24;

// Extra vertical clearance (px) added per port to the right of the
// source/target port on its node (see data.sourceLeftRank /
// data.targetLeftRank in reactFlowAdapter.ts), so back edges leaving
// or arriving at different ports on the same node peel off at
// different heights instead of running on top of each other.
const PER_PORT_STEP = 14;

// Extra horizontal detour distance (px) added per combined rank (see
// PER_PORT_STEP above), so back edges that already sit at different
// heights near their source/target also run through the detour lane
// at different x, rather than converging back onto the same line.
const PER_PORT_H_STEP = 20;

export type Point = [number, number];

/**
 * What the adapter gives a back edge: the x of the detour lane, to the
 * right of every process, and the ranks of its ports.
 */
export interface BackEdgeRouteData {
  detourX?: number;
  sourceLeftRank?: number;
  targetLeftRank?: number;
}

/**
 * The points of the rectilinear detour of a back edge: down from the
 * source handle, out to the lane to the right of every process in the
 * program, up, and back in to the target handle from above, which clears
 * every node's box regardless of what's between source and target.
 */
export function backEdgeRoute(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  data: BackEdgeRouteData | undefined
): Point[] {

  const sourceLeftRank = data?.sourceLeftRank ?? 0;
  const targetLeftRank = data?.targetLeftRank ?? 0;

  const detourX =
    (data?.detourX ?? Math.max(sourceX, targetX) + 60) +
    (sourceLeftRank + targetLeftRank) * PER_PORT_H_STEP;

  const sourceStep = STEP + sourceLeftRank * PER_PORT_STEP;
  const targetStep = STEP + targetLeftRank * PER_PORT_STEP;

  return [
    [sourceX, sourceY],
    [sourceX, sourceY + sourceStep],
    [detourX, sourceY + sourceStep],
    [detourX, targetY - targetStep],
    [targetX, targetY - targetStep],
    [targetX, targetY],
  ];

}

/**
 * The outline of a band along `route` whose half-width goes from
 * `startHalfWidth` at its first point to `endHalfWidth` at its last, in
 * proportion to the length run: the wedge of a fanout edge, which is a
 * single quadrilateral when the route is a straight line. Each side is
 * the route shifted along its normals, joined at a corner by the miter
 * point, where both shifted segments meet.
 */
export function taperedBand(
  route: Point[],
  startHalfWidth: number,
  endHalfWidth: number
): Point[] {

  // A point that repeats the one before it adds a segment with no
  // direction, and is dropped; a route that is a single point keeps both
  // ends.
  const deduped = route.filter(
    (point, i) => i === 0 || point[0] !== route[i - 1][0] || point[1] !== route[i - 1][1]
  );
  const points = deduped.length >= 2 ? deduped : [route[0], route[route.length - 1]];

  // The unit normal of each segment.
  const normals = points.slice(1).map((point, i): Point => {
    const dx = point[0] - points[i][0];
    const dy = point[1] - points[i][1];
    const length = Math.hypot(dx, dy) || 1;
    return [-dy / length, dx / length];
  });

  const runs = [0];
  for (let i = 1; i < points.length; i++) {
    runs.push(runs[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  }
  const total = runs[runs.length - 1] || 1;

  const offsets = points.map((_, i): Point => {
    if (i === 0) {
      return normals[0];
    }
    if (i === points.length - 1) {
      return normals[normals.length - 1];
    }
    const [ax, ay] = normals[i - 1];
    const [bx, by] = normals[i];
    const scale = 1 + ax * bx + ay * by;
    return [(ax + bx) / scale, (ay + by) / scale];
  });

  const halfWidths = runs.map(run => startHalfWidth + (endHalfWidth - startHalfWidth) * (run / total));

  const side = (sign: number) =>
    points.map(([x, y], i): Point => [
      x + sign * offsets[i][0] * halfWidths[i],
      y + sign * offsets[i][1] * halfWidths[i],
    ]);

  return [...side(1), ...side(-1).reverse()];

}
