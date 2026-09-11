interface Props {
  phase: "running" | "finished" | "unfinished";
  // debasher_status's output from the poll that settled on
  // "unfinished" — shown below the message so the failure can be
  // diagnosed on the spot. Ignored for any other phase.
  output?: string | null;
  onClose: () => void;
}

const MESSAGE: Record<Props["phase"], string> = {
  running: "Running program…",
  finished: "Program finished.",
  unfinished: "Program finished with errors.",
};

export default function RunStatusIndicator({ phase, output, onClose }: Props) {

  return (

    <div
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

        <button onClick={onClose}>
          {phase === "running" ? "Stop" : "Close"}
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
            whiteSpace: "pre-wrap",
          }}
        >
          {output}
        </pre>

      )}

    </div>

  );

}
