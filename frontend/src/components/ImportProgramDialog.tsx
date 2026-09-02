import { useState } from "react";
import type { Program } from "../models/program";
import { importProgram } from "../storage/programStorage";

interface Props {
  onImport: (program: Program) => void;
  onClose: () => void;
}

export default function ImportProgramDialog({ onImport, onClose }: Props) {

  const [scriptPath, setScriptPath] =
    useState("");

  const [debasherModDir, setDebasherModDir] =
    useState("");

  const [isImporting, setImporting] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function handleImport() {

    if (!scriptPath.trim()) {
      setError("Please enter a script path.");
      return;
    }

    setImporting(true);
    setError(null);

    try {
      const program = await importProgram(scriptPath.trim(), debasherModDir.trim());
      onImport(program);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to import program."
      );
    } finally {
      setImporting(false);
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
          Import program
        </h3>

        <label style={{ fontSize: 14 }}>
          DEBASHER_MOD_DIR (optional)
        </label>

        <input

          type="text"

          value={debasherModDir}

          onChange={(event) =>
            setDebasherModDir(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleImport();
            }
          }}

          placeholder="/path/to/modules"

          autoFocus

          style={{
            width: "100%",
          }}

        />

        <label style={{ fontSize: 14 }}>
          Script path (.sh)
        </label>

        <input

          type="text"

          value={scriptPath}

          onChange={(event) =>
            setScriptPath(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleImport();
            }
          }}

          placeholder="/path/to/program.sh"

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

          <button onClick={onClose} disabled={isImporting}>
            Cancel
          </button>

          <button onClick={handleImport} disabled={isImporting}>
            {isImporting ? "Importing..." : "Import"}
          </button>

        </div>

      </div>

    </div>

  );

}
