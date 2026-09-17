import { useState } from "react";
import type { Program } from "../models/program";
import { loadProgram } from "../storage/programStorage";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  onLoad: (program: Program) => void;
  onClose: () => void;
}

export default function LoadProgramDialog({ onLoad, onClose }: Props) {

  const [currentDir, setCurrentDir] =
    useState("");

  const [isLoading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleLoad() {

    if (!currentDir.trim()) {
      setError("Please browse to a program directory.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const program = await loadProgram(currentDir.trim());
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
          Load program
        </h3>

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

          <button onClick={handleLoad} disabled={isLoading || !currentDir.trim()}>
            {isLoading ? "Loading..." : "Load"}
          </button>

        </div>

      </div>

    </div>

  );

}
