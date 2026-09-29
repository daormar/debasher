import { BaseEdge, useInternalNode } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

// Vertical clearance (px) between a handle and where the loop turns
// sideways, and the extra clearance per port to the right of the source or
// target port on its node (see data.sourceLeftRank / data.targetLeftRank in
// reactFlowAdapter.ts), as in BackEdge.
const STEP = 24;
const PER_PORT_STEP = 14;

// Horizontal clearance (px) between the right side of the node's box and the
// loop, and the extra distance per combined rank, so that several self-loops
// of the same node run apart from each other, the one that leaves the
// leftmost ports around the others.
const MARGIN = 24;
const PER_PORT_H_STEP = 16;

/**
 * A self-loop: a connection from an output of a process to an input of the
 * same process, drawn next to its node: from its output handle, along the
 * bottom, around the right side of the node, clear of its box, to its input
 * handle, along the top. The box comes from the size that the canvas library
 * measured for the node, which the program model does not hold.
 */
export default function SelfLoopEdge({
  id,
  source,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  style,
  markerEnd,
}: EdgeProps) {

  const node = useInternalNode(source);

  const edgeData = data as { sourceLeftRank?: number; targetLeftRank?: number } | undefined;

  const sourceLeftRank = edgeData?.sourceLeftRank ?? 0;
  const targetLeftRank = edgeData?.targetLeftRank ?? 0;

  const nodeRight = node
    ? node.internals.positionAbsolute.x + (node.measured.width ?? 0)
    : Math.max(sourceX, targetX);

  const loopX = nodeRight + MARGIN + (sourceLeftRank + targetLeftRank) * PER_PORT_H_STEP;

  const sourceStep = STEP + sourceLeftRank * PER_PORT_STEP;
  const targetStep = STEP + targetLeftRank * PER_PORT_STEP;

  const path = [
    `M ${sourceX},${sourceY}`,
    `L ${sourceX},${sourceY + sourceStep}`,
    `L ${loopX},${sourceY + sourceStep}`,
    `L ${loopX},${targetY - targetStep}`,
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
