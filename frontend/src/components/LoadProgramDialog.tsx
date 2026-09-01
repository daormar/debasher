import { useState } from "react";
import type { Program } from "../models/program";
import { loadProgram } from "../storage/programStorage";

interface Props {
  onLoad: (program: Program) => void;
  onClose: () => void;
}

export default function LoadProgramDialog({ onLoad, onClose }: Props) {

  const [inputDir, setInputDir] =
    useState("");

  const [isLoading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleLoad() {

    if (!inputDir.trim()) {
      setError("Please enter a program directory.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const program = await loadProgram(inputDir.trim());
      onLoad(program);
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
          Load program
        </h3>

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
              handleLoad();
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

          <button onClick={handleLoad} disabled={isLoading}>
            {isLoading ? "Loading..." : "Load"}
          </button>

        </div>

      </div>

    </div>

  );

}
