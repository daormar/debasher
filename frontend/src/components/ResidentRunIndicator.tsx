import type { ResidentRunPhase } from "../models/residentRun";

interface Props {
  phase: Exclude<ResidentRunPhase, "new">;
  // For "stopped": whether every process finished, an orderly stop.
  inOrder: boolean;
  // Hides the indicator, and stops nothing: a resident program is meant to
  // outlive the tab.
  onHide: () => void;
}

const MESSAGE: Record<Exclude<ResidentRunPhase, "new" | "stopped">, string> = {
  launching: "Launching program…",
  live: "Program live: it runs until it is stopped.",
  stopping: "Stopping program…",
};

const STOPPED_IN_ORDER =
  "Program stopped in order. The next launch resumes it with nothing lost.";

const STOPPED_ABRUPTLY =
  "Program stopped abruptly: some node did not end cleanly, after a hard " +
  "kill, a node that failed, or a Supervisor that gave up on a node. The " +
  "next launch resumes each node from its last checkpoint and its input " +
  "log, and what the FIFOs held may have been lost.";

export default function ResidentRunIndicator({ phase, inOrder, onHide }: Props) {

  const message = phase === "stopped"
    ? (inOrder ? STOPPED_IN_ORDER : STOPPED_ABRUPTLY)
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
