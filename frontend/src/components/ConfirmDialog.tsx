import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

// Asks the user to confirm a destructive action, with a warning that says
// what it does.
export default function ConfirmDialog({
  title,
  children,
  confirmLabel,
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
          fontSize: 14,
        }}
      >

        <h3 style={{ margin: 0, color: "#b00020" }}>
          {title}
        </h3>

        {children}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onCancel}>
            Cancel
          </button>

          <button
            onClick={onConfirm}
            style={{
              background: "#b00020",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              padding: "6px 12px",
              cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>

        </div>

      </div>

    </div>

  );

}
