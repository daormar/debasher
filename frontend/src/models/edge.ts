// How the canvas draws an edge: as a line between its two handles, or as a
// label edge, a short stub at each handle that names the other end, with no
// line between them. It only changes the drawing: script generation ignores
// it.
export type EdgeDisplay = "line" | "label";

export interface ProgramEdge {

  id: string;

  sourceProcessId: string;

  sourceOptionId: string;

  targetProcessId: string;

  targetOptionId: string;

  // Absent in a program saved before edges had a display: a line.
  display?: EdgeDisplay;

}

export function isLabelEdge(edge: ProgramEdge): boolean {
  return edge.display === "label";
}

// The "[proc;opt]" sentinel a connected option's value takes, shared by
// the edits that derive it (see programEdits.ts) and any UI that needs to
// display the same thing read-only.
export function buildConnectionSentinel(
  sourceProcessName: string,
  sourceOptionLabel: string
): string {
  return `[${sourceProcessName};${sourceOptionLabel}]`;
}
