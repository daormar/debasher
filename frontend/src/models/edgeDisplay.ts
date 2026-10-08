import type { EdgeDisplay } from "./edge";
import { edgeEndText, isLabelEdge } from "./edge";
import type { Program } from "./program";

// One entry of the context menu of an edge: set how the canvas draws the
// given edges.
export interface EdgeDisplayAction {
  label: string;
  edgeIds: string[];
  display: EdgeDisplay;
}

/**
 * The entries of the context menu of an edge. For the edge itself, the
 * other way of drawing it: as a label edge or as a line. For its output,
 * when the output has more than one edge, drawing all of them one way or
 * the other, whichever would change one of them. Opened from the source
 * stub of a label edge that stands for several edges of the output (see
 * LabelEdge), the menu is about the output only, since the user picked no
 * single edge there.
 */
export function edgeDisplayActions(
  program: Program,
  edgeId: string,
  fromSharedSourceStub = false
): EdgeDisplayAction[] {

  const edge = program.edges.find(e => e.id === edgeId);

  if (!edge) {
    return [];
  }

  const actions: EdgeDisplayAction[] = [];

  if (!fromSharedSourceStub) {
    actions.push(
      isLabelEdge(edge)
        ? { label: "Show as line", edgeIds: [edge.id], display: "line" }
        : { label: "Show as label", edgeIds: [edge.id], display: "label" }
    );
  }

  const siblings = program.edges.filter(
    e => e.sourceProcessId === edge.sourceProcessId && e.sourceOptionId === edge.sourceOptionId
  );

  if (siblings.length > 1) {

    const sourceProcess = program.processes.find(process => process.id === edge.sourceProcessId);
    const sourceOption = sourceProcess?.options.find(option => option.id === edge.sourceOptionId);
    const output = edgeEndText(sourceProcess?.name ?? "?", sourceOption?.label ?? "?");
    const edgeIds = siblings.map(e => e.id);

    if (siblings.some(e => !isLabelEdge(e))) {
      actions.push({ label: `Show the ${siblings.length} edges of ${output} as labels`, edgeIds, display: "label" });
    }

    if (siblings.some(isLabelEdge)) {
      actions.push({ label: `Show the ${siblings.length} edges of ${output} as lines`, edgeIds, display: "line" });
    }

  }

  return actions;

}
