interface Props {
  outputDir: string;
  isPending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ResetOutputDirConfirm({
  outputDir,
  isPending,
  error,
  onConfirm,
  onCancel,
}: Props) {

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
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0, color: "#b00020" }}>
          Reset output directory?
        </h3>

        <p style={{ margin: 0, fontSize: 14 }}>
          This will permanently delete everything inside:
        </p>

        <code
          style={{
            fontSize: 13,
            wordBreak: "break-all",
            background: "#f5f5f5",
            padding: "4px 6px",
            borderRadius: 4,
          }}
        >
          {outputDir}
        </code>

        <p style={{ margin: 0, fontSize: 14 }}>
          This cannot be undone.
        </p>

        {error && (
          <div style={{ color: "#b00020", fontSize: 13 }}>
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onCancel} disabled={isPending}>
            Cancel
          </button>

          <button
            onClick={onConfirm}
            disabled={isPending}
            style={{
              background: "#b00020",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              padding: "6px 12px",
              cursor: isPending ? "default" : "pointer",
            }}
          >
            {isPending ? "Resetting..." : "Reset"}
          </button>

        </div>

      </div>

    </div>

  );

}
