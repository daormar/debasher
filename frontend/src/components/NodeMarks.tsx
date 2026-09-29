import type { NodeKind } from "../models/node";

// The marks of a canvas node of a resident program, and of its legend. Each
// is drawn as an inline SVG, not as a character of a font, so that it looks
// the same whatever fonts the browser has; data-mark names it.

const MARK_COLOR = "#444";

/** An initiator, where rounds start. */
export function InitiatorMark() {
  return (
    <svg data-mark="initiator" width={12} height={12} viewBox="0 0 12 12" aria-label="Initiator">
      <title>Initiator: rounds start here</title>
      <path d="M 2 1 L 11 6 L 2 11 Z" fill={MARK_COLOR} />
    </svg>
  );
}

/** A node that observes the world outside the program. */
export function ObserveMark() {
  return (
    <svg data-mark="observe" width={16} height={12} viewBox="0 0 16 12" aria-label="Observes the outside world">
      <title>Observes the outside world</title>
      <path d="M 1 6 Q 8 -1 15 6 Q 8 13 1 6 Z" fill="none" stroke={MARK_COLOR} strokeWidth={1.4} />
      <circle cx={8} cy={6} r={2.2} fill={MARK_COLOR} />
    </svg>
  );
}

/**
 * Data that cross the border of the program: an arrow that points the way
 * the data go, down into an external input above its handle, and down out of
 * a business output read outside the program below its handle.
 */
export function OutsideMark({ kind }: { kind: "externalInput" | "readOutside" }) {
  const title = kind === "externalInput"
    ? "External input: written from outside the program"
    : "Read outside the program: something outside has to read it";
  return (
    <svg data-mark={kind} width={10} height={12} viewBox="0 0 10 12" aria-label={title}>
      <title>{title}</title>
      <path d="M 5 1 L 5 10 M 1.5 6.5 L 5 10.5 L 8.5 6.5" fill="none" stroke={MARK_COLOR} strokeWidth={1.6} />
    </svg>
  );
}

/**
 * The node kind, in the head of a canvas node. The Supervisor's stands apart,
 * since it is not a business node and the user does not edit its code.
 */
export function NodeKindChip({ kind }: { kind: NodeKind }) {
  const isSupervisor = kind === "Supervisor";
  return (
    <span
      data-mark="node-kind"
      data-node-kind={kind}
      style={{
        fontSize: 10,
        padding: "1px 6px",
        borderRadius: 8,
        border: `1px solid ${isSupervisor ? "#555" : "#bbb"}`,
        background: isSupervisor ? "#555" : "#f4f4f4",
        color: isSupervisor ? "#fff" : "#444",
        whiteSpace: "nowrap",
      }}
    >
      {kind}
    </span>
  );
}
