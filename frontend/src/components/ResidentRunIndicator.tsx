import { stoppedAbruptlyText, stoppedInOrderText, type ResidentRunPhase } from "../models/residentRun";

interface Props {
  phase: Exclude<ResidentRunPhase, "new">;
  // For "stopped": whether every process finished, an orderly stop.
  inOrder: boolean;
  // For "stopped": whether the program is durable, which decides what the
  // next launch starts from.
  durable: boolean;
  // Hides the indicator, and stops nothing: a resident program is meant to
  // outlive the tab.
  onHide: () => void;
}

const MESSAGE: Record<Exclude<ResidentRunPhase, "new" | "stopped">, string> = {
  launching: "Launching program…",
  live: "Program live: it runs until it is stopped.",
  stopping: "Stopping program…",
};

export default function ResidentRunIndicator({ phase, inOrder, durable, onHide }: Props) {

  const message = phase === "stopped"
    ? (inOrder ? stoppedInOrderText(durable) : stoppedAbruptlyText(durable))
    : MESSAGE[phase];

  return (

    <div
      data-resident-phase={phase}
      style={{
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
        padding: "10px 12px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        maxWidth: 360,
        fontSize: 14,
      }}
    >

      <span>
        {message}
      </span>

      <button onClick={onHide}>
        Hide
      </button>

    </div>

  );

}
