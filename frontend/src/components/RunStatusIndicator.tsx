interface Props {
  phase: "running" | "finished" | "unfinished";
  onClose: () => void;
}

const MESSAGE: Record<Props["phase"], string> = {
  running: "Running workflow…",
  finished: "Workflow finished.",
  unfinished: "Workflow finished with errors.",
};

export default function RunStatusIndicator({ phase, onClose }: Props) {

  return (

    <div
      style={{
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
        padding: "10px 12px",
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

  );

}
