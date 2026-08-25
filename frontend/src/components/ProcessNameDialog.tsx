import { useState } from "react";

import { validateProcessName } from "../api/processApi";

interface Props {
  title: string;
  confirmLabel: string;
  initialName?: string;
  existingNames: string[];
  onConfirm: (name: string) => void;
  onClose: () => void;
}

export default function ProcessNameDialog({
  title,
  confirmLabel,
  initialName = "",
  existingNames,
  onConfirm,
  onClose,
}: Props) {

  const [name, setName] =
    useState(initialName);

  const [isValidating, setValidating] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleConfirm() {

    const trimmedName = name.trim();

    if (!trimmedName) {
      setError("Please enter a process name.");
      return;
    }

    const isDuplicate = existingNames.some(
      existingName => existingName.toLowerCase() === trimmedName.toLowerCase()
    );

    if (isDuplicate) {
      setError("A process with this name already exists.");
      return;
    }

    setValidating(true);
    setError(null);

    try {
      const valid = await validateProcessName(trimmedName);

      if (!valid) {
        setError("Invalid process name.");
        return;
      }

      onConfirm(trimmedName);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to validate process name."
      );
    } finally {
      setValidating(false);
    }

  }

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

        <h3 style={{ margin: 0 }}>
          {title}
        </h3>

        <label style={{ fontSize: 14 }}>
          Name
        </label>

        <input

          type="text"

          value={name}

          onChange={(event) =>
            setName(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleConfirm();
            }
          }}

          autoFocus

          style={{
            width: "100%",
          }}

        />

        {error && (
          <div style={{ color: "#b00020", fontSize: 14 }}>
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

          <button onClick={onClose} disabled={isValidating}>
            Cancel
          </button>

          <button onClick={handleConfirm} disabled={isValidating}>
            {isValidating ? "Validating..." : confirmLabel}
          </button>

        </div>

      </div>

    </div>

  );

}
