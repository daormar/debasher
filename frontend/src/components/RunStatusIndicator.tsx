import type { GeneralRunPhase } from "../models/generalRun";

interface Props {
  phase: Exclude<GeneralRunPhase, "idle">;
  // debasher_status's output from the last reading, shown below the
  // message when the run did not finish, so the failure can be
  // diagnosed on the spot. Ignored for any other phase.
  output?: string | null;
  // Hides the indicator, and stops nothing: a run lives in its output
  // directory, not in the tab.
  onHide: () => void;
}

const MESSAGE: Record<Props["phase"], string> = {
  launching: "Launching program…",
  running: "Running program…",
  stopping: "Stopping program…",
  finished: "Program finished.",
  unfinished: "Program finished with errors.",
};

export default function RunStatusIndicator({ phase, output, onHide }: Props) {

  return (

    <div
      data-general-phase={phase}
      style={{
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 360,
      }}
    >

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >

        <span>
          {MESSAGE[phase]}
        </span>

        <button onClick={onHide}>
          Hide
        </button>

      </div>

      {phase === "unfinished" && output && (

        <pre
          style={{
            margin: 0,
            padding: 8,
            maxHeight: 180,
            overflow: "auto",
            background: "#f5f5f5",
            border: "1px solid #ddd",
            borderRadius: 4,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 12,
            whiteSpace: "pre",
          }}
        >
          {output}
        </pre>

      )}

    </div>

  );

}
