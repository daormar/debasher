import { useState } from "react";
import type { Program } from "../models/program";
import { loadProgram } from "../storage/programStorage";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  onAdd: (loaded: Program, sourceDir: string) => void;
  onClose: () => void;
}

export default function AddProgramDialog({ onAdd, onClose }: Props) {

  const [currentDir, setCurrentDir] =
    useState("");

  const [isLoading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleAdd() {

    if (!currentDir.trim()) {
      setError("Please browse to a program directory.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const dir = currentDir.trim();
      const loaded = await loadProgram(dir);
      onAdd(loaded, dir);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load program."
      );
    } finally {
      setLoading(false);
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
          Add program
        </h3>

        <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
          Adds every process from a previously-saved program into this one,
          as a group generated via add_debasher_program.
        </p>

        <DirectoryBrowser initialPath="" onPathChange={setCurrentDir} />

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

          <button onClick={onClose} disabled={isLoading}>
            Cancel
          </button>

          <button onClick={handleAdd} disabled={isLoading || !currentDir.trim()}>
            {isLoading ? "Adding..." : "Add"}
          </button>

        </div>

      </div>

    </div>

  );

}
