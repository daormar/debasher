import { BaseEdge } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

// Vertical clearance (px) between a handle and where the detour path
// turns sideways, so the elbow doesn't hug the node border.
const STEP = 24;

/**
 * A "back edge" — one whose target sits at or above its source (see
 * isBackEdge in reactFlowAdapter.ts). A plain edge would have to route
 * straight back up from the source's Bottom handle into the target's
 * Top handle (see ProcessNode: every option's handle is fixed to
 * Top(input)/Bottom(output)), cutting through whatever nodes sit
 * between the two. Routed instead as a rectilinear detour out to a
 * lane to the right of every process in the program (data.detourX,
 * computed once in reactFlowAdapter.ts from all processes' positions),
 * which clears every node's box regardless of what's between source
 * and target.
 */
export default function BackEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  style,
  markerEnd,
}: EdgeProps) {

  const detourX =
    (data as { detourX?: number } | undefined)?.detourX ??
    Math.max(sourceX, targetX) + 60;

  const path = [
    `M ${sourceX},${sourceY}`,
    `L ${sourceX},${sourceY + STEP}`,
    `L ${detourX},${sourceY + STEP}`,
    `L ${detourX},${targetY - STEP}`,
    `L ${targetX},${targetY - STEP}`,
    `L ${targetX},${targetY}`,
  ].join(" ");

  return (
    <BaseEdge
      id={id}
      path={path}
      style={style}
      markerEnd={markerEnd}
    />
  );

}
