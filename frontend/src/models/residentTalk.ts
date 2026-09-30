import { isBusinessOutput, nodeOptionRole } from "./node";
import type { ProgramOption } from "./option";
import type { Program } from "./program";

// "Talk to FIFOs" in a resident program (see "Observing and talking to a
// live program" in doc/design_doc_webui.md): what it offers, and how it
// shows what it writes and reads.

export interface TalkCandidate {
  id: string;
  processName: string;
  option: ProgramOption;
}

// The FIFOs it offers: the external inputs, into which the user writes, and
// the business outputs with no connection, from which the user reads. The
// control ports and the rest of the Supervisor wiring are not in the
// program model, and so are never offered.
export function talkCandidates(program: Program): { inputs: TalkCandidate[]; outputs: TalkCandidate[] } {
  const inputs: TalkCandidate[] = [];
  const outputs: TalkCandidate[] = [];
  for (const process of program.processes) {
    for (const option of process.options) {
      const candidate = { id: option.id, processName: process.name, option };
      if (nodeOptionRole(option) === "externalInput") {
        inputs.push(candidate);
      } else if (isBusinessOutput(option) && !program.edges.some(edge => edge.sourceOptionId === option.id)) {
        outputs.push(candidate);
      }
    }
  }
  return { inputs, outputs };
}

export type TalkMode = "json" | "text";

// What a read of an output answered: an envelope, a line that is not one,
// or nothing within its bound.
export interface ResidentFifoRead {
  envelope?: { type: string; seq: number | null; payload: unknown } | null;
  unparsable?: string | null;
  timedOut?: boolean;
  error?: string | null;
}

// One line of the transcript: a message written, or something read.
export type TalkEntry =
  | { kind: "written"; port: string; payload: unknown }
  | { kind: "read"; port: string; read: ResidentFifoRead };

// The payload as the user wrote it, as the backend sends it: in JSON mode
// the value parsed, in text mode the text as a string. Undefined when JSON
// mode is given text that does not parse.
export function draftPayload(draft: string, mode: TalkMode): unknown {
  if (mode === "text") {
    return draft;
  }
  try {
    return JSON.parse(draft);
  } catch {
    return undefined;
  }
}

function barrierText(payload: unknown): string {
  const barrier = (payload ?? {}) as { epoch?: unknown; halt?: unknown };
  return `[round ${String(barrier.epoch)}${barrier.halt ? ", halt" : ""}: the marker of a round (BARRIER)]`;
}

// The text of a line of the transcript: ">" for what was written, "<" for a
// DATA read, with its sequence number, and brackets for the rest.
export function entryText(entry: TalkEntry): string {
  if (entry.kind === "written") {
    return `> ${entry.port}: ${JSON.stringify(entry.payload)}`;
  }
  const { envelope, unparsable } = entry.read;
  if (unparsable != null) {
    return `< ${entry.port}: [not an envelope] ${unparsable}`;
  }
  if (!envelope) {
    return `< ${entry.port}: [nothing]`;
  }
  switch (envelope.type) {
    case "DATA":
      return `< ${entry.port}${envelope.seq != null ? ` #${envelope.seq}` : ""}: ${JSON.stringify(envelope.payload)}`;
    case "BARRIER":
      return `< ${entry.port}: ${barrierText(envelope.payload)}`;
    case "CLOSE":
      return `< ${entry.port}: [the writer closed the channel for good (CLOSE)]`;
    default:
      return `< ${entry.port}: [${envelope.type}] ${JSON.stringify(envelope.payload)}`;
  }
}
