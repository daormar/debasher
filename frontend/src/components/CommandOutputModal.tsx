interface Props {
  title: string;
  output: string;
  onClose: () => void;
}

export default function CommandOutputModal({ title, output, onClose }: Props) {

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

      <div
        style={{
          width: "60%",
          maxWidth: 720,
          maxHeight: "80vh",
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          {title}
        </h3>

        <pre
          style={{
            width: "100%",
            maxHeight: "60vh",
            margin: 0,
            padding: 8,
            background: "#f5f5f5",
            border: "1px solid #ddd",
            borderRadius: 4,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 13,
            whiteSpace: "pre-wrap",
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
