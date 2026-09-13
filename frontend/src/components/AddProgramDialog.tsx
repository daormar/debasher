import { useState } from "react";
import type { Program } from "../models/program";
import { loadProgram } from "../storage/programStorage";

interface Props {
  onAdd: (loaded: Program, sourceDir: string) => void;
  onClose: () => void;
}

export default function AddProgramDialog({ onAdd, onClose }: Props) {

  const [inputDir, setInputDir] =
    useState("");

  const [isLoading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleAdd() {

    if (!inputDir.trim()) {
      setError("Please enter a program directory.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const dir = inputDir.trim();
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
          Add program
        </h3>

        <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
          Adds every process from a previously-saved program into this one,
          as a group generated via add_debasher_program.
        </p>

        <label style={{ fontSize: 14 }}>
          Program directory
        </label>

        <input

          type="text"

          value={inputDir}

          onChange={(event) =>
            setInputDir(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleAdd();
            }
          }}

          placeholder="/path/to/program/directory"

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

          <button onClick={onClose} disabled={isLoading}>
            Cancel
          </button>

          <button onClick={handleAdd} disabled={isLoading}>
            {isLoading ? "Adding..." : "Add"}
          </button>

        </div>

      </div>

    </div>

  );

}
