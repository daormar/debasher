import { BaseEdge } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

import { backEdgeRoute } from "./edgeRoutes";
import type { BackEdgeRouteData } from "./edgeRoutes";

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
 * and target (see backEdgeRoute).
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

  const [first, ...rest] = backEdgeRoute(
    sourceX,
    sourceY,
    targetX,
    targetY,
    data as BackEdgeRouteData | undefined
  );

  const path = [
    `M ${first[0]},${first[1]}`,
    ...rest.map(([x, y]) => `L ${x},${y}`),
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
