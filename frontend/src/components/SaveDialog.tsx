import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  onClose: () => void;
}

export default function SaveDialog({ onClose }: Props) {

  const { program, save, isRunInProgress } = useProgram();

  const [outputDir, setOutputDir] =
    useState(program.homeDir);

  const [isSaving, setSaving] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const conflictsWithOutputDir =
    !!program.outputDir.trim() && outputDir.trim() === program.outputDir.trim();

  async function handleSave() {

    if (!outputDir.trim()) {
      setError("Please enter an output directory.");
      return;
    }

    if (conflictsWithOutputDir) {
      setError("This can't be the same as the program's output directory.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await save(outputDir.trim());
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save program."
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
          maxWidth: 560,
          height: "70%",
          maxHeight: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Save program
        </h3>

        <DirectoryBrowser initialPath={outputDir} onPathChange={setOutputDir} />

        {isRunInProgress && (
          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            A run is in progress for this program's output directory.
            Saving is disabled until it finishes: it would overwrite
            the script that not-yet-started processes read from disk
            when they start.
          </div>
        )}

        {conflictsWithOutputDir && (
          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            This matches the program's output directory ({program.outputDir}).
            Saving here would let a run overwrite the saved program, and
            "Reset output directory" would delete it. Pick a different
            directory.
          </div>
        )}

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

          <button
            onClick={handleSave}
            disabled={
              isSaving || isRunInProgress || conflictsWithOutputDir || !outputDir.trim()
            }
          >
            {isSaving ? "Saving..." : "Save"}
          </button>

        </div>

      </div>

    </div>

  );

}
