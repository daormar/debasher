export interface ProgramEdge {

  id: string;

  sourceProcessId: string;

  sourceOptionId: string;

  targetProcessId: string;

  targetOptionId: string;

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
