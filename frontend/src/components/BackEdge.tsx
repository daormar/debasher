import { BaseEdge } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

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

  const edgeData = data as
    { detourX?: number; sourceLeftRank?: number; targetLeftRank?: number } | undefined;

  const sourceLeftRank = edgeData?.sourceLeftRank ?? 0;
  const targetLeftRank = edgeData?.targetLeftRank ?? 0;

  const detourX =
    (edgeData?.detourX ?? Math.max(sourceX, targetX) + 60) +
    (sourceLeftRank + targetLeftRank) * PER_PORT_H_STEP;

  const sourceStep = STEP + sourceLeftRank * PER_PORT_STEP;
  const targetStep = STEP + targetLeftRank * PER_PORT_STEP;

  const path = [
    `M ${sourceX},${sourceY}`,
    `L ${sourceX},${sourceY + sourceStep}`,
    `L ${detourX},${sourceY + sourceStep}`,
    `L ${detourX},${targetY - targetStep}`,
    `L ${targetX},${targetY - targetStep}`,
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
