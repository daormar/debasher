import { useClaudeTerminal } from "../store/ClaudeTerminalContext";

// What a hidden terminal panel leaves on the canvas: the state of its session
// of Claude Code, and "Show" to bring the panel back (see "The terminal panel"
// in doc/design_doc_webui.md).
export default function ClaudeTerminalMini() {

  const { phase, visible, notice, setVisible } = useClaudeTerminal();

  if (phase === "none" || visible) {
    return null;
  }

  const status =
    phase === "starting" ? "Starting..." :
    phase === "running" ? "Running" :
    notice;

  return (

    <div
      role="status"
      aria-label="Claude Code session"
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
      }}
    >

      <span>
        <strong>Claude Code</strong>
        {status && <>: {status}</>}
      </span>

      <button onClick={() => setVisible(true)}>
        Show
      </button>

    </div>

  );

}
