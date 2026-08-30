import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";

interface Props {
  onClose: () => void;
}

export default function SaveDialog({ onClose }: Props) {

  const { save } = useWorkflow();

  const [outputDir, setOutputDir] =
    useState("");

  const [isSaving, setSaving] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleSave() {

    if (!outputDir.trim()) {
      setError("Please enter an output directory.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await save(outputDir.trim());
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save workflow."
      );
    } finally {
      setSaving(false);
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
          Save workflow
        </h3>

        <label style={{ fontSize: 14 }}>
          Output directory
        </label>

        <input

          type="text"

          value={outputDir}

          onChange={(event) =>
            setOutputDir(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleSave();
            }
          }}

          placeholder="/path/to/output/directory"

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

          <button onClick={onClose} disabled={isSaving}>
            Cancel
          </button>

          <button onClick={handleSave} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save"}
          </button>

        </div>

      </div>

    </div>

  );

}
