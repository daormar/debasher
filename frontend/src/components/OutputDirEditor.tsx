import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  onClose: () => void;
}

export default function OutputDirEditor({ onClose }: Props) {

  const {
    program,
    isRunInProgress,
    setOutputDir,
  } = useProgram();

  const [draft, setDraft] =
    useState(program.outputDir);

  const [error, setError] =
    useState<string | null>(null);

  const conflictsWithHomeDir =
    !!program.homeDir.trim() && draft.trim() === program.homeDir.trim();

  function handleSave() {
    if (conflictsWithHomeDir) {
      return;
    }
    try {
      setOutputDir(draft);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set output directory.");
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
          Output directory
        </h3>

        <DirectoryBrowser initialPath={draft} onPathChange={setDraft} />

        {conflictsWithHomeDir && (
          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            This matches the program's save directory ({program.homeDir}).
            Running here would mix engine-internal files into the saved
            program, and "Reset output directory" would delete it. Pick a
            different directory.
          </div>
        )}

        {isRunInProgress && (
          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            A run is in progress for this program's output directory.
            Changing it is disabled until the run finishes.
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

          <button onClick={onClose}>
            Cancel
          </button>

          <button
            onClick={handleSave}
            disabled={conflictsWithHomeDir || isRunInProgress || !draft.trim()}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
