import type { EdgeProps } from "@xyflow/react";

// Half-widths (px) at the narrow ("standard" family option) and wide
// ("array" process) ends of the wedge.
const NARROW_HALF_WIDTH = 1.5;
const WIDE_HALF_WIDTH = 6;

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
}: EdgeProps) {

  const narrowEnd = (data as { narrowEnd?: "source" | "target" } | undefined)?.narrowEnd ?? "source";

  const sourceHalfWidth = narrowEnd === "source" ? NARROW_HALF_WIDTH : WIDE_HALF_WIDTH;
  const targetHalfWidth = narrowEnd === "source" ? WIDE_HALF_WIDTH : NARROW_HALF_WIDTH;

  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const length = Math.hypot(dx, dy) || 1;

  // Unit normal to the source->target line.
  const nx = -dy / length;
  const ny = dx / length;

  const points = [
    [sourceX + nx * sourceHalfWidth, sourceY + ny * sourceHalfWidth],
    [targetX + nx * targetHalfWidth, targetY + ny * targetHalfWidth],
    [targetX - nx * targetHalfWidth, targetY - ny * targetHalfWidth],
    [sourceX - nx * sourceHalfWidth, sourceY - ny * sourceHalfWidth],
  ]
    .map(([x, y]) => `${x},${y}`)
    .join(" ");

  return (
    <polygon
      points={points}
      fill="#999"
      stroke="none"
    />
  );

}
