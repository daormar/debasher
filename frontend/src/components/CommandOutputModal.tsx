interface Props {
  title: string;
  // What the outcome means, shown as text above what the tool printed.
  message?: string;
  output: string;
  onClose: () => void;
}

export default function CommandOutputModal({ title, message, output, onClose }: Props) {

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      {/* A fixed width, whatever the output, which scrolls inside it: a
          long path, in the title or in the output, never widens it */}
      <div
        style={{
          width: "min(900px, 90vw)",
          maxHeight: "80vh",
          boxSizing: "border-box",
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0, overflowWrap: "anywhere" }}>
          {title}
        </h3>

        {message && (
          <p style={{ margin: 0, fontSize: 14, overflowWrap: "anywhere" }}>
            {message}
          </p>
        )}

        <pre
          style={{
            width: "100%",
            minHeight: 0,
            maxHeight: "60vh",
            margin: 0,
            padding: 8,
            background: "#f5f5f5",
            border: "1px solid #ddd",
            borderRadius: 4,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 13,
            whiteSpace: "pre",
            overflow: "auto",
            boxSizing: "border-box",
          }}
        >
          {output || "No output."}
        </pre>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Close
          </button>

        </div>

      </div>

    </div>

  );

}
