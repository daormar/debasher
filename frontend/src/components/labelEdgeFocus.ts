import { createContext } from "react";

// What the canvas tells every label edge about where the user's attention
// is, so that each one knows whether to draw its ghost line (see
// LabelEdge): the stub under the pointer, which is the target stub of one
// edge or the source stub shared by every label edge of an output, and the
// selected process.
export type LabelEdgeHover =
  | { edgeId: string }
  | { sourceKey: string }
  | null;

export interface LabelEdgeFocus {
  hover: LabelEdgeHover;
  setHover: (hover: LabelEdgeHover) => void;
  selectedProcessId: string | null;
}

export const LabelEdgeFocusContext = createContext<LabelEdgeFocus>({
  hover: null,
  setHover: () => {},
  selectedProcessId: null,
});

/**
 * Whether a label edge draws its ghost line: while one of its stubs is
 * under the pointer, while it is selected, and while its source or its
 * target is the selected process.
 */
export function showsGhost(
  focus: LabelEdgeFocus,
  edge: { id: string; source: string; target: string; sourceKey: string; selected: boolean }
): boolean {
  const { hover, selectedProcessId } = focus;
  return (
    edge.selected ||
    (hover !== null && "edgeId" in hover && hover.edgeId === edge.id) ||
    (hover !== null && "sourceKey" in hover && hover.sourceKey === edge.sourceKey) ||
    (selectedProcessId !== null &&
      (selectedProcessId === edge.source || selectedProcessId === edge.target))
  );
}
