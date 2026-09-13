/**
 * Deterministic string -> HSL color, used to give every "Add program"
 * group (see ProgramProcess.groupSource) a stable, distinct border/badge
 * color in ProcessNode without having to track a palette anywhere.
 */
export function groupColor(groupId: string): string {

  let hash = 0;

  for (let i = 0; i < groupId.length; i++) {
    hash = (hash * 31 + groupId.charCodeAt(i)) | 0;
  }

  const hue = Math.abs(hash) % 360;

  return `hsl(${hue}, 65%, 45%)`;

}
