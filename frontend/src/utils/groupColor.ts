// The border of a selected canvas node (see ProcessNode), whose hue no
// group color takes.
export const SELECTED_NODE_COLOR = "#1a73e8";

// The hue of SELECTED_NODE_COLOR, and how far from it on either side a group
// color stays, so that a group is never taken for a selection.
const SELECTED_HUE = 214;
const SELECTED_HUE_MARGIN = 30;

/**
 * Deterministic string -> HSL color, used to give every "Add program"
 * group (see ProgramProcess.groupSource) a stable, distinct border/badge
 * color in ProcessNode without having to track a palette anywhere. The hue
 * runs over the whole circle but the band around the blue of a selected
 * canvas node.
 */
export function groupColor(groupId: string): string {

  let hash = 0;

  for (let i = 0; i < groupId.length; i++) {
    hash = (hash * 31 + groupId.charCodeAt(i)) | 0;
  }

  const hue =
    (SELECTED_HUE + SELECTED_HUE_MARGIN + (Math.abs(hash) % (360 - 2 * SELECTED_HUE_MARGIN))) % 360;

  return `hsl(${hue}, 65%, 45%)`;

}
