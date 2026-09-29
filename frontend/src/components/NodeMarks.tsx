import { WIRING_EDGE_COLOR } from "../adapters/reactFlowAdapter";
import type { NodeKind } from "../models/node";

// The marks of a canvas node of a resident program, and of its legend. Each
// is drawn as an inline SVG, not as a character of a font, so that it looks
// the same whatever fonts the browser has; data-mark names it.

const MARK_COLOR = "#444";

// The band behind the head of a canvas node of a resident program, which
// groups its name, its node kind and its marks: translucent, so that the
// background of the canvas node, the color of its process status, shows
// through it in every status. The Supervisor's takes the blue gray of its
// wiring, and its chip a darker shade of it, which white text reads on.
export const HEAD_BAND_COLOR = "rgba(0, 0, 0, 0.05)";
export const SUPERVISOR_HEAD_BAND_COLOR = `${WIRING_EDGE_COLOR}38`;
const SUPERVISOR_CHIP_COLOR = "#5f7399";

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
 * A trigger port of the Supervisor wiring: a yellow lightning bolt, drawn in
 * place of the round handle on an initiator and on the Supervisor.
 */
export function TriggerMark() {
  return (
    <svg data-mark="trigger" width={12} height={14} viewBox="0 0 12 14" aria-label="Trigger port">
      <title>Trigger port of the Supervisor wiring</title>
      <path d="M 7 0.5 L 1 8 L 5.5 8 L 4.5 13.5 L 11 5.5 L 6.5 5.5 Z" fill="#f2c200" stroke="#9a7b00" strokeWidth={0.8} strokeLinejoin="round" />
    </svg>
  );
}

/**
 * The node kind, in the head of a canvas node. The Supervisor's stands apart,
 * in the blue gray of its wiring, since it is not a business node and the
 * user does not edit its code.
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
        border: `1px solid ${isSupervisor ? SUPERVISOR_CHIP_COLOR : "#bbb"}`,
        background: isSupervisor ? SUPERVISOR_CHIP_COLOR : "#f4f4f4",
        color: isSupervisor ? "#fff" : "#444",
        whiteSpace: "nowrap",
      }}
    >
      {kind}
    </span>
  );
}
