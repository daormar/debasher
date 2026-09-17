import type { EdgeProps } from "@xyflow/react";

// Half-widths (px) at the narrow ("standard" family option) and wide
// ("array" process) ends of the wedge.
const NARROW_HALF_WIDTH = 1.5;
const WIDE_HALF_WIDTH = 6;

// Minimum half-width (px) of the invisible click/hit-test area, so the
// wedge stays easy to select near its narrow end even though it's only
// NARROW_HALF_WIDTH*2 px wide visually there. Plain edges get an
// equivalent generous hit area for free from ReactFlow's own
// `react-flow__edge-interaction` path; this wedge has to add its own.
const MIN_HIT_HALF_WIDTH = 8;

/**
 * A scatter/gather connection between a "standard" process's fanout
 * family option (see isFanoutOption) and the paired "array" process —
 * drawn as a filled wedge, narrow at the family end and wide at the
 * array end, so the single edge visually reads as "one becomes many"
 * rather than a plain 1:1 connection.
 */
export default function FanoutEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  selected,
}: EdgeProps) {

  const fanoutData = data as { narrowEnd?: "source" | "target"; isFifo?: boolean } | undefined;
  const narrowEnd = fanoutData?.narrowEnd ?? "source";
  const isFifo = fanoutData?.isFifo ?? false;

  // Standard/FIFO edges pick up ReactFlow's built-in selected-edge
  // highlight for free, since it targets the `react-flow__edge-path`
  // class BaseEdge renders. This edge draws its own filled polygon
  // instead, so it has to mirror that highlight color itself.
  const fill = selected ? "var(--xy-edge-stroke-selected-default, #555)" : "#999";

  const sourceHalfWidth = narrowEnd === "source" ? NARROW_HALF_WIDTH : WIDE_HALF_WIDTH;
  const targetHalfWidth = narrowEnd === "source" ? WIDE_HALF_WIDTH : NARROW_HALF_WIDTH;

  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const length = Math.hypot(dx, dy) || 1;

  // Unit normal to the source->target line.
  const nx = -dy / length;
  const ny = dx / length;

  const wedgePoints = (sourceHW: number, targetHW: number) =>
    [
      [sourceX + nx * sourceHW, sourceY + ny * sourceHW],
      [targetX + nx * targetHW, targetY + ny * targetHW],
      [targetX - nx * targetHW, targetY - ny * targetHW],
      [sourceX - nx * sourceHW, sourceY - ny * sourceHW],
    ]
      .map(([x, y]) => `${x},${y}`)
      .join(" ");

  const points = wedgePoints(sourceHalfWidth, targetHalfWidth);
  const hitPoints = wedgePoints(
    Math.max(sourceHalfWidth, MIN_HIT_HALF_WIDTH),
    Math.max(targetHalfWidth, MIN_HIT_HALF_WIDTH),
  );

  // A FIFO-backed fanout is filled lighter and outlined with the same
  // dashed stroke used for plain FIFO edges (see reactFlowAdapter's
  // strokeDasharray), so the wedge still reads as a FIFO connection
  // instead of a solid, always-connected one.
  return (
    <>
      <polygon points={hitPoints} fill="transparent" pointerEvents="all" />
      <polygon
        points={points}
        fill={fill}
        fillOpacity={isFifo ? 0.35 : 1}
        stroke={isFifo ? fill : "none"}
        strokeDasharray={isFifo ? "6 4" : undefined}
        pointerEvents="none"
      />
    </>
  );

}
