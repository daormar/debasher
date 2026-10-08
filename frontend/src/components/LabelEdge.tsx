import { useContext, useEffect, useRef } from "react";
import { Position, getBezierPath, useReactFlow } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";

import type { LabelEdgeData } from "../adapters/reactFlowAdapter";
import { LABEL_RING_RADIUS, labelStub } from "./edgeRoutes";
import { LabelEdgeFocusContext, showsGhost } from "./labelEdgeFocus";
import type { LabelEdgeHover } from "./labelEdgeFocus";

// Horizontal distance (px) between the stubs of the label edges that share
// one input.
const TARGET_STUB_SPACING = 12;

// Longest text (characters) a stub shows; a longer one is cut, and its
// tooltip has it whole. Its length on the canvas stays below the usual gap
// between two rows of processes.
const MAX_TEXT_LENGTH = 24;

const COLOR = "#888";
const SELECTED_COLOR = "var(--xy-edge-stroke-selected-default, #555)";

function shortened(text: string): string {
  return text.length > MAX_TEXT_LENGTH ? `${text.slice(0, MAX_TEXT_LENGTH - 1)}…` : text;
}

/**
 * One stub of a label edge: a short line out of its handle, a ring, and
 * its text, which runs away from the node, on a white halo that keeps it
 * legible over a line or another stub that it crosses. Hovering it sets `hover`, and a
 * double click calls `onJump`. The double click is caught before it bubbles
 * up to the canvas, which would otherwise zoom in on it too. A stub that is
 * not `selectable` catches the click as well, before the canvas selects the
 * edge with it. `end` says which end of the edge it is, for the context
 * menu of the canvas (see ProgramCanvas).
 */
function LabelStub({
  x,
  y,
  side,
  shift,
  text,
  title,
  hover,
  dashed,
  color,
  selectable,
  end,
  onJump,
}: {
  x: number;
  y: number;
  side: "top" | "bottom";
  shift: number;
  text: string;
  title: string;
  hover: LabelEdgeHover;
  dashed: boolean;
  color: string;
  selectable: boolean;
  end: "source" | "target";
  onJump: () => void;
}) {

  const { setHover } = useContext(LabelEdgeFocusContext);

  const groupRef = useRef<SVGGElement>(null);

  const onJumpRef = useRef(onJump);
  onJumpRef.current = onJump;

  useEffect(() => {
    const group = groupRef.current;
    if (!group) {
      return;
    }
    const onDoubleClick = (event: MouseEvent) => {
      event.stopPropagation();
      onJumpRef.current();
    };
    const onClick = (event: MouseEvent) => {
      event.stopPropagation();
    };
    group.addEventListener("dblclick", onDoubleClick);
    if (!selectable) {
      group.addEventListener("click", onClick);
    }
    return () => {
      group.removeEventListener("dblclick", onDoubleClick);
      group.removeEventListener("click", onClick);
    };
  }, [selectable]);

  const { line, ring, textAt } = labelStub(x, y, side, shift);

  return (
    <g
      ref={groupRef}
      className="label-edge-stub"
      data-label-edge-end={end}
      style={{ cursor: "pointer" }}
      onMouseEnter={() => setHover(hover)}
      onMouseLeave={() => setHover(null)}
    >
      <title>{title}</title>
      <polyline
        points={line.map(([px, py]) => `${px},${py}`).join(" ")}
        fill="none"
        stroke="transparent"
        strokeWidth={10}
        pointerEvents="stroke"
      />
      <polyline
        points={line.map(([px, py]) => `${px},${py}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeDasharray={dashed ? "3 2" : undefined}
        pointerEvents="none"
      />
      <circle
        cx={ring[0]}
        cy={ring[1]}
        r={LABEL_RING_RADIUS}
        fill="#fff"
        stroke={color}
        strokeWidth={1.5}
        pointerEvents="all"
      />
      <text
        x={textAt[0]}
        y={textAt[1]}
        transform={`rotate(-90 ${textAt[0]} ${textAt[1]})`}
        textAnchor={side === "top" ? "start" : "end"}
        dominantBaseline="central"
        fontSize={10}
        fill={color}
        stroke="#fff"
        strokeWidth={3}
        paintOrder="stroke"
        pointerEvents="all"
      >
        {shortened(text)}
      </text>
    </g>
  );

}

/**
 * A label edge: instead of a line between its two handles, a stub at each
 * that names the other end, as the net labels of an electronic schematic
 * do. The stub at the target names the source; the stub at the source,
 * drawn by one label edge of the output only (see LabelEdgeData), names its
 * target, or says how many there are when there are several. A dashed stub
 * is an edge from a FIFO.
 *
 * The edge draws a faint ghost of the line that it stands for while one of
 * its stubs is under the pointer, while it is selected, and while its source
 * or its target is the selected process (see showsGhost). A double click on
 * the target stub brings the source into view, and one on the source stub
 * the targets, without zooming in. A source stub that stands for several
 * edges selects none of them, so that the delete key never removes one of
 * them that the user did not pick.
 */
export default function LabelEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {

  const label = data as LabelEdgeData;

  const focus = useContext(LabelEdgeFocusContext);

  const { fitView, getZoom } = useReactFlow();

  const bringIntoView = (processIds: string[]) => {
    void fitView({
      nodes: processIds.map(processId => ({ id: processId })),
      duration: 300,
      maxZoom: getZoom(),
      padding: 0.3,
    });
  };

  const color = selected ? SELECTED_COLOR : COLOR;

  const ghost = showsGhost(focus, {
    id,
    source,
    target,
    sourceKey: label.sourceKey,
    selected: !!selected,
  });

  const [ghostPath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const sourceStub = label.sourceStub;

  const targetCount = sourceStub?.targetTexts.length ?? 0;

  return (
    <>
      {ghost && (
        <path
          d={ghostPath}
          fill="none"
          stroke={color}
          strokeWidth={1}
          strokeDasharray="2 3"
          opacity={0.6}
          pointerEvents="none"
        />
      )}

      <LabelStub
        x={targetX}
        y={targetY}
        side={targetPosition === Position.Bottom ? "bottom" : "top"}
        shift={(label.targetIndex - (label.targetCount - 1) / 2) * TARGET_STUB_SPACING}
        text={label.sourceText}
        title={`From ${label.sourceText}. Double-click to bring it into view.`}
        hover={{ edgeId: id }}
        dashed={label.isFifo}
        color={color}
        selectable
        end="target"
        onJump={() => bringIntoView([source])}
      />

      {sourceStub && (
        <LabelStub
          x={sourceX}
          y={sourceY}
          side={sourcePosition === Position.Top ? "top" : "bottom"}
          shift={0}
          text={targetCount === 1 ? sourceStub.targetTexts[0] : `${targetCount} inputs`}
          title={
            `To ${sourceStub.targetTexts.join(", ")}. ` +
            `Double-click to bring ${targetCount === 1 ? "it" : "them"} into view.`
          }
          hover={{ sourceKey: label.sourceKey }}
          dashed={label.isFifo}
          color={color}
          selectable={targetCount === 1}
          end="source"
          onJump={() => bringIntoView(sourceStub.targetProcessIds)}
        />
      )}
    </>
  );

}
